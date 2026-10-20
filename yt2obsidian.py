"""yt2obsidian: YouTube URL -> transcript note in an Obsidian vault. See PRD.md."""
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import tomllib
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

import yt_dlp

HERE = Path(__file__).parent
LOG = HERE / "run.log"
RETRY = HERE / "retry.txt"
RETRY_DELAY = 2  # seconds, times attempt number
TOGGLES = {  # config key -> menu label, all default on
    "open_obsidian": "Open the note in Obsidian after saving",
    "notify": "Desktop notifications",
}
THROTTLE = ("http error 429", "not a bot", "rate-limited", "try again later")
USAGE = """usage: yt2obsidian.py [URL]   save a transcript (no URL: read the clipboard)
       yt2obsidian.py -i       interactive prompt (or run ./yt)
       yt2obsidian.py -h       this help"""
NET_RE = re.compile(r"unable to download|timed out|connection|resolution|network is unreachable|name or service", re.I)
ID_RE = re.compile(r"[A-Za-z0-9_-]{11}")
HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be"}
BAD_CHARS = re.compile(r'[/\\:*?"<>|#^\[\]\x00-\x1f\x7f]')
# 255-byte filesystem limit minus ".md" and a " (99)" collision suffix
MAX_NAME = 255 - len(".md") - len(" (99)")

RESTRICTED = "video is private, members-only, or age-restricted"
LIVE = "live stream or premiere, not finished; transcript not yet available"
NO_CAPS = "no captions available"


class Quiet:
    """yt-dlp logger that prints nothing; errors still raise DownloadError."""
    def debug(self, msg): pass
    info = warning = error = debug


class Throttled(Exception):
    """Throttled, bot-checked, or network down after retries: stop the run, queue the URL."""


def load_config():
    """config.toml next to this script, with defaults applied. Raises ValueError naming the problem."""
    path = HERE / "config.toml"
    try:
        with open(path, "rb") as f:
            cfg = {"timeout": 30, "retries": 3, **{k: True for k in TOGGLES}, **tomllib.load(f)}
    except FileNotFoundError:
        raise ValueError(f"{path} not found; copy config.example.toml to config.toml") from None
    except tomllib.TOMLDecodeError as e:
        raise ValueError(f"{path}: {e}") from e
    for k in ("vault", "inbox"):
        if k not in cfg:
            raise ValueError(f"{path}: missing {k!r}")
    for k in TOGGLES:
        if not isinstance(cfg[k], bool):
            raise ValueError(f"{path}: {k} must be true or false")
    cfg["vault"] = Path(cfg["vault"]).expanduser()
    if not cfg["vault"].is_dir():
        raise ValueError(f"{path}: vault is not a folder: {cfg['vault']}")
    return cfg


def set_toggle(key, value):
    """Rewrite `key = value` in config.toml, keeping comments; append if absent."""
    path = HERE / "config.toml"
    line = f"{key} = {str(value).lower()}"
    text = path.read_text()
    text, n = re.subn(rf"^{key}\s*=\s*\S+", line, text, flags=re.M)
    path.write_text(text if n else text.rstrip("\n") + "\n" + line + "\n")


