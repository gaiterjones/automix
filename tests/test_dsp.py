"""Unit tests. Graph/DSP checks need no ffmpeg; the render length regression
tests skip themselves when ffmpeg is not on PATH."""
import math
import os
import shutil
import subprocess
import tempfile
import unittest
from array import array

from automix import dsp, plan as planmod, render, taxonomy

SR = 11025
HOP = dsp.HOP
FRAME = dsp.FRAME


def _silence(seconds, sr=SR):
    return array("h", [0]) * int(seconds * sr)


def _tone(seconds, freq=440.0, amp=10000, sr=SR):
    n = int(seconds * sr)
    return array("h", [int(amp * math.sin(2 * math.pi * freq * i / sr)) for i in range(n)])


def _click_train(bpm, seconds, amp=30000, click_ms=8, sr=SR):
    period = 60.0 / bpm
    click = int(sr * click_ms / 1000)
    n = int(seconds * sr)
    a = array("h", [0]) * n
    k = 0
    while True:
        start = int(k * period * sr)
        if start >= n:
            break
        for i in range(start, min(n, start + click)):
            a[i] = amp
        k += 1
    return a


class TestTempo(unittest.TestCase):
    def test_click_train_is_rhythmic(self):
        # A pure click train is tempo-ambiguous (every divisor is also a valid
        # period), so we assert a plausible tempo and a strong rhythm reading -
        # the property the classifier actually relies on.
        env = dsp.frame_rms(_click_train(120, 20))
        bpm, strength = dsp.estimate_tempo(env, SR)
        self.assertIsNotNone(bpm)
        self.assertTrue(55 <= bpm <= 130, bpm)
        self.assertGreater(strength, 2.0)

    def test_flat_envelope_has_no_tempo(self):
        bpm, strength = dsp.estimate_tempo([1.0] * 400, SR)
        self.assertIsNone(bpm)
        self.assertEqual(strength, 0.0)


