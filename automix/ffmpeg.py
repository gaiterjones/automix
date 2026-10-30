"""Thin wrappers around ffmpeg / ffprobe.

Everything the analyser needs comes from here: metadata, EBU R128 loudness,
silence detection, and raw PCM windows for our own (stdlib) DSP.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from array import array

# analysis sample rate - low on purpose, we only look at envelopes/onsets
DEFAULT_SR = 11025


class FFmpegError(RuntimeError):
    pass


def _tool(name: str) -> str:
    """Resolve an ffmpeg tool, honouring FFMPEG_BINARY / FFPROBE_BINARY."""
    override = os.environ.get(f"{name.upper()}_BINARY")
    if override:
        return override
    path = shutil.which(name)
    if not path:
        raise FFmpegError(f"{name} not found on PATH (install ffmpeg)")
    return path


def binary(name: str) -> str:
    """Public resolver for an ffmpeg tool name (see ``_tool``)."""
    return _tool(name)


def run(args: list[str], text: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=text)


def ffprobe_metadata(path: str) -> dict:
    p = subprocess.run(
        [_tool("ffprobe"), "-v", "error", "-print_format", "json",
         "-show_format", "-show_streams", path],
        capture_output=True, text=True,
    )
    if p.returncode != 0:
        raise FFmpegError(p.stderr.strip() or "ffprobe failed")
    data = json.loads(p.stdout or "{}")
    fmt = data.get("format") or {}
    stream = next((s for s in data.get("streams", [])
                   if s.get("codec_type") == "audio"), {})

    def num(x):
        try:
            return float(x)
        except (TypeError, ValueError):
            return None

    return {
        "duration": num(fmt.get("duration")),
        "bit_rate": num(fmt.get("bit_rate")),
        "format_name": fmt.get("format_name"),
        "codec": stream.get("codec_name"),
        "sample_rate": num(stream.get("sample_rate")),
        "channels": stream.get("channels"),
        "tags": fmt.get("tags") or {},
    }


def measure_loudness(path: str) -> dict:
    """EBU R128 integrated loudness, range and true peak (dB)."""
    p = subprocess.run(
        [_tool("ffmpeg"), "-hide_banner", "-nostats", "-i", path,
         "-filter_complex", "ebur128=peak=true", "-f", "null", "-"],
        capture_output=True, text=True,
    )
    err = p.stderr or ""

    def grab(pattern, text=err):
        # ebur128 emits a running figure while it works and the real summary at
        # the end - take the LAST match, not the first (the first is a -70 stub).
        hits = re.findall(pattern, text)
        return float(hits[-1]) if hits else None

    return {
        "integrated_lufs": grab(r"I:\s*(-?\d+(?:\.\d+)?)\s*LUFS"),
        "lra": grab(r"LRA:\s*(-?\d+(?:\.\d+)?)\s*LU"),
        "true_peak_db": grab(r"Peak:\s*(-?\d+(?:\.\d+)?)\s*dBFS"),
    }


def detect_silence(path: str, noise_db: int = -40, min_dur: float = 0.4) -> list[tuple]:
    p = subprocess.run(
        [_tool("ffmpeg"), "-hide_banner", "-nostats", "-i", path,
         "-af", f"silencedetect=noise={noise_db}dB:d={min_dur}", "-f", "null", "-"],
        capture_output=True, text=True,
    )
    out: list[tuple] = []
    start = None
    for line in (p.stderr or "").splitlines():
        m = re.search(r"silence_start:\s*(-?\d+(?:\.\d+)?)", line)
        if m:
            start = float(m.group(1))
        m = re.search(r"silence_end:\s*(-?\d+(?:\.\d+)?)", line)
        if m:
            out.append((start, float(m.group(1))))
            start = None
    if start is not None:  # silence runs to EOF
        m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", p.stderr or "")
        end = None
        if m:
            end = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
        out.append((start, end))
    return out


def decode_pcm(path: str, start: float | None = None,
               duration: float | None = None,
               sr: int = DEFAULT_SR, channels: int = 1) -> array:
    """Decode a window to mono s16le and return an array('h')."""
    cmd = [_tool("ffmpeg"), "-v", "error"]
    if start:
        cmd += ["-ss", f"{start:.3f}"]
    cmd += ["-i", path]
    if duration is not None:
        cmd += ["-t", f"{duration:.3f}"]
    cmd += ["-map", "a:0", "-ac", str(channels), "-ar", str(sr),
            "-f", "s16le", "-"]
    p = subprocess.run(cmd, capture_output=True)
    if p.returncode != 0:
        raise FFmpegError(p.stderr.decode(errors="replace")[:400] or "ffmpeg decode failed")
    raw = p.stdout
    a = array("h")
    a.frombytes(raw[: len(raw) // 2 * 2])
    return a


def transcoded_duration(path: str) -> float | None:
    """Duration via ffprobe (convenience)."""
    return ffprobe_metadata(path).get("duration")
