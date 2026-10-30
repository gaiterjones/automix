# Contributing

Thanks for looking. This is a small, deliberately dependency-free tool; the
guiding rule is that **the decision table is the product** — anything that makes
transitions easier to reason about and tune is welcome.

## Ground rules

- **No third-party Python packages.** Analysis stays ffmpeg + the standard
  library so the tool drops into a minimal container. ffmpeg itself is invoked
  as an external binary.
- **Keep the layers separate.** `analysis` describes tracks, `plan` decides,
  `render` executes. The plan JSON is the seam — render should never need to
  know how a decision was made.
- **Explainable over clever.** Prefer a readable rule or a named threshold to a
  fit you can't see.

## Dev setup

```bash
git clone https://github.com/gaiterjones/automix && cd automix
python3 -m venv .venv && . .venv/bin/activate
pip install -e .
automix check   # not implemented yet - just ensure ffmpeg is on PATH
```

ffmpeg must be on `PATH` for the end-to-end tests. Everything else runs on the
standard library.

## Testing

```bash
python3 -m unittest discover -s tests -v   # unit tests (no ffmpeg needed)
bash tests/smoke.sh                        # end-to-end on synthetic tracks
```

`tests/smoke.sh` generates ffmpeg-lavfi test tracks, analyses them, builds a
plan and renders a mix — it should pass on any machine with ffmpeg. CI runs
both.

## Tuning transitions

The thresholds live as named constants at the top of `automix/analysis.py`
(`T_STRENGTH`, `T_ZCR`, …). The decision table is
`automix/taxonomy.py::decide()`. If you tune either against your own material,
say so in the PR — the current values are v1 heuristics from a single reference
set.

## Pull requests

- One logical change per PR; describe the *material* you tested on.
- Update `docs/` and `CHANGELOG.md` when behaviour changes.
- Don't commit audio. `tests/audio/`, `input/` and `out/` are git-ignored.
