"""Beat-grid detection: period, phase and (4/4) downbeat - pure stdlib.

Given a tempo, a comb filter over the onset envelope finds the phase that puts
the grid on the transients, and the strongest of the four bar positions is taken
as the downbeat. Enough to *align* two tracks so one's kick lands on the other's
during a crossfade.
"""
from __future__ import annotations

import math

from . import dsp


def detect(samples, sr: int, bpm: float | None = None, start: float = 0.0,
           hop: int = dsp.HOP, frame: int = dsp.FRAME) -> dict | None:
    """Return {bpm, period, phase, start, beats, strength, downbeat} or None.

    ``phase`` is seconds from the window start to the first beat; ``start`` is
    the window's offset within the track, so absolute beat times are
    ``start + phase + k*period``.
    """
    env = dsp.frame_rms(samples, frame, hop)
    if len(env) < 4:
        return None
    onsets = dsp.onset_envelope(env)
    hop_sec = hop / sr
    n = len(onsets)
    dur = n * hop_sec

    if bpm is None:
        bpm, _ = dsp.estimate_tempo(env, sr, hop)
    if not bpm or bpm <= 0:
        return None
    period = 60.0 / bpm
    steps = max(1, int(round(period / hop_sec)))

    best_score, best_phase = -1.0, 0.0
    for k in range(steps):
        phase = k * hop_sec
        total, count, t = 0.0, 0, phase
        while t < dur:
            idx = int(round(t / hop_sec))
            if 0 <= idx < n:
                total += onsets[idx]
            count += 1
            t += period
        if count and (total / count) > best_score:
            best_score, best_phase = total / count, phase

    mean = (sum(onsets) / n) if n else 0.0
    strength = round(best_score / mean, 3) if mean > 0 else 0.0

    # downbeat: which of the 4 bar positions carries the most onset energy
    sums, counts = [0.0] * 4, [0] * 4
    t, k = best_phase, 0
    while t < dur:
        idx = int(round(t / hop_sec))
        if 0 <= idx < n:
            sums[k % 4] += onsets[idx]
            counts[k % 4] += 1
        t += period
        k += 1
    avg = [(sums[i] / counts[i]) if counts[i] else 0.0 for i in range(4)]
    downbeat = avg.index(max(avg)) if any(avg) else 0

    return {
        "bpm": round(bpm, 2),
        "period": round(period, 4),
        "phase": round(best_phase, 4),
        "start": round(start, 3),
        "beats": k,
        "strength": strength,
        "downbeat": downbeat,
    }


def next_beat(grid: dict, t: float) -> float | None:
    """Absolute time of the first beat at or after ``t``."""
    if not grid:
        return None
    s = grid["start"] + grid["phase"]
    P = grid["period"]
    k = math.ceil((t - s) / P)
    return s + k * P


def mix_delay(out_fp: dict, in_fp: dict, overlap: float, out_trim: float = 0.0,
              in_warp: float = 1.0, min_strength: float = 1.5,
              max_drift: float = 0.03) -> float:
    """Seconds to delay the incoming track so its beat lands on the outgoing's.

    Returns 0.0 (no nudge) when either grid is weak or the tempos differ too
    much for an overlap to stay locked.
    """
    ta, tb = out_fp.get("tail_beat"), in_fp.get("head_beat")
    if not ta or not tb or not ta.get("bpm") or not tb.get("bpm"):
        return 0.0
    if ta.get("strength", 0) < min_strength or tb.get("strength", 0) < min_strength:
        return 0.0
    # A tempo warp removes the drift, so only gate on it when we are not warping
    if abs(in_warp - 1.0) < 1e-9 and abs(ta["bpm"] - tb["bpm"]) / ta["bpm"] > max_drift:
        return 0.0

    # the outgoing may be trimmed (splash tail) before the crossfade, so the
    # effective end is shorter than the track duration
    len_a = (out_fp.get("duration") or 0.0) - float(out_trim)
    t0 = len_a - overlap                     # overlap starts here in A
    a_next = next_beat(ta, t0)
    if a_next is None:
        return 0.0
    # the incoming's first beat, from its start - scaled by the warp (atempo
    # factor f compresses its timeline by 1/f)
    b0 = (tb["start"] + tb["phase"]) / float(in_warp)
    return round((a_next - t0 - b0) % ta["period"], 3)
