"""Per-track fingerprinting and head/tail classification."""
from __future__ import annotations

from . import beatgrid, dsp, ffmpeg, taxonomy

# seconds of head/tail used to locate the beat grid for alignment
BEAT_WINDOW = 20.0

# RMS envelope window, in seconds. Deliberately long: a ~1 s RMS curve is smooth
# enough that silence-edge and fade detection are stable, while the hop stays
# short (23 ms) so boundaries still land precisely. (A short ~93 ms frame makes
# the envelope jittery and the fade test unreliable.)
ENVELOPE_SECONDS = 1.0


def _envelope(samples, sr: int) -> list[float]:
    return dsp.frame_rms(samples, frame=max(1, int(sr * ENVELOPE_SECONDS)))

# tunable thresholds (v1 heuristics - adjust after listening)
T_STRENGTH = 2.0     # autocorr peak/mean for "clearly rhythmic"
T_ONSET = 2.0        # onsets/sec for "active rhythm"
T_ZCR = 0.16         # zero-crossing rate for "noisy / voice-like"
T_LEAD = 1.0         # seconds of leading silence -> silent lead-in


def _features(samples, sr: int) -> dict:
    env = _envelope(samples, sr)
    bpm, strength = dsp.estimate_tempo(env, sr)
    lead, trail = dsp.silence_edges(env, sr)
    return {
        "seconds": round(len(samples) / sr, 2),
        "rms_db": dsp.rms_db(env),
        "peak": round(max(env), 1) if env else 0.0,
        "onset_rate": dsp.onset_rate(env, sr),
        "bpm": bpm,
        "tempo_strength": strength,
        "zcr": round(dsp.zero_crossing_rate(samples), 4),
        "lead_silence": lead,
        "trail_silence": trail,
        "fade": dsp.fade_out_likely(env, sr),
        "fade_span": dsp.fade_span(env, sr),
        "abrupt": dsp.abrupt_end(env, sr),
    }


def classify_intro(f: dict) -> str:
    if f["lead_silence"] >= T_LEAD:
        return taxonomy.INTRO_SILENT
    if f["tempo_strength"] >= T_STRENGTH:            # clear rhythm from the top
        return taxonomy.INTRO_BEAT
    if f["zcr"] >= T_ZCR and f["tempo_strength"] < 1.8:   # noisy / voice-like
        return taxonomy.INTRO_SPOKEN
    if f["tempo_strength"] >= 1.4 and f["onset_rate"] >= T_ONSET:
        return taxonomy.INTRO_PERC
    if f["tempo_strength"] < 1.4 and f["onset_rate"] < 1.5:
        if f["rms_db"] is None or f["rms_db"] < -45:
            return taxonomy.INTRO_SILENT
        return taxonomy.INTRO_AMBIENT
    return taxonomy.INTRO_MELODIC


def classify_outro(f: dict, head: dict) -> str:
    if f["fade"]:                                    # an engineered fade wins
        return taxonomy.OUTRO_FADE
    if f["tempo_strength"] >= T_STRENGTH:            # rhythm runs to the end
        return taxonomy.OUTRO_BEATRUN
    if f["abrupt"]:
        return taxonomy.OUTRO_HARDSTOP
    if f["trail_silence"] >= 1.0:
        return taxonomy.OUTRO_BREAK
    if f["rms_db"] is None or f["rms_db"] < -45:     # near-silent ending (dead tail)
        return taxonomy.OUTRO_BREAK
    if f["zcr"] >= T_ZCR and f["tempo_strength"] < 1.8:
        return taxonomy.OUTRO_VOCAL
    if (f["rms_db"] is not None and head["rms_db"] is not None
            and f["rms_db"] < head["rms_db"] - 6.0):
        return taxonomy.OUTRO_RING
    return taxonomy.OUTRO_BEATRUN


def analyze_track(path: str, window: float = 30.0, edge: float = 12.0,
                  sr: int = ffmpeg.DEFAULT_SR) -> dict:
    meta = ffmpeg.ffprobe_metadata(path)
    duration = meta.get("duration") or 0.0
    dur = duration or window
    loud = ffmpeg.measure_loudness(path)
    silences = ffmpeg.detect_silence(path)

    # intro / overall character - first 30s
    head = _features(ffmpeg.decode_pcm(path, 0, min(window, dur), sr), sr)

    # tempo - a mid-track window. Intros and outros mislead the estimator (a
    # quiet or half-time opening reads as a different tempo), so measure the body.
    b_start = max(0.0, dur * 0.15)
    b_len = min(60.0, max(20.0, dur * 0.5))
    bpm, strength = dsp.estimate_tempo(_envelope(ffmpeg.decode_pcm(path, b_start, b_len, sr), sr), sr)
    head["bpm"], head["tempo_strength"] = bpm, strength

    # outro - the actual ending (last ~12s), plus a 30s tail for context
    end = _features(ffmpeg.decode_pcm(path, max(0.0, dur - edge), edge, sr), sr)
    tail = _features(ffmpeg.decode_pcm(path, max(0.0, dur - window), window, sr), sr)

    # beat grids at the head (incoming) and tail (outgoing) for beat alignment
    bw = min(BEAT_WINDOW, dur)
    head_beat = beatgrid.detect(ffmpeg.decode_pcm(path, 0, bw, sr), sr, bpm=bpm, start=0.0)
    tb_start = max(0.0, dur - bw)
    tail_beat = beatgrid.detect(ffmpeg.decode_pcm(path, tb_start, bw, sr), sr, bpm=bpm, start=tb_start)

    return {
        "path": path,
        "duration": round(duration, 2),
        "sample_rate": meta.get("sample_rate"),
        "channels": meta.get("channels"),
        "codec": meta.get("codec"),
        "bit_rate": meta.get("bit_rate"),
        "lufs_integrated": loud.get("integrated_lufs"),
        "lra": loud.get("lra"),
        "true_peak_db": loud.get("true_peak_db"),
        "silences": [[round(s, 2) if s is not None else None,
                      round(e, 2) if e is not None else None] for s, e in silences],
        "bpm": bpm,
        "tempo_strength": strength,
        "head": head,
        "end": end,
        "tail": tail,
        "head_beat": head_beat,
        "tail_beat": tail_beat,
        "intro_class": classify_intro(head),
        "outro_class": classify_outro(end, head),
    }


def analyze_tracks(paths: list[str], window: float = 30.0, edge: float = 12.0,
                   sr: int = ffmpeg.DEFAULT_SR) -> list[dict]:
    return [analyze_track(p, window=window, edge=edge, sr=sr) for p in paths]
