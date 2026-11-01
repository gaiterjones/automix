# Case studies

## ARPNOTIC VOL.1 — nine tracks

A public sequence: **[ARPNOTIC VOL.1](https://www.mixcloud.com/gaiterjones/arpnotic-vol1/)**
— nine tracks in F minor at ~123 BPM, 28:53, mixed end to end by automix. The
source tracks are not in this repository.

The shipped junction plan:

| junction | transition | notes |
|---|---|---|
| 1→2 | fade_under 16 s | outgoing fades out |
| 2→3 | fade_under 7.25 s | outgoing ends on a cymbal splash — 3.8 s trimmed |
| 3→4 | fade_under 16 s | |
| 4→5 | fade_under 8.96 s | outgoing's trailing silence trimmed — 3.7 s |
| 5→6 | beat_mix 11 s | warp ×1.0098, 316 ms nudge, bass cut 350 Hz, splash trimmed 6.5 s |
| 6→7 | fade_under 16 s | beatless intro rides under the outgoing |
| 7→8 | beat_mix 14 s | warp ×0.99919, 164 ms nudge, bass cut |
| 8→9 | xfade 34 s | outgoing stops dead; incoming's quiet arp intro only reaches full level ~34 s in |

**Four junctions were hand-set after listening, not chosen by the rule table**
(5→6, 7→8, 8→9, and the 4→5 trim). That is the design working: the plan is an
editable artefact and the ear is the judge. The table alone had picked
`fade_under 2 s` for 7→8 — a short tail decay masking a beat run — and
`beat_mix 8 s` for 8→9.

### What the set exposed

Three bugs that only listening found:

- **A bass-cut junction silently collapsed into a hard cut.** That branch
  pre-trimmed both sides to exactly the fade length and crossfaded the stubs.
  Decoded audio is a fraction of a second shorter than its nominal duration, so
  `acrossfade` could not fit inside them and emitted a near-empty segment
  instead of failing — the outgoing track's last N seconds disappeared into a
  cut. Fixed by crossfading the full streams with the sweep offset to the
  junction. Every bass-cut junction was affected, including the 5→6 example
  shipped in this repository.
- **`bass_cut` overrode `mode`.** The bass-cut branch was tested before the mode
  switch, so any junction carrying a bass cut rendered as a crossfade even when
  the plan said `fade_under` — two different plans produced byte-identical
  audio. `mode` is now authoritative.
- **A fade anchored to the end of the file, not the end of the audio.** Track 4
  fades to silence ~3.7 s before its file ends; the overlap sat entirely inside
  that dead air, so nothing audible ever crossfaded. The planner now trims a
  trailing silence when it is a meaningful share of the overlap.

### What worked

- **Tempo** — all nine tracks measured 123.6–123.7 BPM, with no sub-harmonic
  errors.
- **Splash trimming** — the cymbal tails on tracks 2 and 5 were removed and the
  mix ended before the crash.
- **Loudness matching** — the set holds at −14 LUFS with no track jumping out.
- **The long fade into a dead stop** — 8 stops abruptly and 9 opens with a 34 s
  quiet arp intro; a long crossfade masked the stop completely.

## A 12-track sequence

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
