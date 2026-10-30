"""The fixed vocabulary of beginnings/endings and the transition decision table.

This is the "intelligence" in v1: a small, explainable rule table mapping
(outro-class, intro-class) -> transition. It is meant to be edited as you listen
to real mixes; the LLM/manual planner can later replace ``decide``.
"""

# ----------------------------------------------------------------- intro ---
# how a track begins
INTRO_SILENT = "silent_lead"        # silence / pickup before anything happens
INTRO_BEAT = "beat_from_start"      # rhythm from the first bar
INTRO_PERC = "percussive_build"     # drums only / no melody
INTRO_AMBIENT = "ambient_pad"       # sustained, harmonic, beatless
INTRO_SPOKEN = "spoken"             # voice / non-rhythmic
INTRO_MELODIC = "melodic"           # melody / harmony lead-in

INTRO_CLASSES = (INTRO_SILENT, INTRO_BEAT, INTRO_PERC,
                 INTRO_AMBIENT, INTRO_SPOKEN, INTRO_MELODIC)

# ----------------------------------------------------------------- outro ---
# how a track ends
OUTRO_HARDSTOP = "hard_stop"        # abrupt stop
OUTRO_FADE = "fade_out"             # engineered fade to silence
OUTRO_BEATRUN = "beat_run"          # rhythm continues right to the end
OUTRO_BREAK = "breakdown"           # drops to near-silence, then ends
OUTRO_RING = "ring_out"             # sustained / ringing / reverb tail
OUTRO_VOCAL = "vocal_tag"           # spoken / vocal ending

OUTRO_CLASSES = (OUTRO_HARDSTOP, OUTRO_FADE, OUTRO_BEATRUN,
                 OUTRO_BREAK, OUTRO_RING, OUTRO_VOCAL)

# ---------------------------------------------------------- transitions ---
MODE_CUT = "cut"        # (near) instant, click-free hard cut
MODE_XFADE = "xfade"    # equal-power crossfade of a given length
MODE_BEAT = "beat_mix"  # crossfade intended to sit on the beat grid

# curves accepted by ffmpeg's acrossfade c1/c2
CURVES = ("tri", "qsin", "hsin", "esin", "log", "ipar",
          "qua", "cub", "squ", "cbr", "par", "exp", "lin", "sin")

DEFAULT = (MODE_XFADE, 6.0, "tri")


def decide(outro: str, intro: str) -> tuple[str, float, str]:
    """Choose (mode, duration_seconds, curve) for an outro -> intro junction."""
    rhythmic = intro in (INTRO_BEAT, INTRO_PERC)
    beatless = intro in (INTRO_SPOKEN, INTRO_AMBIENT, INTRO_SILENT)

    if outro == OUTRO_HARDSTOP:
        # an abrupt ending is already a clean cut point
        if rhythmic or intro == INTRO_SILENT:
            return (MODE_CUT, 0.05, "tri")
        return (MODE_XFADE, 3.0, "tri")

    if outro == OUTRO_FADE:
        # it is already fading - slide the next one in early over the fade
        return (MODE_XFADE, 2.0, "tri")

    if outro == OUTRO_VOCAL:
        if rhythmic:
            return (MODE_CUT, 0.05, "tri")
        return (MODE_XFADE, 4.0, "tri")

    if outro in (OUTRO_RING, OUTRO_BREAK):
        # let the tail breathe under the incoming track
        return (MODE_XFADE, 12.0, "log")

    if outro == OUTRO_BEATRUN:
        if rhythmic:
            return (MODE_BEAT, 8.0, "tri")
        if beatless:
            return (MODE_XFADE, 10.0, "tri")
        return (MODE_XFADE, 8.0, "tri")

    return DEFAULT


def explain(outro: str, intro: str) -> str:
    mode, dur, curve = decide(outro, intro)
    return f"{outro} -> {intro}: {mode} {dur}s ({curve})"
