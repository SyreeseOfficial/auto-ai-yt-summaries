"""yt2obsidian: YouTube URL -> transcript note in an Obsidian vault. See PRD.md."""
import fcntl
import json
import os
import re
import readline
import signal
import subprocess
import sys
import time
import tomllib
import unicodedata
from collections import Counter, namedtuple
from datetime import datetime
from importlib.metadata import version
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

import yt_dlp
from yt_dlp.networking.exceptions import HTTPError, RequestError, TransportError

HERE = Path(__file__).resolve().parent
LOG = HERE / "run.log"
RETRY = HERE / "retry.txt"
LOCK = HERE / ".lock"
HISTORY = HERE / ".history"
RETRY_DELAY = 2  # seconds, times attempt number
SETTINGS = {  # config key -> (menu label, default, allowed): bool, a {choice: note} dict, int, or str
    "open_obsidian": ("Open the note in Obsidian after saving", True, bool),
    "notify": ("Desktop notifications", "auto", {"auto": "only when no terminal is attached", "always": "even at the prompt", "never": "off"}),
    "inbox": ("Inbox folder inside the vault", None, str),
    "timeout": ("Seconds to wait per fetch", 15, int),
    "retries": ("Attempts per fetch", 3, int),
}
THROTTLE = ("http error 429", "not a bot", "rate-limited", "try again later")
FLAGS = ("--retry", "--no-open", "--no-notify")
USAGE = """usage: yt2obsidian.py [URL]   save a transcript (no URL: prompt in a terminal, else read the clipboard)
       yt2obsidian.py -i       interactive prompt (or run ./yt; ./yt URL saves one link)
       yt2obsidian.py --retry  save the links waiting in retry.txt, stop at the first throttle
       yt2obsidian.py --settings  settings menu only
       yt2obsidian.py -h       this help
options for a URL or --retry run: --no-open (skip Obsidian), --no-notify (no toasts)
exit codes: 0 ok (saved, stub, duplicate, skipped), 1 bad input or failure, 2 stopped (throttled or network down, URL queued)"""
HELP = """  <link>  save a transcript; several links (one per line or space-separated) are saved in turn
          Enter alone: use the clipboard
  o       open the last saved note in Obsidian
  l       list the last 5 saved notes
  r       retry the links waiting in retry.txt
  undo    delete the note saved last in this session
  u       update yt-dlp
  s       settings
  ?       this help
  q       quit"""
SUMMARY = ("saved", "stub", "duplicate", "skipped", "failed", "stopped")
LOG_AS = {"stopped": "failed", "invalid": "failed"}  # run.log keeps its old outcome names
ID_RE = re.compile(r"[A-Za-z0-9_-]{11}")
HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be",
         "youtube-nocookie.com", "www.youtube-nocookie.com"}
NOT_VIDEO = {"playlist": "playlists are not supported", "clip": "clip links are not supported",
             "channel": "that is a channel, paste a video link", "c": "that is a channel, paste a video link",
             "user": "that is a channel, paste a video link"}
KEEP = re.compile(r"[^A-Za-z0-9 '(),.&!+=@$%~_-]")  # allowlist: everything else is dropped
PUNCT = str.maketrans("\u2018\u2019\u201c\u201d\u2013\u2014", "''\"\"--")
# 255-byte filesystem limit minus ".md" and a " (99)" collision suffix
MAX_NAME = 255 - len(".md") - len(" (99)")

RESTRICTED = "video is private, members-only, or age-restricted"
LIVE = "live stream or premiere, not finished; transcript not yet available"
NO_CAPS = "no captions available"
TOAST_REASON = {RESTRICTED: "restricted", LIVE: "live or upcoming", NO_CAPS: "no captions"}


class Quiet:
    """yt-dlp logger that prints nothing; errors still raise DownloadError."""
    def debug(self, msg): pass
    info = warning = error = debug


class Stop(Exception):
    """Stop the run and queue the URL."""
    def __init__(self, msg, short=None):
        super().__init__(msg)
        self.short = short  # one-line version for the screen; the full text goes to run.log


Result = namedtuple("Result", "code outcome path title", defaults=(None, None))


