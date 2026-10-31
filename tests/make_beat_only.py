#!/usr/bin/env python3
"""Generate beat-only fixtures for testing beat alignment (ffmpeg lavfi).

Three click tracks (a sharp kick every beat), mono 44.1k:

  beatA_123.mp3       123 BPM, phase 0
  beatB_123_phase.mp3 123 BPM, phase +0.25 s  (deliberately out of lock with A)
  beatC_127.mp3       127 BPM               (a ~3.2% tempo difference to A)

A and B share a tempo so the aligner CAN engage; A and C do not, which
exercises the drift gate.
"""
import os
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "audio-beat")

# a sharp click once per period, optionally delayed by `off` seconds.
# t+period-off keeps the mod() argument positive (ffmpeg mod follows the sign
# of the operand), so a negative offset cannot explode the envelope.
KICK = "0.9*exp(-45*mod(t+{period}-{off}\\,{period}))*sin(2*PI*1000*t)"


def ff(args):
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args], check=True)


def kick_track(bpm, dur, off=0.0, sr=44100):
    period = 60.0 / bpm
    return f"aevalsrc={KICK.format(period=period, off=off)}:d={dur}:s={sr}:c=mono"


def main():
    os.makedirs(OUT, exist_ok=True)
    p = lambda n: os.path.join(OUT, n)
    ff(["-f", "lavfi", "-i", kick_track(123, 60, 0.0), "-b:a", "192k", p("beatA_123.mp3")])
    ff(["-f", "lavfi", "-i", kick_track(123, 60, 0.25), "-b:a", "192k", p("beatB_123_phase.mp3")])
    ff(["-f", "lavfi", "-i", kick_track(127, 60, 0.0), "-b:a", "192k", p("beatC_127.mp3")])
    print("wrote in", OUT)
    for n in sorted(os.listdir(OUT)):
        print("  ", n)


if __name__ == "__main__":
    main()
