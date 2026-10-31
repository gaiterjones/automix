"""Execute a mix plan with ffmpeg.

Everything goes through ONE ``-filter_complex`` graph: each input is forced to a
common format (fltp/44.1k/stereo) and gain-matched, then the tracks are folded
together in order with ``acrossfade``. A single graph decodes each input once
and writes no intermediate files - important once a mix is a dozen tracks long
(the earlier pairwise version rewrote the growing mix on every junction).

A hard "cut" is just a very short crossfade (20ms), which is click-free.
"""
from __future__ import annotations

import os
import subprocess
import tempfile

from .ffmpeg import binary as _binary


class RenderError(RuntimeError):
    pass


def _ff(args: list[str]) -> None:
    p = subprocess.run(args, capture_output=True, text=True)
    if p.returncode != 0:
        raise RenderError((p.stderr or "ffmpeg failed").strip()[-1000:])


def _build_graph(plan: dict, sr: int, channels: int) -> tuple[str, str]:
    ch = "stereo" if channels == 2 else "mono"

    # per-input delay (beat alignment) and tempo warp (atempo), both applied to
    # the INCOMING side of a beat_mix junction
    delays: dict[int, float] = {}
    warps: dict[int, float] = {}
    for junc in plan.get("junctions") or []:
        if junc.get("delay"):
            delays[junc["to"]] = float(junc["delay"])
        if junc.get("tempo_factor"):
            warps[junc["to"]] = float(junc["tempo_factor"])

    parts, labels = [], []
    for i, t in enumerate(plan["tracks"]):
        gain = float(t.get("gain_db", 0.0))
        chain = (f"aformat=sample_fmts=fltp:sample_rates={sr}:channel_layouts={ch},"
                 f"volume={gain}dB")
        if i in warps:
            chain += f",atempo={warps[i]:.6f}"
        if i in delays:
            chain += f",adelay={int(round(delays[i] * 1000))}:all=1"
        parts.append(f"[{i}]{chain}[a{i}]")
        labels.append(f"a{i}")

    # warping compresses a track's timeline by the factor, so later junction
    # positions must use the effective length
    lengths = [float(t.get("duration") or 0.0) / warps.get(i, 1.0)
               for i, t in enumerate(plan["tracks"])]
    cur = labels[0]
    cur_len = lengths[0] if lengths else 0.0
    for j, junc in enumerate(plan.get("junctions") or []):
        nxt = labels[junc["to"]]
        dur = max(0.02, float(junc.get("duration", 6.0)))
        curve = junc.get("curve", "tri")

        # optional manual nudge: bring the incoming track in earlier by trimming
        # the outgoing stream (and everything mixed so far) by `trim_out` seconds
        trim = float(junc.get("trim_out") or 0.0)
        if trim > 0.0 and cur_len > trim + 0.1:
            trimmed = f"t{j}"
            parts.append(f"[{cur}]atrim=0:{cur_len - trim:.3f},asetpts=PTS-STARTPTS[{trimmed}]")
            cur, cur_len = trimmed, cur_len - trim

        out = f"m{j}"
        nxt_len = lengths[junc["to"]] if junc["to"] < len(lengths) else 0.0
        mode = junc.get("mode", "xfade")

        bass_cut = int(junc.get("bass_cut") or 0)
        if bass_cut and nxt_len > dur and cur_len > dur:
            # classic DJ move: sweep a high-pass up across the outgoing's tail so
            # its kick/bass clears out and the incoming bass takes over cleanly.
            a, b = f"aA{j}", f"aB{j}"
            n1, n2 = f"n1{j}", f"n2{j}"
            parts.append(f"[{cur}]asplit=2[{a}][{b}]")
            parts.append(f"[{a}]atrim=0:{cur_len - dur:.3f},asetpts=PTS-STARTPTS[p{j}]")
            # highpass takes no time expression, so sweep it with staged
            # commands (a single command at t=dur lands on the last sample and
            # never sweeps). Reach the target just before the end.
            nsteps = 30
            cmds = ";".join(
                f"{dur * i / nsteps:.3f} highpass@bc{j} f "
                f"{int(round(20 + (bass_cut - 20) * i / (nsteps - 1)))}"
                for i in range(nsteps)
            )
            parts.append(f"[{b}]atrim=start={cur_len - dur:.3f},asetpts=PTS-STARTPTS,"
                         f"asendcmd=c='{cmds}',highpass@bc{j}=f=20[t{j}]")
            parts.append(f"[{nxt}]asplit=2[{n1}][{n2}]")
            parts.append(f"[{n1}]atrim=0:{dur:.3f},asetpts=PTS-STARTPTS[bh{j}]")
            parts.append(f"[{n2}]atrim=start={dur:.3f},asetpts=PTS-STARTPTS[br{j}]")
            parts.append(f"[t{j}][bh{j}]acrossfade=d={dur:.3f}:c1={curve}:c2={curve}[mm{j}]")
            parts.append(f"[p{j}][mm{j}][br{j}]concat=n=3:v=0:a=1[{out}]")
        elif mode == "fade_under" and nxt_len > dur and cur_len > dur:
            # prefix + (outgoing faded out UNDER the incoming at full level) + rest
            a, b = f"aA{j}", f"aB{j}"
            n1, n2 = f"n1{j}", f"n2{j}"
            fade_in = min(0.3, dur)
            # Keep the outgoing at FULL level for most of the overlap so both
            # tracks are genuinely audible together, then hand over in a short
            # fade at the end. Fading it across the whole overlap makes the
            # outgoing vanish immediately, which reads as "no mix at all".
            fade_out = min(max(dur * 0.25, 1.5), 4.0)
            fade_out_start = max(0.0, dur - fade_out)
            parts.append(f"[{cur}]asplit=2[{a}][{b}]")
            parts.append(f"[{a}]atrim=0:{cur_len - dur:.3f},asetpts=PTS-STARTPTS[p{j}]")
            parts.append(f"[{b}]atrim=start={cur_len - dur:.3f},asetpts=PTS-STARTPTS,"
                         f"afade=t=out:st={fade_out_start:.3f}:d={fade_out:.3f}[t{j}]")
            parts.append(f"[{nxt}]asplit=2[{n1}][{n2}]")
            parts.append(f"[{n1}]atrim=0:{dur:.3f},asetpts=PTS-STARTPTS,"
                         f"afade=t=in:st=0:d={fade_in:.3f}[bh{j}]")
            parts.append(f"[{n2}]atrim=start={dur:.3f},asetpts=PTS-STARTPTS[br{j}]")
            parts.append(f"[t{j}][bh{j}]amix=inputs=2:duration=longest:normalize=0,"
                         f"alimiter=limit=0.95[mm{j}]")
            parts.append(f"[p{j}][mm{j}][br{j}]concat=n=3:v=0:a=1[{out}]")
        else:
            parts.append(f"[{cur}][{nxt}]acrossfade=d={dur:.3f}:c1={curve}:c2={curve}[{out}]")
        cur = out
        cur_len += nxt_len - dur

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