def load_config():
    """config.toml next to this script, with defaults applied. Raises ValueError naming the problem."""
    path = HERE / "config.toml"
    try:
        with open(path, "rb") as f:
            cfg = {**{k: d for k, (_, d, _) in SETTINGS.items() if d is not None}, **tomllib.load(f)}
    except FileNotFoundError:
        raise ValueError(f"{path} not found; copy config.example.toml to config.toml") from None
    except tomllib.TOMLDecodeError as e:
        raise ValueError(f"{path}: {e}") from e
    for k in ("vault", "inbox"):
        if k not in cfg:
            raise ValueError(f"{path}: missing {k!r}")
    if isinstance(cfg["notify"], bool):  # the old on/off form
        cfg["notify"] = "auto" if cfg["notify"] else "never"
    for k, (_, _, allowed) in SETTINGS.items():
        if allowed is bool and not isinstance(cfg[k], bool):
            raise ValueError(f"{path}: {k} must be true or false")
        if isinstance(allowed, dict) and cfg[k] not in allowed:
            raise ValueError(f"{path}: {k} must be {', '.join(allowed)}")
        if allowed is int and not (isinstance(cfg[k], int) and not isinstance(cfg[k], bool) and cfg[k] >= 1):
            raise ValueError(f"{path}: {k} must be a whole number, 1 or more")
    cfg["vault"] = Path(cfg["vault"]).expanduser()
    if not cfg["vault"].is_absolute():  # a hotkey run starts in $HOME, so "relative" would mean another place
        raise ValueError(f"{path}: vault must be an absolute path (or start with ~): {cfg['vault']}")
    if not cfg["vault"].is_dir():
        raise ValueError(f"{path}: vault is not a folder: {cfg['vault']}")
    try:
        check_inbox(cfg["inbox"])
    except ValueError as e:
        raise ValueError(f"{path}: inbox {e}") from None
    return cfg


def edit_config(fn):
    """Apply fn(text) -> text to config.toml via a temp file + os.replace, so a crash can't truncate it."""
    path = HERE / "config.toml"
    tmp = path.with_suffix(".toml.tmp")
    tmp.write_text(fn(path.read_text(encoding="utf-8")), encoding="utf-8")
    os.replace(tmp, path)


def toml_line(key, value):
    return f"{key} = {json.dumps(value, ensure_ascii=False)}"  # JSON bool/int/string syntax is valid TOML


def put_line(text, key, value):
    """text with `key = value` rewritten in place (trailing comment kept), or None if the key is absent."""
    new, n = re.subn(rf'^{key}\s*=\s*("(?:[^"\\]|\\.)*"|[^\s#]+)', lambda m: toml_line(key, value), text, flags=re.M)
    return new if n else None


def set_value(key, value):
    """Rewrite `key = value` in config.toml, keeping comments; append if absent."""
    edit_config(lambda text: put_line(text, key, value) or text.rstrip("\n") + "\n" + toml_line(key, value) + "\n")


def reset_settings():
    """Put every setting that has a default back to it (inbox has none). Keys not in the file stay absent."""
    def put(text):
        for k, (_, default, _) in SETTINGS.items():
            if default is not None:
                text = put_line(text, k, default) or text
        return text

    edit_config(put)


def check_inbox(raw):
    """raw if it is a folder name inside the vault; a leading / or .. would save outside it."""
    if not isinstance(raw, str) or not raw or Path(raw).is_absolute() or ".." in Path(raw).parts:
        raise ValueError("must be a relative folder name (no leading / and no ..)")
    return raw


def parse_setting(key, raw):
    """Typed value for text typed into the menu. Raises ValueError with a message for the user."""
    raw = raw.strip()
    if SETTINGS[key][2] is int:
        if not raw.isdigit() or int(raw) < 1:
            raise ValueError("must be a whole number, 1 or more")
        return int(raw)
    return check_inbox(raw)


def show_setting(key, v):
    allowed = SETTINGS[key][2]
    if allowed is bool:
        return "on" if v else "off"
    return f"{v} ({allowed[v]})" if isinstance(allowed, dict) else str(v)


def unknown_keys(cfg):
    return sorted(set(cfg) - {"vault", *SETTINGS})


