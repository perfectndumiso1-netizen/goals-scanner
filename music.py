"""The one music bed every PlayReport video uses (user rule 2026-10-21: no narration at all).

Every video — the 16:9 shortlist briefing, the 9:16 reel and the match breakdown, in both aspect ratios — is
silent apart from one track: `assets/reel/under_the_stadium_lights.mp3`, the user's own file. It loops for the
whole video, fades in at the head and out at the tail, and is loudness-normalised to a background level so it
never competes with the picture.

Slide timing used to come from the length of each voice clip. With no voice, it comes from how long the slide's
own words take to read (`reading_seconds`), measured at the pace the narration used to speak them (~2.6 words per
second), so the videos keep the length and the rhythm they had. `REEL_READ_WPS` tunes it without a code change.
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
from pathlib import Path

log = logging.getLogger("scanner")

MUSIC_FILE = "under_the_stadium_lights.mp3"
FADE_IN = 1.5                  # seconds of fade at the head
FADE_OUT = 2.5                 # seconds of fade at the tail
BED_LUFS = -18.0               # integrated loudness of the bed (a background level, not a music video)
READ_WPS = float(os.environ.get("REEL_READ_WPS", "2.6"))   # words per second: the old narration's speaking pace
MIN_SLIDE = 2.6                # no slide flashes past, even a two-word one
MAX_SLIDE = 40.0               # a long recap page still moves on

_WORD = re.compile(r"[A-Za-z0-9']+")


def music_path(assets: Path) -> Path:
    """The committed track next to the backgrounds and the logo."""
    return Path(assets) / MUSIC_FILE


def words(text: str) -> int:
    return len(_WORD.findall(str(text or "")))


def reading_seconds(text: str, *, wps: float | None = None) -> float:
    """How long a slide's words take to read at the house pace, clamped so no slide is too short or too long."""
    pace = float(wps or READ_WPS or 2.6)
    if pace <= 0:
        pace = 2.6
    secs = words(text) / pace
    return max(MIN_SLIDE, min(MAX_SLIDE, secs))


def bed(duration: float, dest: Path, ff: str, *, assets: Path | None = None, music: Path | None = None) -> Path:
    """Build the audio track of a whole video: the one track, looped to `duration`, faded, normalised.

    Returns `dest`. Raises when the track is missing — a video without its music is never published silently.
    """
    src = Path(music) if music else music_path(Path(assets) if assets else Path("assets/reel"))
    if not src.exists():
        raise FileNotFoundError(f"music bed missing: {src}")
    duration = max(1.0, float(duration))
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    fade_out_start = max(0.0, duration - min(FADE_OUT, duration / 3))
    graph = (f"afade=t=in:st=0:d={min(FADE_IN, duration / 4):.2f},"
             f"afade=t=out:st={fade_out_start:.2f}:d={duration - fade_out_start:.2f},"
             f"loudnorm=I={BED_LUFS}:TP=-2:LRA=11")
    cmd = [ff, "-y", "-stream_loop", "-1", "-i", str(src), "-t", f"{duration:.3f}",
           "-af", graph, "-ar", "44100", "-ac", "2", str(dest)]
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if r.returncode != 0 or not dest.exists():
        # loudnorm is the only fragile part; a plain fade is still the same track, just without the normalisation
        log.info("music bed loudnorm unavailable, using plain fades: %s", r.stdout[-300:])
        graph = (f"afade=t=in:st=0:d={min(FADE_IN, duration / 4):.2f},"
                 f"afade=t=out:st={fade_out_start:.2f}:d={duration - fade_out_start:.2f}")
        r = subprocess.run([ff, "-y", "-stream_loop", "-1", "-i", str(src), "-t", f"{duration:.3f}",
                            "-af", graph, "-ar", "44100", "-ac", "2", str(dest)],
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        if r.returncode != 0 or not dest.exists():
            raise RuntimeError(f"music bed failed:\n{r.stdout[-1200:]}")
    log.info("music bed %.1fs from %s", duration, src.name)
    return dest


def mux(video: Path, audio: Path, out: Path, ff: str, *, bitrate: str = "160k") -> Path:
    """Picture from `video`, sound from `audio`, no re-encode of the picture."""
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run([ff, "-y", "-i", str(video), "-i", str(audio), "-map", "0:v", "-map", "1:a",
                        "-c:v", "copy", "-c:a", "aac", "-b:a", bitrate, "-movflags", "+faststart", str(out)],
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if r.returncode != 0 or not out.exists():
        raise RuntimeError(f"mux failed:\n{r.stdout[-1200:]}")
    return out
