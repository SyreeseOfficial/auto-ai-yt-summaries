"""yt2obsidian: YouTube URL -> transcript note in an Obsidian vault. See PRD.md."""
import re
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


def pick_track(info):
    """URL of the best English json3 caption track (manual before auto), or None."""
    for key in ("subtitles", "automatic_captions"):
        for lang, formats in (info.get(key) or {}).items():
            if lang == "en" or lang.startswith("en-"):
                for f in formats:
                    if f.get("ext") == "json3":
                        return f["url"]
    return None


def transcript_text(track):
    """Join a json3 caption track (parsed dict) into one whitespace-collapsed string."""
    events = ("".join(s.get("utf8", "") for s in e.get("segs") or []) for e in track.get("events", []))
    return re.sub(r"\s+", " ", " ".join(events)).strip()


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
    pass


if __name__ == "__main__":
    main()
