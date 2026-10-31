# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/); this project
aims to follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- Per-junction **`trim_out`** (seconds): trims the outgoing stream before the
  crossfade so the incoming track comes in earlier. It is an optional field in
  the plan JSON and is applied by `render` with `atrim`.

### Changed
- **Fade detection** now uses a longer (20 s) window and a start-vs-end level
  drop rather than an almost-monotonic curve, so long fades are caught. A
  synth-arp fade-out that previously read as `beat_run` is now `fade_out`.
- A `beat_mix` junction that cannot be beat-matched now falls back to `xfade`
  (the plan records `fallback: "beat_mix unavailable"`) instead of implying a
  beat mix it did not perform.
- **Fade-aware overlap:** a fading ending now gets a crossfade that spans the
  detected fade, so the fade no longer starts after the outgoing has gone quiet
  (which left a ~20 dB hole in the level at the junction).

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