class TestEnvelopeFeatures(unittest.TestCase):
    def test_zero_crossing_rate(self):
        alternating = array("h", [1000 if i % 2 else -1000 for i in range(1000)])
        self.assertGreater(dsp.zero_crossing_rate(alternating), 0.9)
        constant = array("h", [1000]) * 1000
        self.assertEqual(dsp.zero_crossing_rate(constant), 0.0)

    def test_silence_edges(self):
        samples = _silence(2) + _tone(3) + _silence(3)
        env = dsp.frame_rms(samples)
        lead, trail = dsp.silence_edges(env, SR)
        self.assertTrue(1.5 <= lead <= 2.5, lead)
        self.assertTrue(2.5 <= trail <= 3.5, trail)

    def test_fade_detection(self):
        decaying = [10000.0 * (1 - i / 400.0) for i in range(400)]
        self.assertTrue(dsp.fade_out_likely(decaying, SR))
        flat = [10000.0] * 400
        self.assertFalse(dsp.fade_out_likely(flat, SR))

    def test_abrupt_end(self):
        self.assertTrue(dsp.abrupt_end([10000.0] * 100, SR))
        tail_silent = [10000.0] * 80 + [0.0] * 20
        self.assertFalse(dsp.abrupt_end(tail_silent, SR))

    def test_noise_tail_span(self):
        import random
        random.seed(1)
        tone = array("h", [int(8000 * math.sin(2 * math.pi * 220 * i / SR)) for i in range(SR)])
        noise = array("h", [random.randint(-8000, 8000) for _ in range(SR // 2)])
        self.assertEqual(dsp.noise_tail_span(tone, SR), 0.0)      # tonal ending
        self.assertGreater(dsp.noise_tail_span(tone + noise, SR), 0.3)  # noise tail

    def test_fade_span(self):
        self.assertEqual(dsp.fade_span([10000.0] * 100, SR), 0.0)
        decaying = [10000.0] * 50 + [10000.0 * (1 - i / 50) for i in range(50)]
        self.assertGreater(dsp.fade_span(decaying, SR), 0.5)


class TestTaxonomy(unittest.TestCase):
    def test_hard_stop_into_beat_is_a_cut(self):
        mode, dur, _ = taxonomy.decide(taxonomy.OUTRO_HARDSTOP, taxonomy.INTRO_BEAT)
        self.assertEqual(mode, taxonomy.MODE_CUT)

    def test_fade_out_fades_under(self):
        mode, dur, _ = taxonomy.decide(taxonomy.OUTRO_FADE, taxonomy.INTRO_BEAT)
        self.assertEqual(mode, taxonomy.MODE_FADE_UNDER)
        self.assertEqual(dur, 2.0)

    def test_ring_out_is_a_long_xfade(self):
        mode, dur, _ = taxonomy.decide(taxonomy.OUTRO_RING, taxonomy.INTRO_BEAT)
        self.assertEqual(mode, taxonomy.MODE_XFADE)
        self.assertEqual(dur, 12.0)

    def test_beat_run_into_beat_is_beat_mix(self):
        mode, _, _ = taxonomy.decide(taxonomy.OUTRO_BEATRUN, taxonomy.INTRO_BEAT)
        self.assertEqual(mode, taxonomy.MODE_BEAT)


class TestGraph(unittest.TestCase):
    def test_graph_includes_adelay_for_beat_alignment(self):
        plan = {
            "tracks": [{"path": "a", "gain_db": 0.0}, {"path": "b", "gain_db": -1.0}],
            "junctions": [{"from": 0, "to": 1, "mode": "beat_mix",
                           "duration": 8.0, "curve": "tri",
                           "delay": 0.12, "align": "beat"}],
        }
        graph, out = render._build_graph(plan, 44100, 2)
        self.assertIn("adelay=120:all=1", graph)
        self.assertIn("acrossfade=d=8.000", graph)
        self.assertEqual(out, "m0")

    def test_graph_trim_out_shifts_incoming(self):
        plan = {
            "tracks": [{"path": "a", "gain_db": 0.0, "duration": 173.4},
                       {"path": "b", "gain_db": 0.0, "duration": 174.5}],
            "junctions": [{"from": 0, "to": 1, "mode": "xfade", "duration": 2.0,
                           "curve": "tri", "trim_out": 1.0}],
        }
        graph, out = render._build_graph(plan, 44100, 2)
        self.assertIn("atrim=0:172.400", graph)   # 173.4 - 1.0
        self.assertIn("acrossfade=d=2.000", graph)
        self.assertEqual(out, "m0")

    def test_graph_applies_tempo_warp(self):
        plan = {
            "tracks": [{"path": "a", "gain_db": 0.0, "duration": 100.0},
                       {"path": "b", "gain_db": 0.0, "duration": 80.0}],
            "junctions": [{"from": 0, "to": 1, "mode": "beat_mix", "duration": 8.0,
                           "curve": "tri", "tempo_factor": 1.0098,
                           "delay": 0.2, "align": "beat"}],
        }
        graph, out = render._build_graph(plan, 44100, 2)
        self.assertIn("atempo=1.009800", graph)
        self.assertIn("adelay=200:all=1", graph)

    def test_graph_applies_filter_in(self):
        plan = {
            "tracks": [{"path": "a", "gain_db": 0.0, "duration": 100.0},
                       {"path": "b", "gain_db": 0.0, "duration": 80.0}],
            "junctions": [{"from": 0, "to": 1, "mode": "beat_mix", "duration": 8.0,
                           "curve": "tri", "filter_in": 1200}],
        }
        graph, _ = render._build_graph(plan, 44100, 2)
        self.assertIn("highpass@fi1=f=1200", graph)
        self.assertIn("asendcmd=c='", graph)

    def test_mode_is_authoritative_over_bass_cut(self):
        # a fade_under junction carrying a bass cut must still render as a
        # fade_under (outgoing afaded out under a full-level incoming), not as
        # a crossfade: bass_cut used to be tested before mode.
        plan = {
            "tracks": [{"path": "a", "gain_db": 0.0, "duration": 100.0},
                       {"path": "b", "gain_db": 0.0, "duration": 80.0}],
            "junctions": [{"from": 0, "to": 1, "mode": "fade_under", "duration": 8.0,
                           "curve": "tri", "bass_cut": 350}],
        }
        graph, _ = render._build_graph(plan, 44100, 2)
        self.assertIn("amix=inputs=2", graph)
        self.assertIn("afade=t=out", graph)
        self.assertIn("highpass@bc0=f=20", graph)
        self.assertNotIn("acrossfade", graph)

    def test_beat_mix_with_bass_cut_uses_acrossfade(self):
        plan = {
            "tracks": [{"path": "a", "gain_db": 0.0, "duration": 100.0},
                       {"path": "b", "gain_db": 0.0, "duration": 80.0}],
            "junctions": [{"from": 0, "to": 1, "mode": "beat_mix", "duration": 8.0,
                           "curve": "tri", "bass_cut": 350}],
        }
        graph, _ = render._build_graph(plan, 44100, 2)
        self.assertIn("acrossfade", graph)
        self.assertIn("highpass@bc0 f 20", graph)
        # the two full streams are crossfaded directly; pre-trimming them to the
        # fade length made acrossfade collapse into a hard cut
        self.assertNotIn("concat=n=3", graph)

    def test_bass_cut_junction_keeps_the_full_length(self):
        # regression: the bass-cut branch used to trim both sides to `duration`
        # and crossfade the stubs, so the result lost `duration` seconds and
        # became a hard cut. The output must be lenA + lenB - duration.
        if not shutil.which("ffmpeg"):
            self.skipTest("ffmpeg not available")
        tmp = tempfile.mkdtemp()
        a, b = os.path.join(tmp, "a.wav"), os.path.join(tmp, "b.wav")
        for path, freq in ((a, 220), (b, 330)):
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
                            "-i", f"sine=frequency={freq}:duration=8", path], check=True)
        plan = {
            "tracks": [{"path": a, "gain_db": 0.0, "duration": 8.0},
                       {"path": b, "gain_db": 0.0, "duration": 8.0}],
            "junctions": [{"from": 0, "to": 1, "mode": "beat_mix", "duration": 3.0,
                           "curve": "tri", "bass_cut": 350}],
        }
        out = os.path.join(tmp, "mix.wav")
        render.render(plan, out)
        got = float(subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", out],
            capture_output=True, text=True).stdout)
        self.assertAlmostEqual(got, 13.0, delta=0.2)

    def test_graph_applies_trim_in(self):
        plan = {
            "tracks": [{"path": "a", "gain_db": 0.0, "duration": 100.0},
                       {"path": "b", "gain_db": 0.0, "duration": 80.0}],
            "junctions": [{"from": 0, "to": 1, "mode": "beat_mix", "duration": 8.0,
                           "curve": "tri", "trim_in": 15.0}],
        }
        graph, _ = render._build_graph(plan, 44100, 2)
        self.assertIn("atrim=start=15.000", graph)

    def test_graph_bass_cut_sweeps_highpass(self):
        plan = {
            "tracks": [{"path": "a", "gain_db": 0.0, "duration": 100.0},
                       {"path": "b", "gain_db": 0.0, "duration": 80.0}],
            "junctions": [{"from": 0, "to": 1, "mode": "beat_mix", "duration": 8.0,
                           "curve": "tri", "bass_cut": 350}],
        }
        graph, out = render._build_graph(plan, 44100, 2)
        self.assertIn("asendcmd=c='", graph)
        self.assertIn("highpass@bc0", graph)
        # the sweep runs over the outgoing's LAST `duration` seconds (100 - 8 =
        # 92), and the two full streams are crossfaded directly
        self.assertIn("92.000 highpass@bc0 f 20", graph)
        self.assertIn("[t0][a1]acrossfade=d=8.000", graph)

    def test_graph_fade_under(self):
        plan = {
            "tracks": [{"path": "a", "gain_db": 0.0, "duration": 100.0},
                       {"path": "b", "gain_db": 0.0, "duration": 80.0}],
            "junctions": [{"from": 0, "to": 1, "mode": "fade_under",
                           "duration": 8.0, "curve": "tri"}],
        }
        graph, out = render._build_graph(plan, 44100, 2)
        self.assertIn("amix=inputs=2", graph)
        self.assertIn("concat=n=3", graph)
        self.assertIn("afade=t=out", graph)
        self.assertEqual(out, "m0")

    def test_graph_without_delay(self):
        plan = {"tracks": [{"path": "a", "gain_db": 0.0}], "junctions": []}
        graph, out = render._build_graph(plan, 44100, 2)
        self.assertNotIn("adelay", graph)
        self.assertEqual(out, "a0")


