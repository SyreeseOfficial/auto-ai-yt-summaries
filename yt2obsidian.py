"""yt2obsidian: YouTube URL -> transcript note in an Obsidian vault. See PRD.md."""
import json
import os
import re
import readline
import signal
import subprocess
import sys
import tempfile
import time
import tomllib
import urllib.error
import urllib.request
from collections import Counter, namedtuple
from datetime import datetime
from importlib.metadata import version
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

import yt_dlp

HERE = Path(__file__).parent
LOG = HERE / "run.log"
RETRY = HERE / "retry.txt"
HISTORY = HERE / ".history"
RETRY_DELAY = 2  # seconds, times attempt number
SETTINGS = {  # config key -> (menu label, default, allowed): bool, a {choice: note} dict, int, or str
    "open_obsidian": ("Open the note in Obsidian after saving", True, bool),
    "notify": ("Desktop notifications", "auto", {"auto": "only when no terminal is attached", "always": "even at the prompt", "never": "off"}),
    "inbox": ("Inbox folder inside the vault", None, str),
    "timeout": ("Seconds to wait per fetch", 30, int),
    "retries": ("Attempts per fetch", 3, int),
}
THROTTLE = ("http error 429", "not a bot", "rate-limited", "try again later")
USAGE = """usage: yt2obsidian.py [URL]   save a transcript (no URL: prompt in a terminal, else read the clipboard)
       yt2obsidian.py -i       interactive prompt (or run ./yt; ./yt URL saves one link)
       yt2obsidian.py --settings  settings menu only
       yt2obsidian.py -h       this help"""
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
    if not cfg["vault"].is_dir():
        raise ValueError(f"{path}: vault is not a folder: {cfg['vault']}")
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