def settings_menu():
    """Numbered settings: on/off flips, choices cycle, values are typed. Enter, q or b returns to the prompt."""
    keys = list(SETTINGS)
    while True:
        try:
            cfg = load_config()
            print(f"\nSettings  {HERE / 'config.toml'}\n  vault: {cfg['vault']}")
            if bad := unknown_keys(cfg):
                print(f"  warning: unknown keys ignored: {', '.join(bad)}")
            for i, k in enumerate(keys, 1):
                label, _, allowed = SETTINGS[k]
                print(f"  {i}. [{'x' if cfg[k] else ' '}] {label}" if allowed is bool else f"  {i}. {label}: {show_setting(k, cfg[k])}")
            pick = ask("Number changes a setting, d resets, Enter goes back\nsettings> ")
            if pick is None or pick.lower() in ("", "q", "b"):
                return
            pick = pick.lower()
            if pick == "d":
                reset_settings()
                print("settings reset to defaults (inbox kept)")
            elif pick.isdigit() and 1 <= int(pick) <= len(keys):
                k = keys[int(pick) - 1]
                label, _, allowed = SETTINGS[k]
                if allowed is bool:
                    new = not cfg[k]
                elif isinstance(allowed, dict):
                    opts = list(allowed)
                    new = opts[(opts.index(cfg[k]) + 1) % len(opts)]
                else:
                    raw = ask(f"{label} [{cfg[k]}], new value (Enter keeps it): ")
                    if raw is None:
                        return
                    if not raw:
                        continue
                    try:
                        new = parse_setting(k, raw)
                    except ValueError as e:
                        print(f"{label} {e}")
                        continue
                set_value(k, new)
                print(f"{label}: {show_setting(k, new)}")
            else:
                print(f"pick 1-{len(keys)}, d, or Enter")
        except (ValueError, OSError) as e:
            print(f"Config problem: {cap(e)}")
            return


def ask(prompt):
    """Stripped input, or None on Ctrl-D / Ctrl-C."""
    try:
        return input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        print()


def clean(s):
    """One line, no control characters (titles and yt-dlp errors can carry escape sequences)."""
    return re.sub(r"[\s\x00-\x1f\x7f-\x9f]+", " ", str(s)).strip()


def cap(s, n=200):
    s = clean(s)
    return s if len(s) <= n else s[:n - 1] + "…"


def rel(path, vault):
    try:
        return str(Path(path).relative_to(vault))
    except ValueError:
        return str(path)


def at_terminal():
    return sys.stdin.isatty()


def get_url(args):
    """args[0] if given, else the clipboard (wl-paste)."""
    return args[0].strip() if args else clipboard()


def clipboard():
    r = subprocess.run(["wl-paste", "--no-newline", "--type", "text"], capture_output=True, text=True, timeout=5)
    if r.returncode or not r.stdout.strip():
        raise ValueError("clipboard is empty or not text")
    return r.stdout.strip()


def parse_url(s):
    """Return (video_id, is_short). Raises ValueError on anything else."""
    t = s.strip().strip("<>()[]\"'").rstrip(".,;!?")  # pasted from chat: wrapped, trailing punctuation
    u = urlparse(t if "://" in t else "https://" + t)
    host = u.hostname or ""
    if host not in HOSTS:
        raise ValueError(f"not a YouTube URL: {s[:60]!r}")
    parts = [p for p in u.path.split("/") if p]
    vid, short = None, False
    if host == "youtu.be":
        vid = parts[0] if parts else None
    elif parts and (parts[0].startswith("@") or parts[0] in NOT_VIDEO):
        raise ValueError(NOT_VIDEO.get(parts[0], NOT_VIDEO["channel"]))
    elif parts[:1] == ["watch"]:
        vid = (parse_qs(u.query).get("v") or [None])[0]
    elif parts[:1] in (["shorts"], ["live"], ["embed"], ["v"]) and len(parts) > 1:
        vid, short = parts[1], parts[0] == "shorts"
    if not vid or not ID_RE.fullmatch(vid):
        raise ValueError(f"no video id in URL: {s[:60]!r}")
    return vid, short


def watch_url(vid):
    return f"https://www.youtube.com/watch?v={vid}"


