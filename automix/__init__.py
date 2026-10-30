"""automix - intelligent sequential audio mixer.

Analyses the head and tail of each track, classifies how they begin and end,
chooses a transition strategy per junction, and renders a seamless mix with
ffmpeg.

No third-party Python dependencies: analysis is ffmpeg + the standard library.

    from automix import analyze_tracks, build_plan
    from automix.render import render
"""

__version__ = "0.1.0"

# NB: do not re-export the ``render`` *function* here - it would shadow the
# ``automix.render`` submodule for ``from automix import render`` callers.
from .analysis import analyze_track, analyze_tracks   # noqa: F401
from .plan import build_plan                           # noqa: F401
