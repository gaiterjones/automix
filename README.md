# automix

[![ci](https://github.com/gaiterjones/automix/actions/workflows/ci.yml/badge.svg)](https://github.com/gaiterjones/automix/actions/workflows/ci.yml)

**Intelligent sequential audio mixer.** Give it an ordered list of tracks and it
decides **how each one should hand over to the next** — fade, hard cut, long
layered crossfade, beat mix — instead of blindly crossfading every join.

```bash
automix mix 01.mp3 02.mp3 03.mp3 -o out/mix.mp3
```

Most auto-mixers do one thing: cross-fade everything for N seconds. The
interesting problem isn't the DSP glue — it's *judging* how a track begins and
ends:

- a track that fades out wants the next one slid in early;
- a track that stops dead wants a clean cut, not a smear;
- a track that ends on a beat, running into one that opens on a beat, wants to
  meet on the grid;
- a spoken or beatless intro wants the previous track to ring out beneath it.

automix makes those judgements per junction, from measurements of each track's
head and tail, and renders the result with ffmpeg.

```
analyse  ->  classify  ->  decide  ->  render
(head/tail)   (taxonomy)    (rules)    (ffmpeg)
```

It is deliberately **rules-first**: a small, explainable decision table you can
edit after listening — not a black box. The machinery to feed an LLM (or a
human) as the planner is already there; it just isn't needed yet.

## Requirements

- **ffmpeg** and **ffprobe** on `PATH` (any recent build; `rubberband` optional).
- **Python ≥ 3.10**.

There are **no Python dependencies** — analysis is ffmpeg plus the standard
library, so it drops into a minimal container. `FFMPEG_BINARY` / `FFPROBE_BINARY`
are respected if you keep them off `PATH`.

## Install

```bash
pipx install git+https://github.com/gaiterjones/automix   # or
pip install git+https://github.com/gaiterjones/automix
```

Or run it without installing:

```bash
git clone https://github.com/gaiterjones/automix && cd automix
./bin/automix --help
```

## Quick start

```bash
# 1. What does automix think of these tracks?
automix analyze 01.mp3 02.mp3 03.mp3        # JSON fingerprints

# 2. What transitions would it choose? (no audio rendered)
automix plan 01.mp3 02.mp3 03.mp3 -o mix.plan.json

# 3. Do it
automix mix 01.mp3 02.mp3 03.mp3 -o out/mix.mp3
```

```text
junctions:
  1 -> 2: xfade 2.0s (tri)   [fade_out -> beat_from_start]
  2 -> 3: beat_mix 8.0s (tri)  [beat_run -> beat_from_start]
  3 -> 4: xfade 12.0s (log)  [breakdown -> beat_from_start]
expected length: 683.2s
rendering -> out/mix.mp3
done: out/mix.mp3  (683.05s)
```

## The vocabulary

**Intros** — how a track begins:
`silent_lead`, `beat_from_start`, `percussive_build`, `ambient_pad`, `spoken`,
`melodic`.

**Outros** — how a track ends:
`hard_stop`, `fade_out`, `beat_run`, `breakdown`, `ring_out`, `vocal_tag`.

**Transitions** — `cut` (click-free ≈20 ms), `xfade` (equal-power crossfade of a
given length/curve), `beat_mix` (crossfade intended to sit on the beat grid).

The mapping `<outro> -> <intro>` to a transition lives in one function,
[`taxonomy.decide()`](automix/taxonomy.py) — edit it as you listen.

## How it works

Per track, automix measures a **30 s head window** and a **30 s tail window**
and, from those, a short **ending** window (last ~12 s) plus a **mid-track**
window for tempo. Features: EBU R128 loudness, RMS envelope, onset rate,
zero-crossing rate, tempo + rhythmicity (autocorrelation peak/mean), silence
edges, fade and abrupt-end detection. From those it classifies the intro and
outro, and the rule table picks each transition. Full detail in
[docs/DESIGN.md](docs/DESIGN.md), [docs/ANALYSIS.md](docs/ANALYSIS.md) and
[docs/TRANSITIONS.md](docs/TRANSITIONS.md).

## The plan is the artefact

`automix plan` writes plain JSON — track gains and per-junction transitions.
Rendering is a pure execute step, so a human or an LLM can edit the plan without
touching audio code.

```json
{
  "title": "automix",
  "target_lufs": -14.0,
  "tracks": [
    { "path": "01.mp3", "gain_db": -1.2, "intro_class": "beat_from_start",
      "outro_class": "fade_out", "bpm": 129.2, "duration": 173.4 }
  ],
  "junctions": [
    { "from": 0, "to": 1, "mode": "xfade", "duration": 2.0, "curve": "tri",
      "reason": "fade_out -> beat_from_start" }
  ]
}
```

## Beat alignment (off by default)

`--beat-align` nudges the incoming track so its beat lands on the outgoing
track's beat through the crossfade (using `adelay`). It is **off by default**:
on the reference material a plain crossfade was preferred by ear, and the
current nudge pads with silence rather than trimming, which under-fills the
equal-power curve. See [docs/TRANSITIONS.md](docs/TRANSITIONS.md#beat-alignment)
for the details and what it would take to make it earn its keep.

## Documentation

| | |
|---|---|
| [docs/DESIGN.md](docs/DESIGN.md) | architecture, data flow, the fingerprint schema |
| [docs/ANALYSIS.md](docs/ANALYSIS.md) | every feature, window and threshold; how to tune |
| [docs/TRANSITIONS.md](docs/TRANSITIONS.md) | the taxonomy, the decision table, beat alignment |
| [docs/USAGE.md](docs/USAGE.md) | full CLI + Python API + plan schema |
| [docs/TESTING.md](docs/TESTING.md) | synthetic tracks, unit tests, CI |
| [docs/ROADMAP.md](docs/ROADMAP.md) | where it goes next |
| [docs/CASE-STUDY.md](docs/CASE-STUDY.md) | a real 12-track run, with findings |
| [CHANGELOG.md](CHANGELOG.md) | release history |
| [CONTRIBUTING.md](CONTRIBUTING.md) | how to hack on it |

## Limitations

- **Tempo detection is plain onset-autocorrelation** (+ harmonic weighting and a
  log-normal prior). It can lock onto a sub-harmonic on tracks with strong
  2:1 / 3:2 accent patterns; on the reference set it matched 10 of 12 tracks.
  Rhythmic-vs-not, which drives the transitions, is unaffected.
- **`beat_mix` renders as an equal-power crossfade** — there is no tempo
  matching and beat alignment is off by default, so it is not yet a true beat
  mix.
- The rule thresholds are v1 heuristics tuned on a small reference set. They are
  named constants precisely so you can adjust them against your own material.

## License

MIT — see [LICENSE](LICENSE).
