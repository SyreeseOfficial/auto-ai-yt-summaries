"""yt2obsidian: YouTube URL -> transcript note in an Obsidian vault. See PRD.md."""
import json
import re
import subprocess
import sys
import tomllib
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ID_RE = re.compile(r"[\w-]{11}")
HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be"}
BAD_CHARS = re.compile(r'[/\\:*?"<>|#^\[\]\x00-\x1f\x7f]')
# 255-byte filesystem limit minus ".md" and a " (99)" collision suffix
MAX_NAME = 255 - len(".md") - len(" (99)")

RESTRICTED = "video is private, members-only, or age-restricted"
LIVE = "live stream or premiere, not finished; transcript not yet available"
NO_CAPS = "no captions available"


class Throttled(Exception):
    """YouTube rate-limited or bot-checked us; stop the run."""


def load_config():
    """config.toml next to this script, with defaults applied."""
    with open(Path(__file__).with_name("config.toml"), "rb") as f:
        cfg = {"timeout": 30, "retries": 3, **tomllib.load(f)}
    cfg["vault"] = Path(cfg["vault"]).expanduser()
    return cfg


def get_url(argv):
    """argv[1] if given, else the clipboard (wl-paste)."""
    if len(argv) > 1:
        return argv[1].strip()
    r = subprocess.run(["wl-paste", "--no-newline"], capture_output=True, text=True, timeout=5)
    if r.returncode or not r.stdout.strip():
        raise ValueError("clipboard is empty or not text")
    return r.stdout.strip()


def parse_url(s):
    """Return (video_id, 'video'|'short'). Raises ValueError on anything else."""
    u = urlparse(s.strip())
    host = (u.hostname or "").lower()
    if host not in HOSTS:
        raise ValueError(f"not a YouTube URL: {s!r}")
    parts = [p for p in u.path.split("/") if p]
    kind, vid = "video", None
    if host == "youtu.be":
        vid = parts[0] if parts else None
    elif parts[:1] == ["watch"]:
        vid = (parse_qs(u.query).get("v") or [None])[0]
    elif parts[:1] in (["shorts"], ["live"], ["embed"], ["v"]) and len(parts) > 1:
        vid = parts[1]
        kind = "short" if parts[0] == "shorts" else "video"
    if not vid or not ID_RE.fullmatch(vid):
        raise ValueError(f"no video id in URL: {s!r}")
    return vid, kind


def fetch(vid, cfg):
    """Video info dict from yt-dlp (no download). Raises Throttled on 429 / bot check."""
    import yt_dlp
    opts = {"quiet": True, "no_warnings": True, "skip_download": True, "noplaylist": True,
            "socket_timeout": cfg["timeout"]}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(f"https://www.youtube.com/watch?v={vid}", download=False)
    except yt_dlp.utils.DownloadError as e:
        if "429" in str(e) or "not a bot" in str(e):
            raise Throttled(str(e)) from e
        raise


def fetch_track(url, cfg):
    """Download and parse a json3 caption track."""
    try:
        with urllib.request.urlopen(url, timeout=cfg["timeout"]) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        if e.code == 429:
            raise Throttled("HTTP 429 on caption download") from e
        raise


def pick_track(info):
    """URL of the best English json3 caption track (manual before auto), or None."""
    for key in ("subtitles", "automatic_captions"):
        for lang, formats in (info.get(key) or {}).items():
            if lang == "en" or lang.startswith("en-"):
                for f in formats:
                    # tlang= marks a machine translation, not a real English track
                    if f.get("ext") == "json3" and "tlang=" not in f["url"]:
                        return f["url"]
    return None


def transcript_text(track):
    """Join a json3 caption track (parsed dict) into one whitespace-collapsed string."""
    events = ("".join(s.get("utf8", "") for s in e.get("segs") or []) for e in track.get("events", []))
    return re.sub(r"\s+", " ", " ".join(events)).strip()


# yt-dlp behavior (checked Phase 2, yt-dlp 2026.08.19):
#   live now        -> info returned, live_status == "is_live" (real: E4zB_LgD-T0)
#   no captions     -> info returned, no English track        (real: 8plwv25NYRo)
#   deleted/gone    -> DownloadError "This video is unavailable" (real: aaaaaaaaaaa)
#   private/members/age/upcoming -> NOT reproduced live; matched on yt-dlp's documented messages
#     ("Private video", "Join this channel", "Sign in to confirm your age", "Premieres in",
#     "This live event will begin"). Tests use mocked strings.
def stub_reason(info, exc=None):
    """Why there is no transcript, in PRD wording."""
    msg = str(exc).lower() if exc else ""
    if info.get("live_status") in ("is_live", "is_upcoming") or "premieres in" in msg or "live event will begin" in msg:
        return LIVE
    if (info.get("availability") in ("private", "subscriber_only", "premium_only", "needs_auth")
            or (info.get("age_limit") or 0) >= 18
            or any(k in msg for k in ("private video", "members-only", "join this channel", "age-restricted", "your age"))):
        return RESTRICTED
    if exc:
        return f"transcript fetch failed: {exc}"
    return NO_CAPS


def safe_name(title, vid):
    """Filename stem: ASCII only, no forbidden chars, capped. Falls back to video-<id>."""
    s = BAD_CHARS.sub("", (title or "").encode("ascii", "ignore").decode())
    s = re.sub(r"\s+", " ", s).strip(" .")[:MAX_NAME].strip(" .")
    return s or f"video-{vid}"


def render(info, vid, text=None, reason=None):
    """Note body per PRD 7.4. Stub when text is falsy."""
    title = info.get("title") or vid
    d = info.get("upload_date") or ""
    date = f"{d[:4]}-{d[4:6]}-{d[6:]}" if len(d) == 8 else "unknown"
    channel = info.get("channel") or info.get("uploader") or "unknown"
    url = f"https://www.youtube.com/watch?v={vid}"
    if text:
        label = title.replace("[", "(").replace("]", ")")
        return f"[{label}]({url})\nChannel: {channel}\nDate: {date}\n\n{text}\n"
    return f"[YouTube]({url})\nTitle: {title}\nChannel: {channel}\nDate: {date}\n\nNo transcript: {reason or NO_CAPS}\n"


def main():
    # Phase 2 scratch: print what we'd write, no file output yet.
    cfg = load_config()
    vid, kind = parse_url(get_url(sys.argv))
    info = fetch(vid, cfg)
    url = pick_track(info)
    text = transcript_text(fetch_track(url, cfg)) if url else None
    print({k: info.get(k) for k in ("title", "channel", "upload_date", "live_status", "availability", "age_limit")})
    print("track:", bool(url), "| reason:", None if text else stub_reason(info))
    print((text or "")[:300])


if __name__ == "__main__":
    main()
