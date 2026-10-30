# Design

## The shape of the problem

Blindly crossfading every join for N seconds is easy and sounds mediocre. The
quality of a mix is decided by *what kind of join each pair needs* — and that
depends on how one track ends and the next begins. So the problem splits cleanly
into four stages:

```
   analyse            classify            decide             render
 ┌──────────┐      ┌───────────┐      ┌───────────┐      ┌───────────┐
 │ head/tail│  ->  │ intro /   │  ->  │ transition│  ->  │ ffmpeg    │
 │ features │      │ outro cls │      │ + params  │      │ graph     │
 └──────────┘      └───────────┘      └───────────┘      └───────────┘
   analysis.py       taxonomy.py        plan.py /         render.py
                                       taxonomy.decide()
```

Each stage has one job, and the boundary between *decide* and *render* is a
plain JSON artefact (the **mix plan**). That means the mixing decisions can be
inspected, edited by a human, or produced by something else entirely (an LLM,
a UI) without the renderer changing.

## Rules first, ML later

The decisions here are small and explicable ("a fade-out wants the next track
slid in early"). A decision table gets you most of the way immediately, is
tunable by ear, and never fails silently. A learned or LLM planner is a later
polish — and the plan JSON is the hook it will plug into. Building the neural
version first would be data-hungry, non-deterministic and, at this scale, worse.

## Module map

| module | responsibility |
|---|---|
| `automix/ffmpeg.py` | ffprobe/ffmpeg wrappers: metadata, EBU R128 loudness, `silencedetect`, raw PCM windows |
| `automix/dsp.py` | stdlib signal maths: RMS envelope, onset envelope, tempo, ZCR, silence/fade/abrupt |
| `automix/beatgrid.py` | beat period/phase/downbeat detection and the alignment nudge |
| `automix/taxonomy.py` | the intro/outro vocabulary and `decide()` (the decision table) |
| `automix/analysis.py` | fingerprint a track; classify its intro and outro |
| `automix/plan.py` | fingerprints -> mix plan (JSON) |
| `automix/render.py` | mix plan -> audio (one ffmpeg `filter_complex` graph) |
| `automix/cli.py` | `analyze` / `plan` / `mix` |

There are **no Python dependencies**; `ffmpeg.py` shells out to the `ffmpeg`
and `ffprobe` binaries, and everything numeric is standard library.

## Data flow, concretely

1. `analysis.analyze_track(path)` runs ffprobe, ffmpeg (`ebur128`,
   `silencedetect`) and several PCM decodes, and returns a **fingerprint**
   (a plain dict — the whole vocabulary a later stage is allowed to see).
2. `taxonomy.classify_*` (called inside analysis) turns the fingerprint's head
   and ending features into an intro class and an outro class.
3. `plan.build_plan(paths, fingerprints)` computes a loudness gain per track and
   asks `taxonomy.decide(outro, intro)` for each junction, producing the plan.
4. `render.render(plan, out)` builds one ffmpeg filter graph: every input is
   forced to a common format and gain-matched, then the tracks are folded
   together in order with `acrossfade`.

## The fingerprint

```jsonc
{
  "path": "...", "duration": 173.4, "codec": "mp3",
  "lufs_integrated": -14.0, "true_peak_db": -1.1, "lra": 6.2,
  "silences": [[170.17, 170.64], [170.65, 173.37]],
  "bpm": 129.2, "tempo_strength": 4.67,          // from a mid-track window
  "head":  { "rms_db": -20.5, "onset_rate": 1.84, "zcr": 0.10,
             "lead_silence": 0.0, ... },          // first 30 s
  "end":   { "rms_db": -20.8, "fade": true, "abrupt": false,
             "trail_silence": 2.69, ... },        // last ~12 s (the outro)
  "tail":  { ... },                               // last 30 s (context)
  "head_beat": { "bpm": 129.2, "period": 0.464, "phase": 0.12,
                 "strength": 3.8, "downbeat": 0 },  // for alignment
  "tail_beat": { ... },
  "intro_class": "beat_from_start", "outro_class": "fade_out"
}
```

Only the last two fields are consumed by the *decision*; the rest exist so a
human (or an LLM planner) can see *why*.

## Rendering

A single `-filter_complex` graph, not a pairwise fold. Each input gets

```
[i]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,
   volume=<gain>dB[, adelay=<ms>:all=1][ai]
```

and then, in order,

```
[a0][a1]acrossfade=d=<d>:c1=<c>:c2=<c>[m0]
[m0][a2]acrossfade=d=<d>:c1=<c>:c2=<c>[m1]  ...
```

One graph decodes each input once and writes no intermediate files — important
once a mix is a dozen tracks long. Loudness matching is a simple per-track gain
from the measured integrated LUFS (clamped), which is enough to stop a quiet
track drowning next to a loud one. A "cut" is expressed as a ~20 ms crossfade so
it is click-free without special-casing.

## Why these windows

- **Head 30 s** — intros are short; 30 s is enough for a stable
  rhythmicity read without dragging the body of the track in.
- **Mid-track ~15 %→60 s** — tempo is measured here, not at the head/tail,
  because a quiet or half-time opening or a fade-out misleads the estimator.
- **Ending ~12 s** — the outro is judged on how the track *actually ends*, not
  on a 30 s window that may be mostly music before a dead tail.
- **Tail 30 s** — kept for context and reporting.

See [ANALYSIS.md](ANALYSIS.md) for every feature and threshold, and
[TRANSITIONS.md](TRANSITIONS.md) for the decision table.
