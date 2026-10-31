# Demo — one beat-matched transition, start to finish

`transition.mp3` is a 27 s excerpt around a single junction (tracks 5 → 6 of a
real sequence): ~8 s of the outgoing track, the 11 s blend, ~8 s of the
incoming track.

It is the output of every feature working together on one junction:

| setting | value |
|---|---|
| mode | `beat_mix` |
| crossfade | **11 s** (equal-power) |
| tempo warp | **×1.0098** — incoming 122.4 → outgoing 123.6 BPM (`atempo`, pitch preserved) |
| phase alignment | **316 ms** nudge so the kicks coincide |
| splash trim | **6.5 s** — the outgoing track ends on a cymbal crash; it is faded out before it |
| bass cut | **350 Hz** — a high-pass sweeps up across the outgoing so its kick clears out and the incoming bass takes over |
| loudness | each track matched to −14 LUFS before mixing |

The exact recipe is in `transition.plan.json`:

```jsonc
{
  "from": 4, "to": 5,
  "mode": "beat_mix",
  "duration": 11.0,
  "trim_out": 6.5,
  "tempo_factor": 1.0098,
  "bass_cut": 350,
  "delay": 0.316,
  "align": "beat"
}
```

## Reproducing it

The source tracks are not part of this repository (they are the author's own
unreleased material, included here as a demo with permission). To reproduce a
similar transition you need the two tracks, then:

```bash
python3 -m automix mix track5.mp3 track6.mp3 -o out/transition.mp3 \
    --beat-align --tempo-match --bass-cut 350 --plan-out out/transition.plan.json
```

then lengthen that junction to 11 s by editing `duration` in the plan and
re-rendering with `automix.render.render(plan, out)` — the phase nudge must be
recomputed for the new overlap (the plan field is a hint; `beatgrid.mix_delay`
with the new duration gives the value).

## Credit

Audio © gaiterjones, included with permission as a demo of the tool.
