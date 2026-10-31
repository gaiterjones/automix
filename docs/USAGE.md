# Usage

## CLI

```
automix analyze  <tracks...> [--window S] [-o FILE]
automix plan     <tracks...> [--window S] [--target-lufs LUFS] [--beat-align|--no-beat-align] [-o FILE]
automix mix      <tracks...> [-o FILE] [--window S] [--target-lufs LUFS]
                             [--beat-align|--no-beat-align] [--bitrate B] [--plan-out FILE]
automix preview  <tracks...> [-o FILE] [--pre S] [--post S] [--gap S]
                             [--beat-align|--no-beat-align] [--tempo-match] [--bass-cut HZ]
automix --version
```

Tracks are mixed **in the order given** (that is the arrangement — automix does
not reorder them).

| flag | default | meaning |
|---|---|---|
| `-o, --output` | `mix.mp3` (mix) / `mix.plan.json` (plan) | output path |
| `--window S` | `30` | head/tail analysis window in seconds |
| `--target-lufs LUFS` | `-14` | loudness target for gain matching |
| `--beat-align` / `--no-beat-align` | **off** | beat-align `beat_mix` junctions |
| `--tempo-match` / `--no-tempo-match` | **off** | warp the incoming track to the outgoing tempo on `beat_mix` junctions |
| `--bass-cut HZ` | `0` (off) | sweep a high-pass up to HZ across the outgoing on `beat_mix` junctions |
| `--bitrate B` | `320k` | output bitrate (mp3/aac) |
| `--plan-out FILE` | — | also write the plan JSON |

### Examples

```bash
# See what automix measured
automix analyze album/*.mp3 -o fingerprints.json

# Inspect the decisions before committing to a render
automix plan album/*.mp3 -o mix.plan.json

# Render, keeping the plan for the record
automix mix album/*.mp3 -o out/album-mix.mp3 --plan-out out/album-mix.plan.json

# Louder, longer-window, beat-aligned experiment
automix mix album/*.mp3 -o out/mix.mp3 --target-lufs -11 --window 45 --beat-align
```

Progress goes to stderr, JSON to stdout, so `automix analyze ... > f.json` is
clean.

### Auditioning transitions only

```bash
automix preview album/*.mp3 -o out/transitions.mp3
```

Renders **only the junctions** — `--pre 6 --post 8` seconds either side of each
blend, joined by `--gap 0.6` s of silence — so you can check the transitions
without sitting through the whole mix. It accepts the same `--beat-align`,
`--tempo-match`, `--bass-cut` and `--plan-out` options as `mix`. The full mix is
rendered once to a lossless temp file, then the windows are cut and joined; a
19-minute mix becomes a ~2-minute preview.

## Output formats

Chosen by the output file extension: `.mp3` (libmp3lame), `.m4a` (aac),
`.wav` (pcm_s16le), `.flac` (flac); anything else defaults to mp3.

## Python API

```python
from automix import analyze_tracks, build_plan
from automix.render import render

fps  = analyze_tracks(["a.mp3", "b.mp3", "c.mp3"])
plan = build_plan(["a.mp3", "b.mp3", "c.mp3"], fps, target_lufs=-14.0)

render(plan, "out/mix.mp3")
```

`render()` also takes `sr`, `channels` and `bitrate`.

## The plan schema

```jsonc
{
  "title": "automix",
  "target_lufs": -14.0,
  "tracks": [
    {
      "path": "01.mp3",
      "gain_db": -1.2,            // to hit target_lufs
      "lufs": -12.8,              // measured
      "bpm": 129.2,
      "duration": 173.4,
      "intro_class": "beat_from_start",
      "outro_class": "fade_out"
    }
  ],
  "junctions": [
    {
      "from": 0, "to": 1,
      "mode": "beat_mix",         // cut | xfade | beat_mix | fade_under
      "duration": 8.0,            // seconds
      "curve": "tri",             // ffmpeg acrossfade curve
      "reason": "beat_run -> beat_from_start",
      "delay": 0.12,              // optional: beat-align nudge (seconds)
      "align": "beat",            // present iff delay is set
      "tempo_factor": 1.0098,     // optional: incoming warped to the outgoing
                                  // tempo (atempo factor)
      "bass_cut": 350,            // optional: high-pass sweeps to 350Hz across
                                  // the outgoing (bass clears out)
      "trim_in": 15.0,            // optional: skip N s of the incoming's head
                                  // (enter where the kick starts)
      "trim_out": 1.0             // optional: bring the incoming track in
                                  // earlier by trimming the outgoing by N s
    }
  ]
}
```

Edit it and re-render with `render(json.load(...), out)` — no re-analysis.

## Environment

| variable | effect |
|---|---|
| `FFMPEG_BINARY` | override the `ffmpeg` executable |
| `FFPROBE_BINARY` | override the `ffprobe` executable |

## Exit / errors

Errors (missing ffmpeg, unreadable file, ffmpeg failure) raise and print to
stderr with a non-zero exit. `automix` never writes a partial output silently —
a failed render leaves no file.
