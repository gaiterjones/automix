"""Turn a set of fingerprints into a mix plan (the editable artefact).

The plan is plain JSON: per-track loudness gain and, per junction, the chosen
transition. Render just executes it - so a human (or an LLM) can edit the plan
without touching audio code.
"""
from __future__ import annotations

import json

from . import analysis, beatgrid, taxonomy


def build_plan(paths: list[str], fingerprints: list[dict] | None = None,
               target_lufs: float = -14.0, max_gain_db: float = 12.0,
               window: float = 30.0, title: str | None = None,
               beat_align: bool = False, tempo_match: bool = False,
               max_warp: float = 0.05, bass_cut_hz: int = 0) -> dict:
    if fingerprints is None:
        fingerprints = analysis.analyze_tracks(paths, window=window)
    if len(fingerprints) != len(paths):
        raise ValueError("fingerprints/paths length mismatch")

    tracks = []
    for path, fp in zip(paths, fingerprints):
        lufs = fp.get("lufs_integrated")
        gain = 0.0
        if lufs is not None:
            gain = max(-max_gain_db, min(max_gain_db, target_lufs - lufs))
        tracks.append({
            "path": path,
            "gain_db": round(gain, 2),
            "lufs": lufs,
            "bpm": fp.get("head", {}).get("bpm"),
            "intro_class": fp.get("intro_class"),
            "outro_class": fp.get("outro_class"),
            "duration": fp.get("duration"),
        })

    junctions = []
    for i in range(len(tracks) - 1):
        outro, intro = tracks[i]["outro_class"], tracks[i + 1]["intro_class"]
        mode, duration, curve = taxonomy.decide(outro, intro)
        junc = {
            "from": i,
            "to": i + 1,
            "mode": mode,
            "duration": duration,
            "curve": curve,
            "reason": f"{outro} -> {intro}",
        }
        fp = fingerprints[i]
        end = fp.get("end") or {}
        tail = fp.get("tail") or {}

        # A fading ending needs the overlap to span the fade, or the crossfade
        # starts after the outgoing has already gone quiet (a hole in the level).
        if junc["mode"] in (taxonomy.MODE_XFADE, taxonomy.MODE_FADE_UNDER):
            span = float(tail.get("fade_span") or end.get("fade_span") or 0.0)
            if end.get("fade") and span > junc["duration"]:
                junc["duration"] = round(min(max(span, 2.0), 16.0), 2)
                junc["reason"] = junc["reason"] + " | fade-aware overlap"

        # Splash / noise-FX endings: end the outgoing before the splash rather
        # than blending a cymbal crash into the next track - it does not belong
        # in the mix. `noise_tail` is the seconds of trailing non-tonal audio.
        noise_tail = float(end.get("noise_tail") or 0.0)
        if "trim_out" not in junc and noise_tail >= 1.0:
            junc["trim_out"] = round(noise_tail, 2)
            junc["reason"] = junc["reason"] + f" | trimmed {noise_tail:.1f}s splash tail"

        # Trailing silence: a track whose own fade dies out before the file ends
        # leaves dead air at the end. An overlap anchored to the file end then
        # sits entirely inside that silence, so nothing audible ever crossfades
        # and the junction is heard as "no mix at all". Anchor to the end of the
        # audio instead by trimming the dead tail.
        # Only worth doing when the dead air is a meaningful share of the
        # overlap; a second or so of near-silence under a long fade is fine and
        # trimming it would shift junctions that already mix well.
        trail = float(end.get("trail_silence") or 0.0)
        if ("trim_out" not in junc and trail >= 1.0
                and trail >= 0.35 * float(junc["duration"])):
            junc["trim_out"] = round(trail, 2)
            junc["reason"] = junc["reason"] + f" | trimmed {trail:.1f}s trailing silence"

        # NOTE: `trim_in` (enter on the kick) is deliberately NOT auto-applied.
        # A detector based on a level rise fires on ordinary arrangement lifts
        # (30s on one track, 31s on another), which would silently cut intros.
        # It is a per-junction plan field: set it where the ear says the intro
        # should be skipped. `kick_entry` in the fingerprint is a hint only.

        # Tempo match: warp the INCOMING track to the outgoing tempo so the two
        # beat grids stay locked through the fade, not just phase-aligned at its
        # start. The outgoing is already playing, so only the incoming can move.
        factor = 1.0
        if tempo_match and junc["mode"] == taxonomy.MODE_BEAT:
            ta = fp.get("tail_beat") or {}
            tb = fingerprints[i + 1].get("head_beat") or {}
            bo, bi = ta.get("bpm"), tb.get("bpm")
            if bo and bi and ta.get("strength", 0) >= 1.5 and tb.get("strength", 0) >= 1.5:
                f = bo / bi
                if 0.0 < abs(f - 1.0) <= max_warp:
                    factor = f
                    junc["tempo_factor"] = round(f, 5)
                    junc["warp"] = f"{bi} -> {bo} BPM"
                    junc["reason"] = junc["reason"] + f" | warped incoming {(f - 1) * 100:+.2f}%"

        # Beat alignment - AFTER the duration/trim/tempo are fixed, so the phase
        # reference is the EFFECTIVE outgoing end (and the warped incoming grid).
        if beat_align and junc["mode"] == taxonomy.MODE_BEAT:
            delay = beatgrid.mix_delay(fingerprints[i], fingerprints[i + 1],
                                       junc["duration"],
                                       out_trim=float(junc.get("trim_out") or 0.0),
                                       in_warp=factor,
                                       in_trim=float(junc.get("trim_in") or 0.0))
            if delay > 0.0:
                junc["delay"] = delay
                junc["align"] = "beat"

        # If a beat_mix could not be beat-matched, it is plain a crossfade -
        # say so, and fall back to a fade.
        if junc["mode"] == taxonomy.MODE_BEAT and not junc.get("align"):
            junc["mode"] = taxonomy.MODE_XFADE
            junc["fallback"] = "beat_mix unavailable"

        # Bass cut: sweep a high-pass up across the outgoing on a beat mix so its
        # kick clears out and the incoming bass takes over cleanly.
        if bass_cut_hz and junc["mode"] == taxonomy.MODE_BEAT:
            junc["bass_cut"] = int(bass_cut_hz)
            junc["reason"] = junc["reason"] + f" | bass cut to {bass_cut_hz}Hz"

        junctions.append(junc)

    return {
        "title": title or "automix",
        "target_lufs": target_lufs,
        "tracks": tracks,
        "junctions": junctions,
    }


def dump_plan(plan: dict, path: str | None = None) -> str:
    text = json.dumps(plan, indent=2)
    if path:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
    return text
