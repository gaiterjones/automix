# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/); this project
aims to follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- Per-junction **`trim_out`** (seconds): trims the outgoing stream before the
  crossfade so the incoming track comes in earlier. It is an optional field in
  the plan JSON and is applied by `render` with `atrim`.
- **`preview` subcommand**: renders only the junctions — `--pre`/`--post`
  seconds either side of each blend, joined by short gaps — so transitions can
  be auditioned without listening to the whole mix.
- **Bass cut** (`--bass-cut HZ`): on a `beat_mix` junction, sweep a high-pass up
  across the outgoing track so its kick/bass clears out and the incoming bass
  takes over cleanly — the classic DJ filter move. Implemented as staged
  `highpass` commands driven by `asendcmd` (highpass has no time expression);
  the plan records `bass_cut`.
- **Tempo matching** (`--tempo-match`): on a `beat_mix` junction the incoming
  track is warped (`atempo`, pitch preserved) to the outgoing tempo, gated on
  |ΔBPM| ≤ 5% and tempo confidence. The plan records `tempo_factor`; render
  applies it. With both grids locked the phase nudge no longer drifts through
  the fade (previously ~39 ms over an 8 s fade at 1% difference).
- **Splash / noise-FX ending detection** (`noise_tail`): a track that ends on a
  cymbal crash or noise FX — a trailing run of high zero-crossing-rate audio —
  has that tail trimmed, and its outro is judged on the music *before* the
  splash. The planner sets `trim_out` so the mix is faded out before the crash.
  (A cymbal reads 0.4–0.7 ZCR; tonal material, even a bright arp fade, stays
  under ~0.25.) On the arpnotic set this trims 6.5 s from track 5 and 3.8 s from
  track 2, and 5→6 now genuinely beat-matches.

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
- **Tempo accuracy:** estimation now uses a dedicated finer hop (192 samples,
  ~17 ms) and parabolic interpolation around the autocorrelation peak. On clean
  beat-only material a 127 BPM click track now reads 127.4 (was 129.2); real
  album readings shift by ~1%, within the estimator's noise floor.
- **`fade_under` transition** for fading endings: the incoming plays at full
  level while the outgoing fades out beneath it, instead of an equal-power
  crossfade that fades both sides (which scooped the level by 14–20 dB at real
  fade→quiet junctions).

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
