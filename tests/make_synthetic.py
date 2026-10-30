#!/usr/bin/env python3
"""Generate synthetic test tracks (ffmpeg lavfi) until real audio is available.

Tracks are a couple of minutes long so the 45s head and tail windows do not
overlap. Each one is designed to exercise a different head/tail class:

  01 beat      -> engineered fade out
  02 tone      -> abrupt stop
  03 spoken    -> then a beat
  04 ambient   -> long fade
  05 beat      -> runs to the end
"""
import os
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "audio")

# a sharp percussive click every 60/bpm seconds
KICK = "0.9*exp(-45*mod(t\\,{period}))*sin(2*PI*1000*t)"


def ff(args):
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args], check=True)


def beat(bpm, dur, sr=44100):
    return f"aevalsrc={KICK.format(period=60.0 / bpm)}:d={dur}:s={sr}:c=mono"


def main():
    os.makedirs(OUT, exist_ok=True)
    p = lambda n: os.path.join(OUT, n)

    # 01 - beat, engineered fade over the last 15s
    ff(["-f", "lavfi", "-i", beat(128, 150),
        "-af", "afade=t=out:st=135:d=15", "-b:a", "192k", p("01_beat_fadeout.mp3")])

    # 02 - sustained tone, stops abruptly
    ff(["-f", "lavfi", "-i", "sine=frequency=220:duration=120",
        "-af", "volume=0.5", "-b:a", "192k", p("02_tone_hardstop.mp3")])

    # 03 - 40s of pink noise (spoken-ish), then a beat
    ff(["-f", "lavfi", "-i", "anoisesrc=c=pink:d=40:s=44100:a=0.3",
        "-f", "lavfi", "-i", beat(120, 110),
        "-filter_complex", "[0][1]concat=n=2:v=0:a=1[a]", "-map", "[a]",
        "-b:a", "192k", p("03_spoken_then_beat.mp3")])

    # 04 - ambient drone, long fade at the end
    ff(["-f", "lavfi", "-i", "sine=frequency=110:duration=140",
        "-af", "tremolo=f=0.15:d=0.6,afade=t=out:st=120:d=20",
        "-b:a", "192k", p("04_ambient_fade.mp3")])

    # 05 - steady beat, runs to the end
    ff(["-f", "lavfi", "-i", beat(126, 140), "-b:a", "192k", p("05_beat_run.mp3")])

    print("wrote in", OUT)
    for n in sorted(os.listdir(OUT)):
        print("  ", n)


if __name__ == "__main__":
    main()
