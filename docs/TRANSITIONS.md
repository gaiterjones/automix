# Transitions

The vocabulary, the decision table, and how to change them. This is the part of
automix you are meant to edit after listening.

## The vocabulary

Every track gets an **intro class** and an **outro class** (see
[ANALYSIS.md](ANALYSIS.md) for how they are detected). Each junction
`outro -> intro` maps to a transition.

**Intro classes** — how a track begins:

| class | meaning |
|---|---|
| `silent_lead` | silence / quiet pickup before anything happens |
| `beat_from_start` | rhythm from the first bar |
| `percussive_build` | drums-only / no melody lead-in |
| `ambient_pad` | sustained, harmonic, beatless |
| `spoken` | voice / non-rhythmic |
| `melodic` | melody / harmony lead-in |

**Outro classes** — how a track ends:

| class | meaning |
|---|---|
| `hard_stop` | abrupt stop |
| `fade_out` | engineered fade to silence |
| `beat_run` | rhythm continues right to the end |
| `breakdown` | drops to near-silence, then ends |
| `ring_out` | sustained / ringing / reverb tail |
| `vocal_tag` | spoken / vocal ending |

**Transitions:**

| mode | what it renders |
|---|---|
| `cut` | click-free ≈20 ms crossfade (a hard cut) |
| `xfade` | equal-power crossfade of a given length and curve |
| `beat_mix` | crossfade intended to sit on the beat grid (see below) |
| `fade_under` | outgoing fades out **under** a full-level incoming (for a fading ending) |

`curve` is any ffmpeg `acrossfade` curve: `tri`, `qsin`, `hsin`, `esin`, `log`,
`ipar`, `qua`, `cub`, `squ`, `cbr`, `par`, `exp`, `lin`, `sin`.

### A short fade is usually a beat's tail

Most dance tracks that "end on a fade" actually end with the beat at full level
that decays over a second or two into the file's end. Classifying that as
`fade_out` is doubly damaging, because the overlap is then sized from the fade:

1. the outro becomes `fade_out`, so the table picks `fade_under`;
2. the fade-aware overlap sizes the blend from `fade_span` — two seconds;
3. a two-second blend centred on the decay is, audibly, **no mix at all**.

Measured on a real track: beat at −8 dBFS with `end.tempo_strength` 4.46 right
up to the end, then a 2.14 s decay and 1.7 s of silence — which produced a 2.16 s
junction. So the ending is classified `beat_run` when the fade is shorter than
`FADE_TAIL` (3 s, in `analysis.py`) **and** the ending is rhythmic. Genuine
engineered fades — 5 to 8 seconds — are unaffected, as is anything not rhythmic.

A related floor: a `beat_run` hand-over is never shorter than
`MIN_BEAT_OVERLAP` (4 s, two bars at 120 BPM), whatever the table returns. Two
seconds of two tracks is a butt-join.

### A much quieter incoming needs a longer blend

An equal-power crossfade into a head that sits well below the outgoing dips
through the middle: measured **8 dB** on a pair whose incoming opened ~15 dB down
(a quiet arpeggio intro), and by ear that junction wanted ~32 s of blend against
the 8 s default. So the overlap is lengthened when the gap between the outgoing's
ending and the incoming's head exceeds `LEVEL_GAP_DB` (6 dB): 24 s up to 12 dB,
32 s above. It only ever *lengthens*, and on the arpnotic set it fired on exactly
one junction out of eight — the one that had been hand-set to 34 s.

Two related rules were tried and **rejected**, recorded so they are not
re-derived:

- *Gate the bass cut on "does the ending have low-end to clear out".* It cannot
  be measured: an arpeggio in F minor carries its own notes at 43 and 87 Hz, so a
  bass-stripped arp measures −9.0 dB under 150 Hz while a full mix measures
  −8.6 dB. Indistinguishable. The cut stays un-gated, and an arp set is judged by
  ear (`--bass-cut 0`).
- *Extend the overlap to span a quiet intro's `head.rise_s`.* On the arpnotic set
  every track builds over ~30 s, so it fired on all eight junctions and rewrote a
  mix that had been approved by ear. `rise_s` remains in the fingerprint as a
  diagnostic.

## The decision table

`automix/taxonomy.py::decide(outro, intro) -> (mode, duration_seconds, curve)`:

```python
rhythmic = intro in (INTRO_BEAT, INTRO_PERC)
beatless = intro in (INTRO_SPOKEN, INTRO_AMBIENT, INTRO_SILENT)

if outro == OUTRO_HARDSTOP:
    return (CUT, 0.05)            if rhythmic or intro == SILENT else (XFADE, 3.0)
if outro == OUTRO_FADE:
    return (XFADE, 2.0)           # already fading - slide the next one in early
if outro == OUTRO_VOCAL:
    return (CUT, 0.05)            if rhythmic else (XFADE, 4.0)
if outro in (OUTRO_RING, OUTRO_BREAK):
    return (XFADE, 12.0, "log")   # let the tail breathe under the incoming track
if outro == OUTRO_BEATRUN:
    return (BEAT_MIX, 8.0)        if rhythmic
    return (XFADE, 10.0)          if beatless
    return (XFADE, 8.0)
return (XFADE, 6.0)               # default
```

Read it as prose:

- **a hard-stopped track is already a cut point** → cut into a rhythmic opening;
- **a track that fades** → `fade_under`: the incoming plays at full level and
  the outgoing fades out underneath it. (A plain equal-power crossfade fades
  *both* sides, so a fade-out meeting a quiet head leaves a hole in the level —
  measured ~14–20 dB at real junctions.) The overlap is made to span the detected
  fade;
- **a vocal tag** → cut if the next track opens on a beat, else a short crossfade;
- **a ringing / breakdown tail** → a long, gentle overlap so it rings under;
- **a beat run into a beat opening** → an 8 s beat mix;
- **a beat run into something beatless** → a longer crossfade to cover the gap.

To change behaviour, edit the durations, curves and conditions — then listen.
There's nothing else to keep in sync.

## Beat alignment {#beat-alignment}

`--beat-align` (CLI) / `beat_align=True` (`build_plan`) adds a **nudge** to
`beat_mix` junctions so the incoming track's beat coincides with the outgoing
track's beat through the crossfade.

- `beatgrid.detect()` finds the beat period, phase and a 4/4 downbeat of a window
  by comb-filtering the onset envelope (phase that maximises transient energy;
  strongest of the four bar positions = downbeat).
- `beatgrid.mix_delay()` returns the seconds to delay the incoming track:
  `(a_next - overlap_start - first_beat_of_incoming) mod period`. The renderer
  applies it with ffmpeg `adelay`.
- It **abstains** (returns 0, no nudge) unless both grids are confident
  (`strength ≥ 1.5`) and the tempos are within 3 % — a phase nudge cannot hold
  two grids that drift apart across the fade.

**It is off by default.** On the reference material the plain crossfade was
preferred by ear, for two reasons worth fixing before it earns its keep:

1. the nudge is implemented as `adelay`, which **prepends silence** rather than
   trimming, so the incoming side is silent for the nudge duration and the
   equal-power curve under-fills — a small dip at the transition;
2. alignment alone is only half of beat *mixing*: without **tempo matching**
   (rubberband/atempo) it cannot engage on pairs whose tempos differ, which is
   most real pairs.

Fix (1) by shifting the phase without silence (trim the outgoing tail by up to a
beat) and add (2), and `beat_mix` starts to mean what it says. Until then, plain
crossfades win. See [ROADMAP.md](ROADMAP.md).
