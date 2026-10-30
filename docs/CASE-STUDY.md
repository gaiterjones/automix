# Case study — a real 12-track sequence

A real listening sequence (12 tracks, ~2:51–3:00 each, all MP3 192 kbps / 44.1
kHz stereo) was mixed end to end. The tracks are not included; this records the
findings so the heuristics have a known reference point.

## The mix

- 12 tracks in order (including a deliberate half-time hidden outro).
- Output ≈ **33:24**, loudness-matched to −14 LUFS, 320 kbps.
- The junction plan:

| junction | transition | reason |
|---|---|---|
| 1→2 | xfade 2 s | fade_out → beat_from_start |
| 2→3 | beat_mix 8 s | beat_run → beat_from_start |
| 3→4 | beat_mix 8 s | beat_run → beat_from_start |
| 4→5 | xfade 2 s | fade_out → beat_from_start |
| 5→6 | xfade 12 s (log) | breakdown → beat_from_start |
| 6→7 | xfade 2 s | fade_out → silent_lead |
| 7→8 | xfade 12 s (log) | breakdown → beat_from_start |
| 8→9 | beat_mix 8 s | beat_run → beat_from_start |
| 9→10 | xfade 2 s | fade_out → beat_from_start |
| 10→11 | xfade 12 s (log) | breakdown → beat_from_start |
| 11→12 | beat_mix 8 s | beat_run → beat_from_start |

The listener's verdict on the plain mix: *"couldn't fault it."* That is the
harness this tool was validated against.

## What worked

- **Loudness matching** — no track jumped out; the sequence is consistently loud.
- **Fade handling** — tracks that end on an engineered fade got the next one
  slid in early; dead stops got cuts.
- **Dead tails / breakdowns** — one track ends on a long near-silent tail; the
  quiet-ending guard classified it `breakdown`, and the junction became a long
  gentle overlap rather than a smear into a stopped track.
- **Transition variety** — the plan used 2 s, 8 s and 12 s crossfades and a
  plain pattern of choices; it was not one blanket crossfade.

## What to know

- **Tempo: 10 of 12 matched** the sequence's own measured BPM (129, 117 and a
  61.5 half-time outro all correct). Two tracks read a **sub-harmonic** (80.7
  and 63 for material at 123) — a genuine 3:2 / 2:1 ambiguity in onset
  autocorrelation, not a mis-timed track. Rythmic-vs-not, which drives the
  transitions, was unaffected.
- **Beat alignment made it worse.** A `--beat-align` run nudged one junction by
  120 ms (the incoming beat had been 367 ms off). The listener preferred the
  plain mix. Two causes: the nudge prepends silence (under-filling the
  equal-power curve), and there was little to fix — the tracks already sat well
  together. Beat alignment is therefore **off by default**.
- **The long RMS envelope window matters.** During hardening, the envelope
  window was briefly "corrected" from ~1 s to ~93 ms; that flipped 7 of 12
  classifications (fade detection became unreliable). The ~1 s window is now an
  explicit, documented choice (`ENVELOPE_SECONDS`), not an accident.

## Lesson

The sequence's own notes say it best: the ear beat the meters more than once.
The tool's job is to make a good first guess and be easy to correct — which is
why the plan is a readable JSON artefact and the rules are a plain function.
