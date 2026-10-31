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

    # Never ask for a lag the data cannot support: acf[lag] divides by
    # (n - lag), so a short window used to raise ZeroDivisionError.
    n = len(onsets)
    max_lag = min(lag_max * len(harmonics), n - 1)
    if max_lag <= lag_min:
        return None, 0.0
    lag_max = min(lag_max, max_lag)

    acf = [0.0] * (max_lag + 1)
    for lag in range(1, max_lag + 1):
        s = 0.0
        for i in range(lag, n):
            s += onsets[i] * onsets[i - lag]
        acf[lag] = s / (n - lag)

    candidates = acf[lag_min:lag_max + 1]
    peak = max(candidates) or 1e-12
    avg = sum(candidates) / len(candidates)
    strength = (peak / avg) if avg > 0 else 0.0

    scores: dict[int, float] = {}
    best_score, best_lag = -1.0, lag_min
    for lag in range(lag_min, lag_max + 1):
        score = 0.0
        for h, w in enumerate(harmonics, start=1):
            L = lag * h
            if L > max_lag:
                break
            score += w * acf[L]
        score *= _tempo_prior(60.0 / (lag * hop_sec), prefer_bpm, prior_octaves)
        scores[lag] = score
        if score > best_score:
            best_score, best_lag = score, lag

    # Parabolic interpolation around the peak for sub-lag resolution. Without
    # it the 23 ms hop resolves only ~1.5% at 120 BPM, which is enough to
    # misread a clean 127 BPM click track as 129.2 - and a wrong tempo ruins
    # any attempt to beat-match or warp.
    refined = float(best_lag)
    if lag_min < best_lag < lag_max:
        a, b, c = scores[best_lag - 1], scores[best_lag], scores[best_lag + 1]
        denom = a - 2.0 * b + c
        if denom != 0.0:
            refined += 0.5 * (a - c) / denom

    return round(60.0 / (refined * hop_sec), 1), round(strength, 3)


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
                    seconds: float = 20.0, drop_ratio: float = 0.35,
                    trend: float = 0.6) -> bool:
    """A sustained level drop over the last ``seconds``.

    Compares the level near the start of the window with the end (rather than
    requiring an almost-perfectly monotonic curve, which noise breaks), so a
    long fade is caught even when it spans more than the ~12 s ending window.
    """
    if not env:
        return False
    k = max(3, int(seconds / (hop / sr)))
    tail = env[-k:] if len(env) > k else env
    if len(tail) < 3:
        return False
    start = sum(tail[:3]) / 3.0
    end = sum(tail[-3:]) / 3.0
    decreasing = sum(1 for i in range(1, len(tail)) if tail[i] <= tail[i - 1])
    return (end / (start or 1e-9) < drop_ratio) and (decreasing / (len(tail) - 1) >= trend)


def kick_entry(samples: array, sr: int, block: float = 1.0,
               rise_db: float = 4.0, sustain: int = 3) -> float:
    """Seconds until a sustained low-band rise - where the kick comes in.

    Feed it a low-passed (kick-band) signal. Returns 0.0 when the level is flat
    from the start (a kick from bar one) or never rises.
    """
    n = int(sr * block)
    if n < 2 or len(samples) < n * (sustain + 3):
        return 0.0
    levels = []
    for i in range(0, len(samples) - n + 1, n):
        seg = samples[i:i + n]
        r = math.sqrt(sum(float(x) * float(x) for x in seg) / len(seg)) or 1e-9
        levels.append(20.0 * math.log10(r / 32768.0))
    base = sum(levels[:3]) / 3.0
    thr = base + rise_db
    for i in range(3, len(levels) - sustain):
        if all(levels[i + j] > thr for j in range(sustain)):
            return round(i * block, 2)
    return 0.0


def noise_tail_span(samples: array, sr: int, block: float = 0.25,
                    zcr_tonal: float = 0.30) -> float:
    """Seconds of a trailing non-tonal (noise / cymbal-splash) run at the end.

    Walks backwards from the end while the blocks are non-tonal (high zero
    crossing rate) and stops at the first tonal block. A cymbal crash or noise
    FX reads 0.4-0.7 ZCR; tonal material (even a bright arp fading out) stays
    under ~0.25. No level floor: a splash decays below any sensible floor while
    still being noise, and silence has a zero crossing rate of ~0.
    """
    n = int(sr * block)
    if n < 2 or len(samples) < n * 4:
        return 0.0
    run = 0
    for start in range(len(samples) - n, -1, -n):
        if zero_crossing_rate(samples[start:start + n]) >= zcr_tonal:
            run += 1
        else:
            break
    return round(run * block, 3)


def fade_span(env: list[float], sr: int, hop: int = HOP,
              level: float = 0.5) -> float:
    """Seconds from the last time the envelope was >= ``level`` * peak to the end.

    A proxy for how long the ending has been decaying - used to make a
    crossfade cover a fade instead of starting after it.
    """
    if not env:
        return 0.0
    peak = max(env) or 1e-9
    thr = peak * level
    idx = len(env) - 1
    while idx > 0 and env[idx] < thr:
        idx -= 1
    return round((len(env) - 1 - idx) * (hop / sr), 3)


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
