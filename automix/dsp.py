"""Dependency-free DSP helpers.

Small, transparent functions over an ``array('h')`` of PCM samples. They are
deliberately simple (RMS envelope, onset function, autocorrelation tempo, zero
crossing rate) - enough to characterise a track's head and tail without
pulling in numpy/librosa.
"""
from __future__ import annotations

import math
from array import array

FRAME = 1024
HOP = 256


def frame_rms(samples: array, frame: int = FRAME, hop: int = HOP) -> list[float]:
    n = len(samples)
    if n == 0:
        return []
    if n < frame:
        frame = n
    env: list[float] = []
    for i in range(0, n - frame + 1, hop):
        s = 0.0
        for x in samples[i:i + frame]:
            s += float(x) * float(x)
        env.append(math.sqrt(s / frame))
    return env or [0.0]


def onset_envelope(env: list[float]) -> list[float]:
    """Half-wave rectified first difference - rises in energy."""
    out = [0.0]
    for i in range(1, len(env)):
        d = env[i] - env[i - 1]
        out.append(d if d > 0 else 0.0)
    return out


def _tempo_prior(bpm: float, prefer_bpm: float, octaves: float) -> float:
    """Log-normal-ish prior favouring a plausible tempo (librosa-style)."""
    if octaves <= 0:
        return 1.0
    d = math.log2(bpm / prefer_bpm) / octaves
    return math.exp(-0.5 * d * d)


def estimate_tempo(env: list[float], sr: int, hop: int = HOP,
                   bpm_min: float = 60.0, bpm_max: float = 200.0,
                   harmonics: tuple = (1.0, 0.5, 0.25),
                   prefer_bpm: float = 120.0, prior_octaves: float = 0.9) -> tuple[float | None, float]:
    """Tempo from the onset-envelope autocorrelation, with HARMONIC WEIGHTING.

    A plain argmax of the autocorrelation picks octave/ratio errors (a track at
    123 BPM reports 63 or 82). Scoring each candidate lag by the summed
    autocorrelation at its harmonics (lag, 2*lag, 3*lag) reinforces the true
    tempo and suppresses those sub-harmonics - the standard fix.

    Returns (bpm, strength); strength is peak/mean of the candidate range
    (>= 1, higher = more clearly rhythmic) and is unaffected by the weighting.
    """
    onsets = onset_envelope(env)
    hop_sec = hop / sr
    if len(onsets) < 8:
        return None, 0.0

    mean = sum(onsets) / len(onsets)
    onsets = [max(0.0, v - mean) for v in onsets]
    if sum(v * v for v in onsets) <= 0:
        return None, 0.0

    lag_min = max(1, int(round(60.0 / (bpm_max * hop_sec))))
    lag_max = max(lag_min + 1, int(round(60.0 / (bpm_min * hop_sec))))
    max_lag = lag_max * len(harmonics)

    acf = [0.0] * (max_lag + 1)
    n = len(onsets)
    for lag in range(1, max_lag + 1):
        s = 0.0
        for i in range(lag, n):
            s += onsets[i] * onsets[i - lag]
        acf[lag] = s / (n - lag)

    candidates = acf[lag_min:lag_max + 1]
    peak = max(candidates) or 1e-12
    avg = sum(candidates) / len(candidates)
    strength = (peak / avg) if avg > 0 else 0.0

    best_score, best_lag = -1.0, lag_min
    for lag in range(lag_min, lag_max + 1):
        score = 0.0
        for h, w in enumerate(harmonics, start=1):
            L = lag * h
            if L > max_lag:
                break
            score += w * acf[L]
        score *= _tempo_prior(60.0 / (lag * hop_sec), prefer_bpm, prior_octaves)
        if score > best_score:
            best_score, best_lag = score, lag

    return round(60.0 / (best_lag * hop_sec), 1), round(strength, 3)


def zero_crossing_rate(samples: array) -> float:
    n = len(samples)
    if n < 2:
        return 0.0
    crossings = 0
    prev = samples[0] >= 0
    for x in samples[1:]:
        cur = x >= 0
        if cur != prev:
            crossings += 1
        prev = cur
    return crossings / (n - 1)


def rms_db(env: list[float]) -> float | None:
    if not env:
        return None
    mean = sum(env) / len(env)
    if mean <= 0:
        return None
    # env values are 16-bit amplitude RMS; reference full scale 32768
    return round(20.0 * math.log10(mean / 32768.0), 2)


def silence_edges(env: list[float], sr: int, hop: int = HOP,
                  thresh_ratio: float = 0.02) -> tuple[float, float]:
    """(leading_silence_sec, trailing_silence_sec) relative to the window peak."""
    if not env:
        return 0.0, 0.0
    hop_sec = hop / sr
    peak = max(env) or 1e-9
    thr = peak * thresh_ratio
    lead = 0
    while lead < len(env) and env[lead] < thr:
        lead += 1
    trail = 0
    while trail < len(env) and env[len(env) - 1 - trail] < thr:
        trail += 1
    return round(lead * hop_sec, 3), round(trail * hop_sec, 3)


def onset_rate(env: list[float], sr: int, hop: int = HOP,
               ratio: float = 0.10) -> float:
    """Transients per second - a rise bigger than ``ratio`` of the loudest frame.

    Thresholding against the envelope peak (not the peak onset) keeps a steady
    tone from being counted as a storm of onsets.
    """
    if len(env) < 2:
        return 0.0
    peak = max(env) or 1e-9
    thr = peak * ratio
    count = sum(1 for v in onset_envelope(env) if v > thr)
    return round(count / ((len(env) * hop) / sr), 2)


def fade_out_likely(env: list[float], sr: int, hop: int = HOP,
                    seconds: float = 8.0) -> bool:
    """A steady, engineered fade over the last ``seconds``."""
    if not env:
        return False
    k = max(3, int(seconds / (hop / sr)))
    tail = env[-k:] if len(env) > k else env
    if len(tail) < 3:
        return False
    decreasing = sum(1 for i in range(1, len(tail)) if tail[i] <= tail[i - 1])
    end_ratio = (sum(tail[-3:]) / 3.0) / ((max(tail) or 1e-9))
    return (decreasing / (len(tail) - 1)) > 0.75 and end_ratio < 0.35


def abrupt_end(env: list[float], sr: int, hop: int = HOP,
               seconds: float = 0.20, level_ratio: float = 0.35) -> bool:
    """File still near full level in its final ``seconds`` -> abrupt stop.

    (A fade is caught separately; this only fires when the material is still
    loud right up to EOF.)
    """
    if not env:
        return False
    k = max(1, int(seconds / (hop / sr)))
    tail = env[-k:]
    peak = max(env) or 1e-9
    return (sum(tail) / len(tail)) > level_ratio * peak
