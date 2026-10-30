"""automix command line interface.

    automix analyze a.mp3 b.mp3          # -> JSON fingerprints
    automix plan    a.mp3 b.mp3          # -> mix.plan.json (no audio)
    automix mix      a.mp3 b.mp3 -o out.mp3
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from . import analysis, plan as planmod, render, taxonomy


def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def _analyze(tracks, window):
    out = []
    for i, path in enumerate(tracks, 1):
        _log(f"[{i}/{len(tracks)}] analysing {os.path.basename(path)} ...")
        out.append(analysis.analyze_track(path, window=window))
    return out


def cmd_analyze(args) -> int:
    fps = _analyze(args.tracks, args.window)
    text = json.dumps(fps, indent=2)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
    print(text)
    return 0


def cmd_plan(args) -> int:
    fps = _analyze(args.tracks, args.window)
    plan = planmod.build_plan(args.tracks, fps, target_lufs=args.target_lufs,
                              window=args.window, beat_align=args.beat_align)
    planmod.dump_plan(plan, args.output)
    _log(f"plan written to {args.output}")
    print(json.dumps(plan, indent=2))
    return 0


def cmd_mix(args) -> int:
    fps = _analyze(args.tracks, args.window)
    plan = planmod.build_plan(args.tracks, fps, target_lufs=args.target_lufs,
                              window=args.window, beat_align=args.beat_align)

    _log("\njunctions:")
    for j in plan["junctions"]:
        align = f"  +beat-align {j['delay'] * 1000:.0f}ms" if j.get("align") == "beat" else ""
        _log(f"  {j['from']+1} -> {j['to']+1}: {j['mode']} {j['duration']}s "
             f"({j['curve']}){align}  [{j['reason']}]")
    _log(f"expected length: {render.plan_duration(plan)}s\n")

    if args.plan_out:
        planmod.dump_plan(plan, args.plan_out)

    _log(f"rendering -> {args.output}")
    render.render(plan, args.output, bitrate=args.bitrate)
    got = analysis.ffmpeg.ffprobe_metadata(args.output).get("duration")
    _log(f"done: {args.output}  ({got}s)")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="automix",
                                description="Intelligent sequential audio mixer")
    p.add_argument("--version", action="version", version="automix 0.1.0")
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("analyze", help="fingerprint tracks as JSON")
    a.add_argument("tracks", nargs="+")
    a.add_argument("--window", type=float, default=30.0)
    a.add_argument("-o", "--output")
    a.set_defaults(func=cmd_analyze)

    pl = sub.add_parser("plan", help="build a mix plan (no rendering)")
    pl.add_argument("tracks", nargs="+")
    pl.add_argument("--window", type=float, default=30.0)
    pl.add_argument("--target-lufs", type=float, default=-14.0)
    pl.add_argument("--beat-align", action=argparse.BooleanOptionalAction, default=False,
                    help="nudge the incoming track so beats align on beat_mix junctions (default: off)")
    pl.add_argument("-o", "--output", default="mix.plan.json")
    pl.set_defaults(func=cmd_plan)

    m = sub.add_parser("mix", help="analyze, plan and render a mix")
    m.add_argument("tracks", nargs="+")
    m.add_argument("-o", "--output", default="mix.mp3")
    m.add_argument("--window", type=float, default=30.0)
    m.add_argument("--target-lufs", type=float, default=-14.0)
    m.add_argument("--beat-align", action=argparse.BooleanOptionalAction, default=False,
                   help="nudge the incoming track so beats align on beat_mix junctions (default: off)")
    m.add_argument("--plan-out")
    m.add_argument("--bitrate", default="320k")
    m.set_defaults(func=cmd_mix)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