class TestBeatgrid(unittest.TestCase):
    def test_mix_delay_accounts_for_out_trim(self):
        from automix import beatgrid
        P = 60.0 / 123.0
        out = {"duration": 100.0,
               "tail_beat": {"bpm": 123.0, "period": P, "phase": 0.1, "start": 80.0, "strength": 5.0}}
        inn = {"head_beat": {"bpm": 123.0, "period": P, "phase": 0.0, "start": 0.0, "strength": 5.0}}

        d0 = beatgrid.mix_delay(out, inn, 8.0, out_trim=0.0)
        d1 = beatgrid.mix_delay(out, inn, 8.0, out_trim=6.5)
        # the splash trim moves the effective end, so the nudge must differ
        self.assertGreater(abs(d0 - d1), 0.01)

        # with the trim, the incoming beat lands exactly on an outgoing beat
        t0 = (100.0 - 6.5) - 8.0
        a_next = beatgrid.next_beat(out["tail_beat"], t0)
        self.assertAlmostEqual(((0.0 + d1) - (a_next - t0)) % P, 0.0, places=3)


class TestTrimInAlignment(unittest.TestCase):
    def test_entering_mid_track_aligns_to_the_body_grid(self):
        from automix import beatgrid
        P = 0.5
        out = {"duration": 100.0, "tail_beat": {"bpm": 120.0, "period": P,
                                               "phase": 0.1, "start": 80.0, "strength": 5.0}}
        inn = {"head_beat": {"bpm": 120.0, "period": P, "phase": 0.0, "start": 0.0, "strength": 5.0},
               "body_beat": {"bpm": 120.0, "period": P, "phase": 0.2, "start": 20.0, "strength": 5.0}}
        trim_in = 15.0
        d = beatgrid.mix_delay(out, inn, 8.0, out_trim=0.0, in_warp=1.0, in_trim=trim_in)

        t0 = 100.0 - 8.0
        a_next = beatgrid.next_beat(out["tail_beat"], t0)
        b_next = beatgrid.next_beat(inn["body_beat"], trim_in)
        b0 = b_next - trim_in
        self.assertAlmostEqual(((b0 + d) - (a_next - t0)) % P, 0.0, places=3)


