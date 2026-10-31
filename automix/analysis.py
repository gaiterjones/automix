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

# Tempo uses its own, finer framing: a short (~93 ms) frame for transient
# resolution and a 192-sample hop (~17 ms). At the default 23 ms hop the tempo
# grid only resolves ~1.5% near 120 BPM, which is enough to read a clean 127
# click track as 128-129 - and a wrong tempo ruins beat-matching.
TEMPO_HOP = 192


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
        "noise_tail": dsp.noise_tail_span(samples, sr),
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
    tempo_env = dsp.frame_rms(ffmpeg.decode_pcm(path, b_start, b_len, sr), dsp.FRAME, TEMPO_HOP)
    bpm, strength = dsp.estimate_tempo(tempo_env, sr, TEMPO_HOP)
    head["bpm"], head["tempo_strength"] = bpm, strength

    # beatless intros: when does the kick come in? (first sustained rise in the
    # kick band) and a body beat grid to align against when entering mid-track
    kick_entry = dsp.kick_entry(
        ffmpeg.decode_pcm_filtered(path, "lowpass=f=120", 0.0, min(45.0, dur), sr), sr)
    body_beat = beatgrid.detect(
        ffmpeg.decode_pcm(path, b_start, min(20.0, b_len), sr), sr, bpm=bpm, start=b_start)

    # outro - the actual ending (last ~12s), plus a 30s tail for context
    end = _features(ffmpeg.decode_pcm(path, max(0.0, dur - edge), edge, sr), sr)

    # If the very end is a cymbal splash / noise FX (abrupt jump to broadband
    # noise), judge the outro from the music BEFORE it - the splash should be
    # trimmed away, not blended. Keep noise_tail so the planner can trim it.
    noise_tail = float(end.get("noise_tail") or 0.0)
    if noise_tail >= 1.0:
        # +1s margin: the ZCR run stops where the crash becomes tonal-ish, but
        # the crash onset is a little earlier. Judge (and trim) from before it.
        noise_tail = round(min(noise_tail + 1.0, edge), 2)
        body = _features(ffmpeg.decode_pcm(path, max(0.0, dur - noise_tail - edge), edge, sr), sr)
        body["noise_tail"] = noise_tail
        end = body

    tail = _features(ffmpeg.decode_pcm(path, max(0.0, dur - window), window, sr), sr)

    # beat grids at the head (incoming) and tail (outgoing) for beat alignment.
    # The tail grid must not include a splash/noise tail - there are no beats in
    # a cymbal crash, and fitting a grid to it skews the phase.
    bw = min(BEAT_WINDOW, dur)
    head_beat = beatgrid.detect(ffmpeg.decode_pcm(path, 0, bw, sr), sr, bpm=bpm, start=0.0)
    tb_end = max(bw, dur - noise_tail)
    tb_start = max(0.0, tb_end - bw)
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
        "body_beat": body_beat,
        "kick_entry": kick_entry,
        "intro_class": classify_intro(head),
        "outro_class": classify_outro(end, head),
    }


def analyze_tracks(paths: list[str], window: float = 30.0, edge: float = 12.0,
                   sr: int = ffmpeg.DEFAULT_SR) -> list[dict]:
    return [analyze_track(p, window=window, edge=edge, sr=sr) for p in paths]
