# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/); this project
aims to follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.0] — 2026-10-30

Initial release.

### Added
- `analyse -> classify -> decide -> render` pipeline.
- `analysis.py` — per-track fingerprinting of a 30 s head, 30 s tail and ~12 s
  ending window, plus a mid-track tempo window; head/tail classification.
- `taxonomy.py` — the intro/outro vocabulary and the editable transition
  decision table (`decide()`).
- `dsp.py` — dependency-free RMS envelope, onset envelope, harmonic-weighted
  autocorrelation tempo (with log-normal prior), zero-crossing rate, silence
  edges, fade and abrupt-end detection.
- `beatgrid.py` — beat-grid detection (period, phase, 4/4 downbeat) and an
  optional beat-alignment nudge (`--beat-align`, off by default).
- `plan.py` — fingerprints to a plain-JSON mix plan (the editable artefact).
- `render.py` — mix plan to audio via a single ffmpeg `filter_complex` graph,
  with per-track EBU R128 loudness matching.
- `cli.py` — `analyze`, `plan` and `mix` subcommands.
- Synthetic test-track generator (`tests/make_synthetic.py`) and unit tests.

### Known limitations
- Tempo detection can lock onto a sub-harmonic on strongly 2:1 / 3:2 material
  (10/12 on the reference set).
- `beat_mix` renders as a plain equal-power crossfade (no tempo matching).
- Beat alignment is off by default and its `adelay` nudge pads with silence.

[Unreleased]: https://github.com/gaiterjones/automix/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/gaiterjones/automix/releases/tag/v0.1.0
