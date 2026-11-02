# Analysis

How automix measures a track. Everything here is computed from ffmpeg output
plus the standard library — see `automix/ffmpeg.py` (I/O) and `automix/dsp.py`
(the maths).

## Windows

| window | length | used for |
|---|---|---|
| head | first 30 s | intro classification, character |
| mid | from 15 % in, ≤60 s | **tempo** and rhythmicity |
| ending | last 12 s | **outro** classification |
| tail | last 30 s | context / reporting |
| head beat | first 20 s | beat grid for alignment (incoming) |
| tail beat | last 20 s | beat grid for alignment (outgoing) |

Windows are decoded to mono, 11025 Hz, s16le — low on purpose: we only look at
envelopes and onsets.

## Features

| feature | how | notes |
|---|---|---|
| `lufs_integrated`, `true_peak_db`, `lra` | ffmpeg `ebur128=peak=true` | EBU R128; drives loudness matching |
| `silences` | ffmpeg `silencedetect=-40dB:0.4` | ranges, for reporting and validation |
| RMS envelope | frame RMS, 1024-frame window, 256 hop | the basis of everything else |
| `onset_rate` | rises in the envelope above 10 % of the peak frame | transients/second |
| `tempo`, `tempo_strength` | autocorrelation of the onset envelope | see below |
| `zcr` | sign changes / samples | a cheap "noisy / voice-like" proxy |
| `lead_silence`, `trail_silence` | envelope below 2 % of peak | seconds |
| `fade` | monotonic decrease over the last 8 s | engineered fade-out |
| `abrupt` | still ≥35 % of peak in the final 200 ms | hard stop |
| `head.rise_s` | seconds until the opening holds within 2 dB of the level it later reaches; **0** unless the opening is ≥8 dB below it | how long a quiet intro takes to arrive. Diagnostic: a planner rule on it was tried and rejected (it fires on nearly every track) |

### Tempo

`estimate_tempo()` autocorrelates the onset envelope, then applies two standard
corrections:

- **harmonic weighting** — each candidate lag is scored by the summed
  autocorrelation at its harmonics (`lag + 0.5·2lag + 0.25·3lag`), which
  suppresses sub-harmonic peaks;
- **a log-normal prior** centred on 120 BPM (`prior_octaves=0.9`), which breaks
  octave ties toward plausible tempos.

`tempo_strength` = peak/mean of the autocorrelation over the candidate range,
independent of the weighting. **It is the key "is this rhythmic?" signal** — a
click track gives a high value, a sustained tone gives ~1.

## Thresholds and tuning

Named constants at the top of `automix/analysis.py`:

| constant | default | meaning |
|---|---|---|
| `T_STRENGTH` | 2.0 | `tempo_strength` at/above which the material is "clearly rhythmic" |
| `T_ONSET` | 2.0 | onsets/second for "active rhythm" |
| `T_ZCR` | 0.16 | ZCR for "noisy / voice-like" |
| `T_LEAD` | 1.0 | seconds of leading silence → `silent_lead` |
| `BEAT_WINDOW` | 20.0 | seconds of head/tail used to locate the beat grid |
| `ENVELOPE_SECONDS` | 1.0 | RMS envelope window (seconds) — see note below |

The RMS **envelope window is deliberately ~1 s** while the hop stays short
(23 ms). A long window smooths the energy curve so silence-edge and fade
detection are stable; a short (~93 ms) frame makes the envelope jittery and the
fade test unreliable. Boundaries still land precisely because the hop is short.

They are v1 heuristics tuned on a small reference set (see
[CASE-STUDY.md](CASE-STUDY.md)). If you tune them for your own material, do it
by ear and say what you tested on.

## Rules

```python
classify_intro(head):
    lead_silence >= T_LEAD                         -> silent_lead
    tempo_strength >= T_STRENGTH                   -> beat_from_start
    zcr >= T_ZCR and tempo_strength < 1.8          -> spoken
    tempo_strength >= 1.4 and onset_rate >= T_ONSET-> percussive_build
    tempo_strength < 1.4 and onset_rate < 1.5      -> ambient_pad (or silent_lead if very quiet)
    otherwise                                      -> melodic

classify_outro(end, head):
    fade                                           -> fade_out
    tempo_strength >= T_STRENGTH                   -> beat_run
    abrupt                                         -> hard_stop
    trail_silence >= 1.0                           -> breakdown
    rms_db is None or rms_db < -45                 -> breakdown     # dead tail
    zcr >= T_ZCR and tempo_strength < 1.8          -> vocal_tag
    rms_db < head.rms_db - 6                       -> ring_out
    otherwise                                      -> beat_run
```

Order matters: an engineered fade wins over "beat run"; a clearly rhythmic tail
wins over "abrupt" (a beat track that stops dead is a beat run that ends, not a
hard-stopped pad).

## Known limitations

- **Sub-harmonic tempo errors.** On tracks whose onset pattern accents every 2nd
  or 3rd beat, the autocorrelation can favour a sub-harmonic (e.g. reading 80.7
  or 63 for a 123 BPM track). Harmonic weighting + the prior reduce this but do
  not eliminate it; a proper DFT tempogram would do better. Classification is
  unaffected (the material is still plainly rhythmic).
- **ZCR is a weak proxy** for "voice" — it separates noise from tones, not
  reliably voice from percussion. It is only ever a tie-breaker after the
  rhythmic tests.
- **`tempo_strength` on very short windows** is noisy; the head/ending windows
  are deliberately not shorter than they are.
- **A pure sustained tone can read as slightly rhythmic.** The ~1 s RMS envelope
  "beats" when a frame holds a non-integer number of periods, so a bare sine
  shows low-level periodic onsets. Real material with any transient content is
  unaffected (a sustained pad sitting under drums is fine).