def parse_setting(key, raw):
    """Typed value for text typed into the menu. Raises ValueError with a message for the user."""
    raw = raw.strip()
    if SETTINGS[key][2] is int:
        if not raw.isdigit() or int(raw) < 1:
            raise ValueError("must be a whole number, 1 or more")
        return int(raw)
    if not raw or Path(raw).is_absolute() or ".." in Path(raw).parts:
        raise ValueError("must be a relative folder name (no leading / and no ..)")
    return raw


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
            if (bad := unknown_keys(cfg)):
                print(f"  warning: unknown keys ignored: {', '.join(bad)}")
            for i, k in enumerate(keys, 1):
                label, _, allowed = SETTINGS[k]
                print(f"  {i}. [{'x' if cfg[k] else ' '}] {label}" if allowed is bool else f"  {i}. {label}: {show_setting(k, cfg[k])}")
            try:
                pick = input("Number changes a setting, d resets, Enter goes back\nsettings> ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print()
                return
            if pick in ("", "q", "b"):
                return
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
                    try:
                        raw = input(f"{label} [{cfg[k]}], new value (Enter keeps it): ").strip()
                    except (EOFError, KeyboardInterrupt):
                        print()
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


def get_url(argv):
    """argv[1] if given, else the clipboard (wl-paste)."""
    return argv[1].strip() if len(argv) > 1 else clipboard()


def clipboard():
    r = subprocess.run(["wl-paste", "--no-newline"], capture_output=True, text=True, timeout=5)
    if r.returncode or not r.stdout.strip():
        raise ValueError("clipboard is empty or not text")
    return r.stdout.strip()


def parse_url(s):
    """Return (video_id, 'video'|'short'). Raises ValueError on anything else."""
    u = urlparse(s.strip())
    host = (u.hostname or "").lower()
    if host not in HOSTS:
        raise ValueError(f"not a YouTube URL: {s[:60]!r}")
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
        raise ValueError(f"no video id in URL: {s[:60]!r}")
    return vid, kind


def fetch(vid, cfg):
    """Video info dict from yt-dlp (no download). Raises Throttled on 429 / bot check."""
    opts = {"logger": Quiet(), "skip_download": True, "noplaylist": True, "socket_timeout": cfg["timeout"]}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(f"https://www.youtube.com/watch?v={vid}", download=False)
    except yt_dlp.utils.DownloadError as e:
        if any(k in str(e).lower() for k in THROTTLE):
            raise Throttled(str(e), "throttled by YouTube") from e
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
                raise Throttled(f"network failure after {attempt} tries: {e}", "network down or unreachable") from e
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
            raise Throttled("HTTP 429 on caption download", "throttled by YouTube") from e
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
        if url not in read_retry():
            with open(RETRY, "a", encoding="utf-8") as f:
                f.write(url + "\n")
    except OSError:
        pass


def toast(cfg, msg, repl=False):
    """Desktop notification per the notify setting; auto skips runs with a terminal attached (you are already looking at it)."""
    mode = (cfg or {}).get("notify", "auto")
    if mode == "always" or (mode == "auto" and not repl and not at_terminal()):
        notify(msg)


def finish(url, cfg, outcome, msg, code=0, err="", repl=False, path=None, title=None):
    """The one exit for every run but a save: print, log, toast. Typos typed at the prompt are not logged."""
    print(msg)
    if not (repl and outcome == "invalid"):
        log_run(url, LOG_AS.get(outcome, outcome), err)
    if code:
        toast(cfg, msg, repl)
    return Result(code, outcome, path, title)


def process(url, cfg, repl=False):
    """Save one URL. Prints the outcome, logs it, returns a Result; never raises."""
    t0 = time.monotonic()
    vault = cfg["vault"]

    def fin(outcome, msg, code=0, err="", **kw):
        return finish(url, cfg, outcome, msg, code, err, repl, **kw)

    try:
        inbox = vault / cfg["inbox"]
        try:
            vid, kind = parse_url(url)
        except ValueError as e:
            return fin("invalid", f"failed: {e}" + (" (? for help)" if repl else ""), 1, str(e))
        if kind == "short":
            return fin("skipped", f"skipped: Shorts are not processed ({vid})")
        if (old := find_existing(inbox, vid)):
            return fin("duplicate", f"duplicate: {rel(old, vault)}" + (" (stub, delete it to retry)" if is_stub(old) else ""),
                       path=old)

        canonical = f"https://www.youtube.com/watch?v={vid}"
        exc = None
        print("fetching...")
        try:
            try:
                info = with_retries(lambda: fetch(vid, cfg), cfg)
            except yt_dlp.utils.DownloadError as e:  # private, members-only...: stub
                if "video is unavailable" in str(e).lower():  # deleted or mistyped ID: nothing to save
                    return fin("failed", f"failed: video unavailable ({vid})", 1, str(e))
                info, exc = {}, e
            track = pick_track(info)
            text = transcript_text(with_retries(lambda: fetch_track(track, cfg), cfg)) if track else None
        except Throttled as e:
            queue_retry(canonical)
            msg = f"stopped: {e.short or cap(e)}\nqueued in {RETRY.name}: {canonical}"
            return fin("stopped", msg + ("\nwait a while, then press r" if repl else ""), 2, str(e))

        reason = None if text else stub_reason(info, exc)
        path = write_atomic(inbox, safe_name(info.get("title"), vid), render(info, vid, text, reason))
        title = clean(info.get("title") or vid)
        shown = rel(path, vault)
        msg = f"saved ({time.monotonic() - t0:.1f}s): {shown}\n  {title}" if text else \
            f"stub ({time.monotonic() - t0:.1f}s): {shown}\n  {title}\n  no transcript: {cap(reason)}"
        if exc and re.search(r"unable to extract|nsig", str(exc), re.I):
            msg += "\n  hint: yt-dlp may be out of date; press u (update yt-dlp)"
        print(msg)
        log_run(url, "saved" if text else "stub", str(path) if text else f"{reason} | {path}")
        toast(cfg, f"Saved: {path.stem}" + ("" if text else f" (stub: {reason})"), repl)
        if cfg.get("open_obsidian", True):
            open_obsidian(vault, path)
        return Result(0, "saved" if text else "stub", path, title)
    except KeyboardInterrupt:
        print("cancelled")
        log_run(url, "cancelled")
        return Result(1, "cancelled")
    except (ValueError, OSError) as e:  # config, disk
        return fin("failed", f"failed: {cap(e)}", 1, str(e))
    except Exception as e:  # anything else must still end in a log row, not a traceback
        return fin("failed", f"failed: {type(e).__name__}: {cap(e)}", 1, f"{type(e).__name__}: {e}")


def urls_in(text):
    """Links in pasted text, one per line or space-separated. Anything else comes back whole, so the error names it."""
    toks = text.split()
    links = [t for t in toks if "youtu" in t.lower()]
    return links if links and len(toks) > 1 else [text.strip()]


def batch(text, cfg, repl=False):
    """process() each link in text. A throttle or Ctrl-C stops the run; links not yet tried go to retry.txt."""
    urls, results = urls_in(text), []
    for i, u in enumerate(urls):
        if len(urls) > 1:
            print(f"[{i + 1}/{len(urls)}]")
        results.append(process(u, cfg, repl))
        if results[-1].outcome in ("stopped", "cancelled"):
            rest = urls[i + 1:]
            for u in rest:
                try:
                    queue_retry(f"https://www.youtube.com/watch?v={parse_url(u)[0]}")
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


def main(argv=None, cfg=None):
    url = ""
    try:
        cfg = cfg or load_config()
        url = get_url(argv if argv is not None else sys.argv)
    except (ValueError, OSError, subprocess.SubprocessError) as e:  # bad config, empty clipboard, no wl-paste
        return finish(url, cfg, "failed", f"failed: {cap(e)}", 1, str(e)).code
    return max(r.code for r in batch(url, cfg))


def retry_queue(cfg):
    """Re-run every URL in retry.txt; keep the ones still waiting. Stops at the first throttle."""
    urls, results, left = read_retry(), [], []
    if not urls:
        print("retry.txt is empty")
    for i, u in enumerate(urls):
        results.append(process(u, cfg, repl=True))
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
        if (bad := unknown_keys(cfg)):
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
            try:
                line = input("> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
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
                    open_obsidian(cfg["vault"], target)
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
                try:
                    ok = input(f"delete {rel(res.path, cfg['vault'])}? [y/N] ").strip().lower() == "y"
                except (EOFError, KeyboardInterrupt):
                    print()
                    ok = False
                if ok:
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
    if (parts := [f"{stats[k]} {k}" for k in SUMMARY if stats[k]]):
        print("session: " + ", ".join(parts))
    if (n := len(read_retry())):
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
    if args[:1] and args[0].startswith("-"):
        print(USAGE, file=sys.stderr)
        return 1
    return main()


if __name__ == "__main__":
    sys.exit(cli(sys.argv[1:]))
