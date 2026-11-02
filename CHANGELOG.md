# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/); this project
aims to follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- Per-junction **`trim_out`** (seconds): trims the outgoing stream before the
  crossfade so the incoming track comes in earlier. It is an optional field in
  the plan JSON and is applied by `render` with `atrim`.
- **`trim_in` (plan field)**: skip N seconds of the incoming track's head so a
  beatless intro can be bypassed and the mix enters where the kick starts. The
  beat alignment then uses the incoming's **body** grid (where the kick is)
  rather than the head grid. Deliberately not auto-detected: a level-rise
  detector fired on ordinary arrangement lifts. `kick_entry` is exposed in the
  fingerprint as a hint.
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

- **`filter_in` (plan field)**: the incoming track enters thin — high-passed at
  N Hz — and opens downward to full bandwidth across the fade. A low-pass that
  opens upward was tried first and scooped the level by ~10 dB, because it left
  the incoming with only its lows while the mids and highs were missing; a
  descending high-pass keeps the body of the track present and lets the bass
  arrive last.
- **Trailing-silence trimming**: when a track's own fade dies out before its
  file ends, the planner trims the dead tail so the overlap anchors to the end
  of the audio. Gated to trailing silence ≥ 1 s **and** ≥ 35 % of the overlap,
  so it only fires where the dead air actually swallows the fade.

### Fixed
- **A short fade no longer outranks a beat run.** A beat that runs at full level
  and then decays over a second or two into the end of the file was classified
  `fade_out`; the fade-aware overlap then sized the blend from that short fade,
  so the junction landed inside the decay and was heard as *no mix at all*.
  Measured on a live set: a track at −8 dBFS with `end.tempo_strength` 4.46 and
  a 2.14 s fade got a **2.16 s** overlap into a track that opens on a solid beat.
  Endings now classify as `beat_run` when the fade is shorter than `FADE_TAIL`
  (3 s) *and* the ending is rhythmic; genuine 5–8 s fades are unaffected.
- **A `beat_run` hand-over gets a minimum 4 s overlap** (`MIN_BEAT_OVERLAP`, two
  bars at 120 BPM), whatever the table returns. Two seconds of two tracks is a
  butt-join, not a blend.
- **Bass-cut junctions collapsed into a hard cut.** The branch trimmed both
  sides to exactly the fade length and crossfaded the stubs; decoded audio is a
  fraction of a second shorter than nominal, so `acrossfade` could not fit and
  silently emitted a near-empty segment — the junction became a cut that also
  dropped the outgoing's last `duration` seconds (measured: 11.00 s short on one
  pair). The sweep is now applied to the outgoing's last `duration` seconds and
  the full streams are crossfaded directly.
- **`mode` was not authoritative over `bass_cut`.** The bass-cut branch was
  tested before the mode switch, so a `fade_under` junction carrying a bass cut
  rendered as a crossfade — two different plans produced byte-identical output.
- **`estimate_tempo` raised `ZeroDivisionError`** on windows too short for the
  longest autocorrelation lag. Lags are now clamped to what the data supports.
- **`plan_duration` over-reported** for plans with a bass cut, because of the
  first bug above; it now agrees with the rendered length.

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