def fetch(vid, timeout):
    """Video info dict from yt-dlp (no download). Raises Stop on 429 / bot check."""
    opts = {"logger": Quiet(), "socket_timeout": timeout}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(watch_url(vid), download=False)
    except yt_dlp.utils.DownloadError as e:
        if any(k in str(e).lower() for k in THROTTLE):
            raise Stop(str(e), "throttled by YouTube") from e
        raise


def transient(e):
    """Timeouts, dropped connections and 5xx are worth retrying; a 4xx is final."""
    if isinstance(e, yt_dlp.utils.DownloadError):  # yt-dlp keeps the original error here
        e = e.exc_info[1] if e.exc_info else None
    return e.status >= 500 if isinstance(e, HTTPError) else isinstance(e, TransportError)


def with_retries(fn, retries):
    """Call fn, retrying network errors up to `retries` attempts. Exhausted -> Stop; other errors pass through."""
    for attempt in range(1, retries + 1):
        try:
            return fn()
        except Stop:
            raise
        except (yt_dlp.utils.DownloadError, RequestError) as e:
            if not transient(e):
                raise
            if attempt == retries:
                raise Stop(f"network failure after {attempt} tries: {e}", "network down or unreachable") from e
            print(f"Retrying ({attempt + 1}/{retries})...")
            time.sleep(RETRY_DELAY * attempt)


def fetch_track(url, timeout):
    """Download and parse a json3 caption track."""
    with yt_dlp.YoutubeDL({"logger": Quiet(), "socket_timeout": timeout}) as ydl:
        try:
            return json.load(ydl.urlopen(url))
        except ValueError as e:  # HTML error page, truncated body
            raise ValueError(f"caption download was not valid JSON: {e}") from e
        except HTTPError as e:
            if e.status == 429:
                raise Stop("HTTP 429 on caption download", "throttled by YouTube") from e
            raise


def pick_track(info):
    """URL of the best English json3 caption track (manual before auto), or None."""
    for key in ("subtitles", "automatic_captions"):
        tracks = info.get(key) or {}
        for lang in sorted(tracks, key=lambda k: k != "en"):  # plain `en` before en-US, en-orig...
            if lang == "en" or lang.startswith("en-"):
                for f in tracks[lang]:
                    # tlang= marks a machine translation, not a real English track
                    if f.get("ext") == "json3" and f.get("url") and "tlang=" not in f["url"]:
                        return f["url"]
    return None


def transcript_text(track):
    """Join a json3 caption track (parsed dict) into one string: sound tags (`[Music]`, `[ __ ]`) and `♪` dropped,
    a blank line at each `>>` speaker change."""
    events = ("".join(s.get("utf8", "") for s in e.get("segs") or []) for e in track.get("events", []))
    text = re.sub(r"\[[^\]]*\]|♪", " ", " ".join(events))  # real tracks only use brackets for sounds and censoring
    return re.sub(r" ?>> ?", "\n\n", re.sub(r"\s+", " ", text)).strip()


# yt-dlp 2026.08.19, real runs: live now -> info with live_status "is_live"; no captions -> info with no
# English track; deleted ID -> DownloadError "This video is unavailable". Private, members-only, age-gated and
# upcoming are not reproduced; matched on yt-dlp's documented messages, tests use mocked strings.
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
    # manual tracks and original-language auto tracks; the auto list also holds every machine translation
    others = [k for k in (info.get("subtitles") or {}) if not k.startswith("en")]
    others += [k for k in (info.get("automatic_captions") or {}) if k.endswith("-orig") and not k.startswith("en")]
    return f"no English captions (found: {', '.join(others[:5])})" if others else NO_CAPS


def safe_name(title, vid, channel=""):
    """Filename stem: accents folded, ASCII allowlist, capped. Falls back to <channel> video-<id>."""
    def clean(t):
        t = unicodedata.normalize("NFKD", (t or "").translate(PUNCT))
        return re.sub(r"\s+", " ", KEEP.sub("", t)).strip(" .,;-_")[:MAX_NAME].strip(" .,;-_")
    return clean(title) or clean(f"{channel or ''} video-{vid}")