def junction_windows(plan: dict, pre: float = 6.0, post: float = 8.0) -> list[tuple]:
    """(start, end) on the OUTPUT timeline around each junction.

    Mirrors _build_graph's length bookkeeping: trims shorten the outgoing,
    warps shorten a track's timeline, and each junction removes `duration`
    seconds of overlap.
    """
    warps = {j["to"]: float(j["tempo_factor"])
             for j in plan.get("junctions") or [] if j.get("tempo_factor")}
    lens = [float(t.get("duration") or 0.0) / warps.get(i, 1.0)
            for i, t in enumerate(plan.get("tracks") or [])]
    if not lens:
        return []
    cur, out = lens[0], []
    for j in plan.get("junctions") or []:
        d = float(j.get("duration", 0.0))
        cur -= float(j.get("trim_out") or 0.0)
        start = cur - d
        out.append((max(0.0, start - pre), start + d + post))
        cur += (lens[j["to"]] if j["to"] < len(lens) else 0.0) - d
    return out


def render_preview(plan: dict, out_path: str, pre: float = 6.0, post: float = 8.0,
                   gap: float = 0.6, bitrate: str = "320k", sr: int = 44100) -> str:
    """Render ONLY the junctions, concatenated with short gaps, for auditioning.

    The full mix is rendered once to a lossless temp file, then each junction
    window is cut and the pieces are concatenated. For a 19-minute mix this
    yields a ~90-second preview.
    """
    ff = _binary("ffmpeg")
    windows = junction_windows(plan, pre, post)
    if not windows:
        raise RenderError("plan has no junctions")

    tmp = tempfile.mkdtemp(prefix="automix-preview-")
    mix = os.path.join(tmp, "mix.wav")
    render(plan, mix, sr=sr)

    silence = os.path.join(tmp, "gap.wav")
    _ff([ff, "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
         "-i", f"anullsrc=r={sr}:cl=stereo", "-t", f"{max(0.0, gap):.3f}",
         "-c:a", "pcm_s16le", silence])

    segments = []
    for i, (start, end) in enumerate(windows):
        seg = os.path.join(tmp, f"seg{i:02d}.wav")
        _ff([ff, "-y", "-hide_banner", "-loglevel", "error",
             "-ss", f"{start:.3f}", "-t", f"{max(0.05, end - start):.3f}",
             "-i", mix, "-c:a", "pcm_s16le", seg])
        segments.append(seg)

    listing = os.path.join(tmp, "list.txt")
    with open(listing, "w", encoding="utf-8") as fh:
        for i, seg in enumerate(segments):
            fh.write(f"file '{seg}'\n")
            if i < len(segments) - 1 and gap > 0:
                fh.write(f"file '{silence}'\n")

    _ff([ff, "-y", "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0",
         "-i", listing, "-c:a", "libmp3lame", "-b:a", bitrate, out_path])
    return out_path


def plan_duration(plan: dict) -> float:
    """Expected output length: sum(track durations) - sum(overlaps)."""
    total = sum(float(t.get("duration") or 0.0) for t in plan.get("tracks") or [])
    overlap = sum(float(j.get("duration") or 0.0) for j in plan.get("junctions") or [])
    return round(total - overlap, 2)
