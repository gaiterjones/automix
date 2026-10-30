#!/usr/bin/env bash
# End-to-end smoke test on generated (ffmpeg lavfi) tracks.
set -euo pipefail

cd "$(dirname "$0")/.."

command -v ffmpeg >/dev/null 2>&1 || { echo "ffmpeg is required for the smoke test" >&2; exit 1; }

echo "== generating synthetic tracks =="
python3 tests/make_synthetic.py

echo "== analyze =="
python3 -m automix analyze tests/audio/*.mp3 > /dev/null

echo "== plan =="
python3 -m automix plan tests/audio/*.mp3 -o /tmp/automix-smoke.plan.json > /dev/null

echo "== mix =="
python3 -m automix mix tests/audio/*.mp3 -o /tmp/automix-smoke.mix.mp3

python3 - <<'PY'
import json, os
plan = json.load(open("/tmp/automix-smoke.plan.json"))
mix = "/tmp/automix-smoke.mix.mp3"
assert len(plan["tracks"]) == 5, plan["tracks"]
assert len(plan["junctions"]) == 4, plan["junctions"]
assert all(j["mode"] in ("cut", "xfade", "beat_mix") for j in plan["junctions"])
size = os.path.getsize(mix)
assert size > 100_000, f"mix too small: {size}"
print(f"smoke ok: {mix} ({size} bytes, {len(plan['junctions'])} junctions)")
PY