class TestPlanDuration(unittest.TestCase):
    def test_accounts_for_trim_and_warp(self):
        plan = {
            "tracks": [{"duration": 100.0}, {"duration": 100.0}, {"duration": 100.0}],
            "junctions": [
                {"from": 0, "to": 1, "duration": 8.0, "trim_out": 6.5, "tempo_factor": 2.0},
                {"from": 1, "to": 2, "duration": 8.0},
            ],
        }
        # 100 + 50 + 100 = 250, minus 16 overlap, minus 6.5 trim
        self.assertAlmostEqual(render.plan_duration(plan), 227.5, places=2)


class TestPreviewWindows(unittest.TestCase):
    def test_windows_account_for_trim_warp_and_overlap(self):
        plan = {
            "tracks": [{"duration": 100.0}, {"duration": 100.0}, {"duration": 100.0}],
            "junctions": [
                # tempo_factor warps the INCOMING track (index 1 here)
                {"from": 0, "to": 1, "duration": 8.0, "trim_out": 6.5, "tempo_factor": 2.0},
                {"from": 1, "to": 2, "duration": 8.0},
            ],
        }
        w = render.junction_windows(plan, pre=0.0, post=0.0)
        # j0: cur=100 -6.5 trim -> 93.5, start 85.5, end 93.5
        self.assertAlmostEqual(w[0][0], 85.5, places=2)
        self.assertAlmostEqual(w[0][1], 93.5, places=2)
        # j1: cur = 93.5 + (100/2.0) - 8.0 = 135.5, start 127.5
        self.assertAlmostEqual(w[1][0], 127.5, places=2)
        self.assertAlmostEqual(w[1][1], 135.5, places=2)


