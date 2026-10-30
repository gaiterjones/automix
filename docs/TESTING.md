# Testing

There are three layers: unit tests (no ffmpeg), a synthetic end-to-end smoke
test, and testing on your own material.

## Unit tests

```bash
python3 -m unittest discover -s tests -v
```

Standard library only — no ffmpeg needed, so they run anywhere. They cover:

- **tempo** — a click train reads rhythmic with a plausible BPM; a flat envelope
  returns no tempo;
- **envelope features** — zero-crossing rate, silence edges, fade detection,
  abrupt-end detection;
- **the decision table** — a few `taxonomy.decide()` cases;
- **the render graph** — that a `beat_mix` junction with a `delay` emits
  `adelay`/`acrossfade` in the ffmpeg graph, and one without does not.

## Synthetic end-to-end

```bash
bash tests/smoke.sh
```

This generates five lavfi tracks with `tests/make_synthetic.py`, analyses them,
builds a plan, renders a mix, and asserts the plan has 4 junctions and the mix
file is non-trivial. It needs ffmpeg on `PATH`.

| generated track | exercises |
|---|---|
| `01_beat_fadeout` | beat opening, engineered fade-out |
| `02_tone_hardstop` | sustained/ambient opening, abrupt stop |
| `03_spoken_then_beat` | noisy/spoken intro, then a beat |
| `04_ambient_fade` | ambient drone, long fade |
| `05_beat_run` | steady beat running to the end |

## CI

`.github/workflows/ci.yml` runs, on Python 3.10 and 3.12:

1. byte-compile the package,
2. the unit tests,
3. the synthetic smoke test.

## Testing on real material

```bash
python3 -m automix analyze album/*.mp3 -o fingerprints.json   # check tempo/classes
python3 -m automix plan    album/*.mp3 -o mix.plan.json       # check the decisions
python3 -m automix mix     album/*.mp3 -o out/mix.mp3         # listen
```

When a junction sounds wrong, the fix is almost always one of two places: a
threshold in `automix/analysis.py`, or a rule in `automix/taxonomy.py::decide`.
Change it, re-plan (cheap — no render), and listen to the single junction rather
than the whole mix. See [CASE-STUDY.md](CASE-STUDY.md) for how that loop went on
a real album.