def settings_menu():
    """Numbered on/off toggles; Enter returns to the prompt."""
    while True:
        cfg = load_config()
        keys = list(TOGGLES)
        print("\nSettings (number toggles, Enter to go back)")
        for i, k in enumerate(keys, 1):
            print(f"  {i}. [{'x' if cfg[k] else ' '}] {TOGGLES[k]}")
        try:
            pick = input("settings> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not pick:
            return
        if pick.isdigit() and 1 <= int(pick) <= len(keys):
            set_toggle(keys[int(pick) - 1], not cfg[keys[int(pick) - 1]])


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
    opts = {"logger": Quiet(), "skip_download": True, "noplaylist": True, "socket_timeout": cfg["timeout"]}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(f"https://www.youtube.com/watch?v={vid}", download=False)
    except yt_dlp.utils.DownloadError as e:
        if any(k in str(e).lower() for k in THROTTLE):
            raise Throttled(str(e)) from e
        raise


def with_retries(fn, cfg):
    """Call fn, retrying network errors cfg['retries'] times. Exhausted -> Throttled; other errors pass through."""
    for attempt in range(1, cfg["retries"] + 1):
        try:
            return fn()
        except Throttled:
            raise
        except (yt_dlp.utils.DownloadError, OSError) as e:
            if isinstance(e, yt_dlp.utils.DownloadError):
                net = bool(NET_RE.search(str(e)))
            else:  # 4xx on a caption URL is final; timeouts, URLError and 5xx are worth retrying
                net = not (isinstance(e, urllib.error.HTTPError) and e.code < 500)
            if not net:
                raise
            if attempt == cfg["retries"]:
                raise Throttled(f"network failure after {attempt} tries: {e}") from e
            print(f"Retrying ({attempt + 1}/{cfg['retries']})...")
            time.sleep(RETRY_DELAY * attempt)


def fetch_track(url, cfg):
    """Download and parse a json3 caption track."""
    try:
        with urllib.request.urlopen(url, timeout=cfg["timeout"]) as r:
            return json.load(r)
    except ValueError as e:  # HTML error page, truncated body
        raise ValueError(f"caption download was not valid JSON: {e}") from e
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
                    if f.get("ext") == "json3" and f.get("url") and "tlang=" not in f["url"]:
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
    msg = re.sub(r"^ERROR: (\[youtube\] \S+: )?", "", str(exc)) if exc else ""
    low = msg.lower()
    if info.get("live_status") in ("is_live", "is_upcoming") or "premieres in" in low or "live event will begin" in low:
        return LIVE
    if (info.get("availability") in ("private", "subscriber_only", "premium_only", "needs_auth")
            or (info.get("age_limit") or 0) >= 18
            or any(k in low for k in ("private video", "members-only", "join this channel", "age-restricted", "your age"))):
        return RESTRICTED
    if exc:
        return f"transcript fetch failed: {msg}"
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
        label = re.sub(r"([*_])", r"\\\1", title.replace("[", "(").replace("]", ")"))
        return f"[{label}]({url})\nChannel: {channel}\nDate: {date}\n\n{text}\n"
    return f"[YouTube]({url})\nTitle: {title}\nChannel: {channel}\nDate: {date}\n\nNo transcript: {reason or NO_CAPS}\n"


def find_existing(inbox, vid):
    """Path of a note for this video (matched on the URL in its first 1 KB), or None."""
    needle = f"youtube.com/watch?v={vid}"
    for p in Path(inbox).glob("*.md"):
        with open(p, encoding="utf-8", errors="replace") as f:
            if needle in f.read(1024):
                return p
    return None


def is_stub(path):
    """True for a no-transcript note (its second line is `Title:`, a real note's is `Channel:`)."""
    lines = Path(path).read_text(encoding="utf-8", errors="replace").split("\n", 2)
    return len(lines) > 1 and lines[1].startswith("Title: ")


def write_atomic(inbox, name, body):
    """Write body to inbox/<name>.md via temp file + hard link. Never overwrites; numbers on clash."""
    inbox = Path(inbox)
    inbox.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=inbox, prefix=".yt2obsidian-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(body)
        os.chmod(tmp, 0o644)  # mkstemp makes it 0600
        for n in range(1, 100):
            dest = inbox / (f"{name}.md" if n == 1 else f"{name} ({n}).md")
            try:
                os.link(tmp, dest)  # atomic, fails if dest exists
                return dest
            except FileExistsError:
                continue
        raise OSError(f"too many name clashes for {name!r}")
    finally:
        os.unlink(tmp)


def notify(msg):
    try:  # fire and forget: a missing notification daemon must not stall the prompt
        subprocess.Popen(["notify-send", "yt2obsidian", msg], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        pass


def open_obsidian(vault, path):
    rel = Path(path).relative_to(vault).as_posix()
    uri = f"obsidian://open?vault={quote(Path(vault).name, safe='')}&file={quote(rel, safe='')}"
    try:
        subprocess.Popen(["xdg-open", uri], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        pass


def log_run(url, outcome, err=""):
    url, err = (re.sub(r"\s+", " ", str(x)).strip() for x in (url, err))  # one row per run, tab-separated
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now().isoformat(timespec='seconds')}\t{url}\t{outcome}\t{err}\n")
    except OSError:
        pass  # a full disk must not hide the run's real outcome


def queue_retry(url):
    try:
        seen = RETRY.read_text().split() if RETRY.exists() else []
        if url not in seen:
            with open(RETRY, "a") as f:
                f.write(url + "\n")
    except OSError:
        pass


def main(argv=None, cfg=None):
    url = ""

    def ping(msg):
        if (cfg or {}).get("notify", True):
            notify(msg)

    def done(outcome, msg, code=0, err=""):
        print(msg)
        log_run(url, outcome, err)
        if code:
            ping(msg)
        return code

    try:
        cfg = cfg or load_config()
        inbox = cfg["vault"] / cfg["inbox"]
        url = get_url(argv if argv is not None else sys.argv)
        vid, kind = parse_url(url)
        if kind == "short":
            return done("skipped", f"Skipped: Shorts are not processed ({vid})")
        if (old := find_existing(inbox, vid)):
            return done("duplicate", f"Already saved: {old}" + (" (stub, delete it to retry)" if is_stub(old) else ""))

        canonical = f"https://www.youtube.com/watch?v={vid}"
        exc = None
        try:
            try:
                info = with_retries(lambda: fetch(vid, cfg), cfg)
            except yt_dlp.utils.DownloadError as e:  # private, members-only...: stub
                if "video is unavailable" in str(e).lower():  # deleted or mistyped ID: nothing to save
                    return done("failed", f"Error: video unavailable ({vid})", 1, str(e))
                info, exc = {}, e
            track = pick_track(info)
            text = transcript_text(with_retries(lambda: fetch_track(track, cfg), cfg)) if track else None
        except Throttled as e:
            queue_retry(canonical)
            return done("failed", f"Stopped: {e}\nQueued in {RETRY.name}: {canonical}", 2, str(e))

        reason = None if text else stub_reason(info, exc)
        path = write_atomic(inbox, safe_name(info.get("title"), vid), render(info, vid, text, reason))
        msg = f"Saved: {path}" if text else f"Saved stub ({reason}): {path}"
        print(msg)
        log_run(url, "saved" if text else "stub", reason or "")
        ping(f"Saved: {path.stem}" + ("" if text else f" (stub: {reason})"))
        if cfg.get("open_obsidian", True):
            open_obsidian(cfg["vault"], path)
        return 0
    except KeyboardInterrupt:
        print("Cancelled")
        log_run(url, "cancelled")
        return 1
    except (ValueError, OSError, subprocess.SubprocessError) as e:  # bad input, config, disk, clipboard
        return done("failed", f"Error: {e}", 1, str(e))
    except Exception as e:  # anything else must still end in a log row, not a traceback
        return done("failed", f"Error: {type(e).__name__}: {e}", 1, f"{type(e).__name__}: {e}")


def repl():
    """Paste a link, press Enter, repeat. Ctrl-D, Ctrl-C or 'q' quits."""
    print("Paste a YouTube link and press Enter (s = settings, q = quit)")
    try:
        load_config()
    except ValueError as e:
        print(f"Config problem: {e}")
    while True:
        try:
            line = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if line in ("q", "quit", "exit"):
            return 0
        if line in ("s", "settings"):
            try:
                settings_menu()
            except ValueError as e:
                print(f"Config problem: {e}")
        elif line:
            main(["", line])


def cli(args):
    if args == ["-i"]:
        return repl()
    if args[:1] in (["-h"], ["--help"]):
        print(USAGE)
        return 0
    if args[:1] and args[0].startswith("-"):
        print(USAGE, file=sys.stderr)
        return 1
    return main()


if __name__ == "__main__":
    sys.exit(cli(sys.argv[1:]))
