"""Execute a mix plan with ffmpeg.

Everything goes through ONE ``-filter_complex`` graph: each input is forced to a
common format (fltp/44.1k/stereo) and gain-matched, then the tracks are folded
together in order with ``acrossfade``. A single graph decodes each input once
and writes no intermediate files - important once a mix is a dozen tracks long
(the earlier pairwise version rewrote the growing mix on every junction).

A hard "cut" is just a very short crossfade (20ms), which is click-free.
"""
from __future__ import annotations

import subprocess

from .ffmpeg import binary as _binary


class RenderError(RuntimeError):
    pass


def _ff(args: list[str]) -> None:
    p = subprocess.run(args, capture_output=True, text=True)
    if p.returncode != 0:
        raise RenderError((p.stderr or "ffmpeg failed").strip()[-1000:])


def _build_graph(plan: dict, sr: int, channels: int) -> tuple[str, str]:
    ch = "stereo" if channels == 2 else "mono"

    # per-input delay (beat alignment): the incoming side of a beat_mix junction
    delays: dict[int, float] = {}
    for junc in plan.get("junctions") or []:
        if junc.get("delay"):
            delays[junc["to"]] = float(junc["delay"])

    parts, labels = [], []
    for i, t in enumerate(plan["tracks"]):
        gain = float(t.get("gain_db", 0.0))
        chain = (f"aformat=sample_fmts=fltp:sample_rates={sr}:channel_layouts={ch},"
                 f"volume={gain}dB")
        if i in delays:
            chain += f",adelay={int(round(delays[i] * 1000))}:all=1"
        parts.append(f"[{i}]{chain}[a{i}]")
        labels.append(f"a{i}")

    cur = labels[0]
    for j, junc in enumerate(plan.get("junctions") or []):
        nxt = labels[junc["to"]]
        dur = max(0.02, float(junc.get("duration", 6.0)))
        curve = junc.get("curve", "tri")
        out = f"m{j}"
        parts.append(f"[{cur}][{nxt}]acrossfade=d={dur:.3f}:c1={curve}:c2={curve}[{out}]")
        cur = out

    return ";".join(parts), cur


def render(plan: dict, out_path: str, sr: int = 44100, channels: int = 2,
           bitrate: str = "320k") -> str:
    ffmpeg = _binary("ffmpeg")
    tracks = plan.get("tracks") or []
    if not tracks:
        raise RenderError("plan has no tracks")

    graph, out_label = _build_graph(plan, sr, channels)

    args = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error"]
    for t in tracks:
        args += ["-i", t["path"]]
    args += ["-filter_complex", graph, "-map", f"[{out_label}]"]

    codec = {
        ".mp3": ["-c:a", "libmp3lame", "-b:a", bitrate],
        ".m4a": ["-c:a", "aac", "-b:a", bitrate],
        ".wav": ["-c:a", "pcm_s16le"],
        ".flac": ["-c:a", "flac"],
    }.get(_ext(out_path), ["-c:a", "libmp3lame", "-b:a", bitrate])

    _ff(args + codec + [out_path])
    return out_path


def _ext(path: str) -> str:
    import os
    return os.path.splitext(path)[1].lower()


def plan_duration(plan: dict) -> float:
    """Expected output length: sum(track durations) - sum(overlaps)."""
    total = sum(float(t.get("duration") or 0.0) for t in plan.get("tracks") or [])
    overlap = sum(float(j.get("duration") or 0.0) for j in plan.get("junctions") or [])
    return round(total - overlap, 2)
