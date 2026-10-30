# Roadmap

Ordered roughly by value-per-effort. Nothing here is a promise.

## Near term

- **Make `beat_mix` mean something.** Two gaps, both documented in
  [TRANSITIONS.md](TRANSITIONS.md#beat-alignment):
  1. the alignment nudge uses `adelay` and therefore prepends silence — replace
     it with a silence-free shift (trim the outgoing tail by up to a beat, or
     shift the crossfade start);
  2. add **tempo matching** (`rubberband`/`atempo`) so two tracks at different
     BPMs can be locked at all. Beat alignment is useless without it on pairs
     that differ.

  Only once both exist does beat mixing beat a plain crossfade in general.

## Medium term

- **Key / chroma awareness.** Detect key (Krumhansl profiles over an FFT) and
  avoid harmonic clashes — prefer transition types that hide a key change
  (drum-only breakdowns) when two tracks are incompatible. A natural fit for
  techno/house where key is often deliberate.
- **Better tempo.** A DFT tempogram (or a proper comb/onset model) to remove the
  remaining sub-harmonic errors; the current estimator is plain
  autocorrelation + heuristics.
- **More transition types.** EQ sweeps, filter "ring-under" (low-pass the
  outgoing under a spoken intro), reverb/delay tails, and a downbeat bass-swap.

## Later

- **Planner as a pluggable step.** The plan JSON already separates decisions
  from rendering. Add an optional LLM planner that takes the fingerprint JSON
  (and any constraints — target length, "tell a story", ordering) and returns the
  `junctions` list. The renderer does not change.
- **Web / API surface.** The natural next home is a small service: upload N
  tracks, get a mix + share page. That is a *product* effort (multi-upload,
  async job/queue, ffmpeg CPU budgeting, cache + cleanup), not an engine one —
  the engine is done. A dedicated host (e.g. a `mix.*` subdomain with its own
  container) keeps it independent of any PHP app that calls it.

## Explicitly out of scope for now

- **End-to-end neural audio mixing.** Data-hungry, non-deterministic, and worse
  than a good rule table at this scale. If a model is used at all, it should be
  the *planner* (choosing transitions), not the generator.