class TestPlan(unittest.TestCase):
    @staticmethod
    def _fp(outro, intro, fade=False, fade_span=0.0, tail_span=None, trail=0.0):
        head = {"bpm": 123.0, "tempo_strength": 5.0}
        return {
            "path": "x", "duration": 100.0, "lufs_integrated": -14.0,
            "head": head, "intro_class": intro, "outro_class": outro,
            "end": {"fade": fade, "fade_span": fade_span, "trail_silence": trail},
            "tail": {"fade_span": tail_span if tail_span is not None else fade_span},
        }

    def test_unmatched_beat_mix_falls_back_to_xfade(self):
        fps = [self._fp(taxonomy.OUTRO_BEATRUN, taxonomy.INTRO_BEAT),
               self._fp(taxonomy.INTRO_BEAT, taxonomy.INTRO_BEAT)]
        p = planmod.build_plan(["a", "b"], fps, beat_align=False)
        j = p["junctions"][0]
        self.assertEqual(j["mode"], taxonomy.MODE_XFADE)
        self.assertEqual(j.get("fallback"), "beat_mix unavailable")

    def test_fade_aware_overlap_extends_duration(self):
        fps = [self._fp(taxonomy.OUTRO_FADE, taxonomy.INTRO_BEAT, fade=True, fade_span=8.8),
               self._fp(taxonomy.OUTRO_BEATRUN, taxonomy.INTRO_BEAT)]
        p = planmod.build_plan(["a", "b"], fps, beat_align=False)
        j = p["junctions"][0]
        self.assertEqual(j["mode"], taxonomy.MODE_FADE_UNDER)
        self.assertGreaterEqual(j["duration"], 8.0)
        self.assertIn("fade-aware", j["reason"])

    def test_trailing_silence_is_trimmed_from_the_overlap(self):
        # a fade-out that dies before the file ends leaves dead air; anchoring
        # the overlap to the file end puts it entirely inside that silence and
        # nothing audible crossfades ("no mix at all")
        fps = [self._fp(taxonomy.OUTRO_FADE, taxonomy.INTRO_BEAT, fade=True,
                        fade_span=8.8, trail=3.669),
               self._fp(taxonomy.OUTRO_BEATRUN, taxonomy.INTRO_BEAT)]
        p = planmod.build_plan(["a", "b"], fps, beat_align=False)
        j = p["junctions"][0]
        self.assertAlmostEqual(float(j["trim_out"]), 3.67, places=2)
        self.assertIn("trailing silence", j["reason"])

    def test_no_trim_out_when_the_ending_runs_to_the_end(self):
        fps = [self._fp(taxonomy.OUTRO_FADE, taxonomy.INTRO_BEAT, fade=True,
                        fade_span=8.8, trail=0.4),
               self._fp(taxonomy.OUTRO_BEATRUN, taxonomy.INTRO_BEAT)]
        p = planmod.build_plan(["a", "b"], fps, beat_align=False)
        self.assertIsNone(p["junctions"][0].get("trim_out"))


if __name__ == "__main__":
    unittest.main()
