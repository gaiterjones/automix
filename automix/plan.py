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
               beat_align: bool = False) -> dict:
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
        # beat alignment: nudge the incoming track so its beat lands on the
        # outgoing track's beat through the crossfade.
        if beat_align and mode == taxonomy.MODE_BEAT:
            delay = beatgrid.mix_delay(fingerprints[i], fingerprints[i + 1], duration)
            if delay > 0.0:
                junc["delay"] = delay
                junc["align"] = "beat"

        # If a beat_mix could not be beat-matched, it is plain a crossfade -
        # say so, and fall back to a fade.
        if junc["mode"] == taxonomy.MODE_BEAT and not junc.get("align"):
            junc["mode"] = taxonomy.MODE_XFADE
            junc["fallback"] = "beat_mix unavailable"

        # A fading ending needs the overlap to span the fade, or the crossfade
        # starts after the outgoing has already gone quiet (a hole in the level).
        if junc["mode"] in (taxonomy.MODE_XFADE, taxonomy.MODE_FADE_UNDER):
            fp = fingerprints[i]
            end = fp.get("end") or {}
            tail = fp.get("tail") or {}
            span = float(tail.get("fade_span") or end.get("fade_span") or 0.0)
            if end.get("fade") and span > duration:
                junc["duration"] = round(min(max(span, 2.0), 16.0), 2)
                junc["reason"] = junc["reason"] + " | fade-aware overlap"
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