def render(info, vid, text=None, reason=None):
    """Note body per PRD 7.4. Stub when text is falsy."""
    title = info.get("title") or vid
    d = info.get("upload_date") or ""
    date = f"{d[:4]}-{d[4:6]}-{d[6:]}" if len(d) == 8 else "unknown"
    meta = f"Channel: {info.get('channel') or info.get('uploader') or 'unknown'}\nDate: {date}\n"
    if secs := info.get("duration"):  # live and upcoming videos have none
        h, m = divmod(int(secs) // 60, 60)
        meta += f"Duration: {f'{h}:{m:02}' if h else m}:{int(secs) % 60:02}\n"
    meta += f"Saved: {datetime.now():%Y-%m-%d}\n"
    url = watch_url(vid)
    if text:
        label = re.sub(r"([*_])", r"\\\1", title.replace("[", "(").replace("]", ")"))
        return f"[{label}]({url})\n{meta}\n{text}\n"
    return f"[YouTube]({url})\nTitle: {info.get('title') or 'unknown'}\n{meta}\nNo transcript: {reason or NO_CAPS}\n"


def find_existing(inbox, vid):
    """Path of a note for this video (its ID in a watch or youtu.be link in the first 1 KB; subfolders count), or None."""
    needle = re.compile(rf"(?:watch\?v=|youtu\.be/){re.escape(vid)}")
    for p in inbox.rglob("*.md"):
        with open(p, encoding="utf-8", errors="replace") as f:
            if needle.search(f.read(1024)):
                return p
    return None


def is_stub(path):
    """True for a no-transcript note (its second line is `Title:`, a real note's is `Channel:`)."""
    lines = Path(path).read_text(encoding="utf-8", errors="replace").split("\n", 2)
    return len(lines) > 1 and lines[1].startswith("Title: ")


def write_atomic(inbox, name, body):
    """Write body to inbox/<name>.md via a temp file + rename. Never overwrites; numbers on clash."""
    inbox.mkdir(parents=True, exist_ok=True)
    tmp = inbox / ".yt2obsidian.tmp"  # ponytail: one temp name is safe because process() runs one save at a time
    try:
        tmp.write_text(body, encoding="utf-8", newline="\n")
        taken = {p.name.lower() for p in inbox.iterdir()}  # case-folded: phone sync may not tell Title.md from title.md
        for n in range(1, 100):
            dest = inbox / (f"{name}.md" if n == 1 else f"{name} ({n}).md")
            if dest.name.lower() not in taken:
                os.replace(tmp, dest)
                return dest
        raise OSError(f"too many name clashes for {name!r}")
    finally:
        tmp.unlink(missing_ok=True)


def notify(msg, urgent=False):
    shown = ["-u", "critical"] if urgent else ["-t", "3000"]  # failures stay until dismissed
    try:  # fire and forget: a missing notification daemon must not stall the prompt
        subprocess.Popen(["notify-send", "-a", "yt2obsidian", *shown, msg], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        pass


def open_obsidian(path):
    uri = f"obsidian://open?path={quote(str(Path(path).resolve()), safe='')}"
    try:
        subprocess.Popen(["xdg-open", uri], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        pass


def log_run(url, outcome, err="", title="", secs=None, source=""):
    """One tab-separated row: time, url, outcome, detail, title, seconds, source. New columns go on the end (recent_saves reads by position)."""
    url, err, title = (re.sub(r"\s+", " ", str(x)).strip() for x in (url, err, title))
    secs = "" if secs is None else f"{secs:.1f}"
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now().isoformat(timespec='seconds')}\t{url}\t{outcome}\t{err}\t{title}\t{secs}\t{source}\n")
    except OSError:
        pass  # a full disk must not hide the run's real outcome


def recent_saves(n=5):
    """Last n (time, note path) pairs from run.log. Saved rows hold the path; stub rows 'reason | path'."""
    try:
        rows = [r.split("\t") for r in LOG.read_text(encoding="utf-8").splitlines()]
    except OSError:
        return []
    saves = [(r[0], r[3].rsplit(" | ", 1)[-1]) for r in rows if len(r) > 3 and r[3] and r[2] in ("saved", "stub")]
    return [(when, path) for when, path in saves if Path(path).exists()][-n:]  # old rows have no path; undone notes are gone


def read_retry():
    try:
        return RETRY.read_text(encoding="utf-8").split()
    except OSError:
        return []


def queue_retry(url):
    try:
        with open(RETRY, "a+", encoding="utf-8") as f:
            f.seek(0)
            if url not in f.read().split():
                f.write(url + "\n")
    except OSError:
        pass


def toast(cfg, msg, repl=False, urgent=False):
    """Desktop notification per the notify setting; auto skips runs with a terminal attached (you are already looking at it)."""
    mode = (cfg or {}).get("notify", "auto")
    if mode == "always" or (mode == "auto" and not repl and not at_terminal()):
        notify(msg, urgent)


def finish(url, cfg, outcome, msg, code=0, err="", repl=False, path=None, title=None, note=None, secs=None, source=None):
    """The one exit for every run: print, log, toast (`note` is the shorter toast text). Typos typed at the prompt are not logged."""
    print(msg)
    if not (repl and outcome == "invalid"):
        if outcome == "invalid":
            url = cap(url, 60)  # a password pasted by mistake must not land in the log whole
        elif code:  # most breakage is a stale yt-dlp, so the log says which one
            err = f"{err} [yt-dlp {yt_dlp.version.__version__}]"
        log_run(url, LOG_AS.get(outcome, outcome), err, title or "", secs, source or ("repl" if repl else "argv"))
    toast(cfg, note or msg.split("\n")[0], repl, urgent=bool(code))
    return Result(code, outcome, path, title)


def process(url, cfg, repl=False, source=None):
    """Save one URL. Prints the outcome, logs it, returns a Result; never raises.
    Runs one at a time per project folder, so a double-tapped hotkey sees the first run's note as a duplicate."""
    try:
        lock = open(LOCK, "a")
    except OSError:
        return _process(url, cfg, repl, source)  # no lock file: run unlocked rather than not at all
    with lock:
        try:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                print("another run is saving, waiting...")
                fcntl.flock(lock, fcntl.LOCK_EX)
        except KeyboardInterrupt:
            print("cancelled")
            return Result(1, "cancelled")
        return _process(url, cfg, repl, source)


def _process(url, cfg, repl, source):
    t0 = time.monotonic()
    vault = cfg["vault"]

    def fin(outcome, msg, code=0, err="", **kw):
        return finish(url, cfg, outcome, msg, code, err, repl, secs=time.monotonic() - t0, source=source, **kw)

    try:
        inbox = vault / cfg["inbox"]
        try:
            vid, short = parse_url(url)
        except ValueError as e:
            return fin("invalid", f"failed: {e}" + (" (? for help)" if repl else ""), 1, str(e))
        if short:
            return fin("skipped", f"skipped: Shorts are not processed ({vid})")
        url = canonical = watch_url(vid)  # logged and queued without tracking params
        if old := find_existing(inbox, vid):
            return fin("duplicate", f"duplicate: {rel(old, vault)}" + (" (stub, delete it to retry)" if is_stub(old) else ""),
                       err=str(old), path=old)

        exc = None
        print("fetching...")
        try:
            try:
                info = with_retries(lambda: fetch(vid, cfg["timeout"]), cfg["retries"])
            except yt_dlp.utils.DownloadError as e:  # private, members-only...: stub
                if "video is unavailable" in str(e).lower():  # deleted or mistyped ID: nothing to save
                    return fin("failed", f"failed: video unavailable ({vid})", 1, f"DownloadError: {e}")
                info, exc = {}, e
            track = pick_track(info)
            text = transcript_text(with_retries(lambda: fetch_track(track, cfg["timeout"]), cfg["retries"])) if track else None
        except Stop as e:
            queue_retry(canonical)
            msg = f"stopped: {e.short or cap(e)}\nqueued in {RETRY.name}: {canonical}"
            return fin("stopped", msg + ("\nwait a while, then press r" if repl else ""), 2, f"Stop: {e}")

        reason = None if text else stub_reason(info, exc)
        path = write_atomic(inbox, safe_name(info.get("title"), vid, info.get("channel") or info.get("uploader")), render(info, vid, text, reason))
        title = clean(info.get("title") or vid)
        shown = rel(path, vault)
        msg = f"saved ({time.monotonic() - t0:.1f}s): {shown}\n  {title}" if text else \
            f"stub ({time.monotonic() - t0:.1f}s): {shown}\n  {title}\n  no transcript: {cap(reason)}"
        if exc and re.search(r"unable to extract|nsig", str(exc), re.I):
            msg += "\n  hint: yt-dlp may be out of date; press u (update yt-dlp)"
        if cfg.get("open_obsidian", True):
            open_obsidian(path)
        return fin("saved" if text else "stub", msg, err=str(path) if text else f"{reason} | {path}", path=path, title=title,
                   note=f"Saved: {cap(title, 80)}" if text else f"Stub: {cap(title, 80)} ({TOAST_REASON.get(reason, cap(reason, 60))})")
    except KeyboardInterrupt:
        print("cancelled")
        log_run(url, "cancelled")
        return Result(1, "cancelled")
    except (ValueError, OSError) as e:  # config, disk
        return fin("failed", f"failed: {cap(e)}", 1, f"{type(e).__name__}: {e}")
    except Exception as e:  # anything else must still end in a log row, not a traceback
        return fin("failed", f"failed: {type(e).__name__}: {cap(e)}", 1, f"{type(e).__name__}: {e}")


def urls_in(text):
    """Links in pasted text, one per line or space-separated. Anything else comes back whole, so the error names it."""
    toks = text.split()
    links = [t for t in toks if "youtu" in t.lower()]
    return links if links and len(toks) > 1 else [text.strip()]


def batch(text, cfg, repl=False, source=None):
    """process() each link in text. A throttle or Ctrl-C stops the run; links not yet tried go to retry.txt."""
    urls, results = urls_in(text), []
    for i, u in enumerate(urls):
        if len(urls) > 1:
            print(f"[{i + 1}/{len(urls)}]")
        results.append(process(u, cfg, repl, source))
        if results[-1].outcome in ("stopped", "cancelled"):
            rest = urls[i + 1:]
            for u in rest:
                try:
                    queue_retry(watch_url(parse_url(u)[0]))
                except ValueError:
                    pass
            if rest:
                print(f"queued the other {len(rest)} in {RETRY.name}")
            break
    return results


def update_ytdlp():
    """pip install -U yt-dlp into the running Python's environment."""
    old = version("yt-dlp")
    try:
        r = subprocess.run([sys.executable, "-m", "pip", "install", "-U", "yt-dlp"], capture_output=True, text=True, timeout=300)
    except (OSError, subprocess.SubprocessError, KeyboardInterrupt) as e:
        print(f"update failed: {cap(e) or 'cancelled'}")
        return
    if r.returncode:
        return print(f"update failed: {cap(r.stderr or r.stdout)}")
    new = version("yt-dlp")
    print(f"yt-dlp {old} -> {new}; quit and start again to use it" if new != old else f"yt-dlp {old} is already the latest")


def main(args=None, cfg=None, retry=False, **override):
    """One-shot run: the URL in args[0] or the clipboard, or the retry queue. Returns the exit code (see USAGE)."""
    url = ""
    try:
        cfg = {**(cfg or load_config()), **override}
        if retry:
            return max((r.code for r in retry_queue(cfg, repl=False)), default=0)
        args = sys.argv[1:] if args is None else args
        url = get_url(args)
    except (ValueError, OSError, subprocess.SubprocessError) as e:  # bad config, empty clipboard, no wl-paste
        return finish(url, cfg, "failed", f"failed: {cap(e)}", 1, str(e)).code
    return max(r.code for r in batch(url, cfg, source="argv" if args else "clipboard"))


def retry_queue(cfg, repl=True):
    """Re-run every URL in retry.txt; keep the ones still waiting. Stops at the first throttle."""
    urls, results, left = read_retry(), [], []
    if not urls:
        print("retry.txt is empty")
    for i, u in enumerate(urls):
        results.append(process(u, cfg, repl, "retry"))
        if results[-1].outcome in ("stopped", "cancelled"):
            left = urls[i:]
            break
    if urls:
        try:
            RETRY.write_text("".join(u + "\n" for u in left), encoding="utf-8")
        except OSError:
            pass
    return results


def repl():
    """Paste a link, press Enter, repeat. Ctrl-D, Ctrl-C or 'q' quits."""
    try:
        cfg = load_config()
        print(f"yt2obsidian (yt-dlp {yt_dlp.version.__version__})\nvault: {cfg['vault']}\ninbox: {cfg['inbox']}")
        if not (cfg["vault"] / ".obsidian").is_dir():
            print("warning: no .obsidian folder in the vault; wrong path, or the vault was never opened in Obsidian?")
        if bad := unknown_keys(cfg):
            print(f"warning: unknown keys in config.toml ignored: {', '.join(bad)}")
    except ValueError as e:
        print(f"Config problem: {e}")
    print("Paste a YouTube link and press Enter (? = help, q = quit)")
    readline.set_auto_history(False)  # only real links go in the history, not typos or pasted secrets
    try:
        readline.read_history_file(HISTORY)
    except OSError:
        pass
    readline.set_history_length(200)
    stats, last, made = Counter(), None, []

    def count(res):
        nonlocal last
        if res.outcome != "invalid":  # typos are not part of the session
            stats[res.outcome] += 1
            last = res.path or last
            if res.outcome in ("saved", "stub"):
                made.append(res)

    try:
        while True:
            line = ask("> ")
            if line is None:
                break
            cmd = line.lower()
            if line.startswith("#"):
                continue
            if cmd in ("q", "quit", "exit"):
                break
            if cmd in ("?", "h", "help"):
                print(HELP)
                continue
            if cmd == "l":
                for when, path in recent_saves():
                    print(f"  {when}  {path}")
                continue
            try:
                cfg = load_config()
            except ValueError as e:
                print(f"Config problem: {e}")
                continue
            if cmd in ("s", "settings"):
                settings_menu()
            elif cmd == "o":
                target = last or (recent_saves(1) or [(0, None)])[0][1]
                print(f"opening {rel(target, cfg['vault'])}" if target else "nothing saved yet")
                if target:
                    open_obsidian(target)
            elif cmd == "r":
                for res in retry_queue(cfg):
                    count(res)
            elif cmd == "u":
                update_ytdlp()
            elif cmd == "undo":
                if not made:
                    print("nothing to undo")
                    continue
                res = made[-1]
                if (ask(f"delete {rel(res.path, cfg['vault'])}? [y/N] ") or "").lower() == "y":
                    try:
                        res.path.unlink(missing_ok=True)
                    except OSError as e:
                        print(f"failed: {cap(e)}")
                        continue
                    made.pop()
                    stats[res.outcome] -= 1
                    last = last if last != res.path else None
                    log_run(res.path, "undone")
                    print("deleted")
            else:
                try:
                    url = line or clipboard()  # Enter alone pastes for you
                except (ValueError, OSError, subprocess.SubprocessError) as e:
                    print(f"failed: {cap(e)}")
                    continue
                results = batch(url, cfg, repl=True)
                for res in results:
                    count(res)
                if line and any(res.outcome != "invalid" for res in results):
                    readline.add_history(line)
    finally:
        try:
            readline.write_history_file(HISTORY)
        except OSError:
            pass
    if parts := [f"{stats[k]} {k}" for k in SUMMARY if stats[k]]:
        print("session: " + ", ".join(parts))
    if n := len(read_retry()):
        print(f"{n} URL{'s' * (n != 1)} waiting in {RETRY.name} (r to retry)")
    return 0


def cli(args):
    if args == ["-i"] or (not args and at_terminal()):  # no terminal = hotkey: read the clipboard
        for sig in (signal.SIGTERM, signal.SIGHUP):  # closing the terminal mid-save still cleans up the temp file
            signal.signal(sig, lambda *_: sys.exit(1))
        return repl()
    if args == ["--settings"]:
        settings_menu()
        return 0
    if args[:1] in (["-h"], ["--help"]):
        print(USAGE)
        return 0
    flags = [a for a in args if a in FLAGS]
    rest = [a for a in args if a not in FLAGS]
    if any(a.startswith("-") for a in rest) or ("--retry" in flags and rest):
        print(USAGE, file=sys.stderr)
        return 1
    over = {**({"open_obsidian": False} if "--no-open" in flags else {}), **({"notify": "never"} if "--no-notify" in flags else {})}
    return main(rest, retry="--retry" in flags, **over)


if __name__ == "__main__":
    sys.exit(cli(sys.argv[1:]))
