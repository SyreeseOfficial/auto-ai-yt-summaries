"""Plain-assert tests: python test_yt2obsidian.py"""
import contextlib
import io
import tempfile
from pathlib import Path
from unittest import mock

import yt2obsidian as y

V = "dQw4w9WgXcQ"


def raises(f, *a):
    try:
        f(*a)
    except ValueError:
        return True
    return False


def test_parse_url():
    for u in (f"https://www.youtube.com/watch?v={V}", f"https://youtu.be/{V}",
              f"https://youtu.be/{V}?t=42&si=abc", f"https://www.youtube.com/watch?feature=share&v={V}&t=1s",
              f"https://m.youtube.com/watch?v={V}", f"https://www.youtube.com/live/{V}?feature=share",
              f"https://www.youtube.com/embed/{V}", f"https://www.youtube.com/v/{V}"):
        assert y.parse_url(u) == (V, False), u
    assert y.parse_url(f"https://www.youtube.com/shorts/{V}") == (V, True)
    for u in ("hello", "https://example.com/watch?v=" + V, "https://www.youtube.com/watch",
              "https://www.youtube.com/watch?v=short", "https://www.youtube.com/@channel", ""):
        assert raises(y.parse_url, u), u


def test_safe_name():
    assert y.safe_name('a/b\\c:d*e?f"g<h>i|j', V) == "abcdefghij"
    assert y.safe_name("Hello 🔥 World 日本語", V) == "Hello World"
    assert y.safe_name("日本語🔥", V) == f"video-{V}"
    assert y.safe_name("  .Title with  spaces. ", V) == "Title with spaces"
    long = y.safe_name("x" * 400, V)
    assert len((long + " (99).md").encode()) <= 255


def test_pick_track():
    t = lambda u: [{"ext": "vtt", "url": u + ".vtt"}, {"ext": "json3", "url": u}]
    assert y.pick_track({"subtitles": {"en-GB": t("manual")}, "automatic_captions": {"en": t("auto")}}) == "manual"
    assert y.pick_track({"automatic_captions": {"en": t("auto")}}) == "auto"
    assert y.pick_track({"subtitles": {"en-US": t("us")}}) == "us"
    assert y.pick_track({"subtitles": {"fr": t("fr")}, "automatic_captions": {"de": t("de")}}) is None
    assert y.pick_track({"subtitles": {"en": [{"ext": "vtt", "url": "x"}]}}) is None
    assert y.pick_track({}) is None
    assert y.pick_track({"automatic_captions": {"en-US": t("us"), "en": t("en")}}) == "en"  # plain en first
    assert y.pick_track({"automatic_captions": {"en-orig": t("orig")}}) == "orig"
    # auto "en" that is really a translation of another language is rejected
    tr = [{"ext": "json3", "url": "https://x/timedtext?lang=ko&tlang=en"}]
    assert y.pick_track({"automatic_captions": {"en": tr}}) is None


def test_transcript_text():
    track = {"events": [{"segs": [{"utf8": "Hello  "}, {"utf8": "world"}]}, {"segs": [{"utf8": "\n"}]},
                        {"tStartMs": 5}, {"segs": [{"utf8": "second\nline"}]}]}
    assert y.transcript_text(track) == "Hello world second line"
    assert y.transcript_text({}) == ""
    # shapes seen in real tracks: music marks, sound tags, the `[ __ ]` censor, `>>` speaker changes
    ev = lambda *t: {"events": [{"segs": [{"utf8": x}]} for x in t]}
    assert y.transcript_text(ev("[♪♪♪] ♪ We're no strangers ♪", "[Music]")) == "We're no strangers"
    assert y.transcript_text(ev("what the [ __ ] is", "that [laughter] >> I", "don't know")) == "what the is that\n\nI don't know"
    assert y.transcript_text(ev("[Music]", "♪ ♪")) == ""  # nothing left: caller writes the no-captions stub


def test_stub_reason():
    assert y.stub_reason({"live_status": "is_upcoming"}) == y.LIVE
    assert y.stub_reason({"live_status": "is_live"}) == y.LIVE
    for info in ({"availability": "private"}, {"availability": "subscriber_only"}, {"age_limit": 18}):
        assert y.stub_reason(info) == y.RESTRICTED
    assert y.stub_reason({}, Exception("Private video. Sign in")) == y.RESTRICTED
    assert y.stub_reason({}, Exception("Join this channel to get access")) == y.RESTRICTED
    assert y.stub_reason({}, Exception("Premieres in 2 hours")) == y.LIVE
    assert y.stub_reason({"live_status": "not_live"}) == y.NO_CAPS
    assert y.stub_reason({"subtitles": {"fr": [], "de": []}, "automatic_captions": {"es-orig": [], "ja": []}}) \
        == "no English captions (found: fr, de, es-orig)"
    assert "boom" in y.stub_reason({}, Exception("boom"))


def test_render():
    info = {"title": "My [Video]", "channel": "Chan", "upload_date": "20240131"}
    note = y.render(info, V, "the text")
    assert note == f"[My (Video)](https://www.youtube.com/watch?v={V})\nChannel: Chan\nDate: 2024-01-31\n\nthe text\n"
    assert not note.startswith(("#", "---"))
    stub = y.render(info, V, None, y.NO_CAPS)
    assert "Title: My [Video]" in stub and "Channel: Chan" in stub and "No transcript: no captions available" in stub
    assert "unknown" in y.render({}, V, "t")


def test_write_path():
    with tempfile.TemporaryDirectory() as d:
        inbox = Path(d) / "deep" / "Inbox"  # created on demand
        a = y.write_atomic(inbox, "Title", y.render({"title": "T"}, V, "x"))
        assert a.name == "Title.md"
        b = y.write_atomic(inbox, "Title", "other")  # same name, different video
        assert b.name == "Title (2).md" and a.read_text().endswith("x\n")
        assert y.find_existing(inbox, V) == a
        assert y.find_existing(inbox, "AAAAAAAAAAA") is None
        assert [p.name for p in inbox.iterdir() if p.name.startswith(".")] == []
        # a failed write leaves no temp file and no note
        with mock.patch("os.replace", side_effect=OSError("boom")):
            try:
                y.write_atomic(inbox, "Other", "x")
            except OSError:
                pass
        assert sorted(p.name for p in inbox.iterdir()) == ["Title (2).md", "Title.md"]


def run_main(url, fetch=None, track=None, tmp=None):
    """Run y.main() against a tmp vault with network/UI stubbed. Returns (code, calls, tmp Path)."""
    d = Path(tmp or tempfile.mkdtemp())
    cfg = {"vault": d / "vault", "inbox": "Inbox", "timeout": 1, "retries": 3}
    calls = {"fetch": 0, "notify": []}

    def fake_fetch(vid, cfg):
        calls["fetch"] += 1
        if isinstance(fetch, BaseException):
            raise fetch
        return fetch

    with mock.patch.multiple(y, fetch=fake_fetch, fetch_track=lambda u, c: track, RETRY_DELAY=0,
                             LOG=d / "run.log", RETRY=d / "retry.txt", at_terminal=lambda: False,
                             notify=lambda m, u=False: calls["notify"].append(m), open_obsidian=lambda *a: None):
        code = y.main([url], cfg)
    return code, calls, d


def notes(d):
    return sorted((d / "vault" / "Inbox").glob("*.md"))


def test_main_saved_and_duplicate():
    info = {"title": "Héllo 🔥 日本 World", "channel": "C", "upload_date": "20200101",
            "subtitles": {"en": [{"ext": "json3", "url": "u"}]}}
    track = {"events": [{"segs": [{"utf8": "hi there 日本語 café"}]}]}
    code, calls, d = run_main(f"https://youtu.be/{V}", info, track)
    assert code == 0 and [p.name for p in notes(d)] == ["Hllo World.md"]
    assert "hi there 日本語 café" in notes(d)[0].read_text() and "saved" in (d / "run.log").read_text()
    code, calls, _ = run_main(f"https://youtu.be/{V}", info, track, tmp=d)  # duplicate: no fetch, no new file
    assert code == 0 and calls["fetch"] == 0 and len(notes(d)) == 1
    assert "duplicate" in (d / "run.log").read_text()


def test_main_short_and_garbage():
    code, calls, d = run_main(f"https://youtube.com/shorts/{V}")
    assert code == 0 and calls["fetch"] == 0 and notes(d) == [] and "skipped" in (d / "run.log").read_text()
    code, calls, d = run_main("not a url")
    assert code == 1 and calls["notify"]


def test_main_stubs():
    # no captions, live, and mocked private / members / age-restricted / premiere errors all give stubs, no retry
    base = {"title": "T", "channel": "C", "upload_date": "20200101"}
    cases = [(base, y.NO_CAPS), ({**base, "live_status": "is_live"}, y.LIVE)]
    for msg, want in (("ERROR: [youtube] x: Private video. Sign in if you've been granted access", y.RESTRICTED),
                      ("ERROR: [youtube] x: Join this channel to get access to members-only content", y.RESTRICTED),
                      ("ERROR: [youtube] x: Sign in to confirm your age", y.RESTRICTED),
                      ("ERROR: [youtube] x: Premieres in 3 hours", y.LIVE)):
        cases.append((y.yt_dlp.utils.DownloadError(msg), want))
    for fetch, want in cases:
        code, calls, d = run_main(f"https://youtu.be/{V}", fetch)
        assert code == 0 and calls["fetch"] == 1, want
        body = notes(d)[0].read_text()
        assert f"No transcript: {want}" in body, (want, body)
        assert not (d / "retry.txt").exists()
    assert notes(d)[0].name == f"video-{V}.md"  # no title available
    # a track that is only music tags gives a stub, not an empty note
    info = {**base, "subtitles": {"en": [{"ext": "json3", "url": "u"}]}}
    code, _, d = run_main(f"https://youtu.be/{V}", info, {"events": [{"segs": [{"utf8": "[♪♪♪]"}]}]})
    assert code == 0 and f"No transcript: {y.NO_CAPS}" in notes(d)[0].read_text()


def test_main_throttle_and_timeout():
    for exc, tries in ((y.Stop("429"), 1), (y.TransportError("timed out"), 3),
                       (y.yt_dlp.utils.DownloadError("ERROR: Unable to download webpage", (y.TransportError, y.TransportError("x"), None)), 3)):
        code, calls, d = run_main(f"https://youtu.be/{V}?t=5", exc)
        assert code == 2 and calls["fetch"] == tries, exc
        assert (d / "retry.txt").read_text() == f"https://www.youtube.com/watch?v={V}\n"
        assert "\tfailed\t" in (d / "run.log").read_text() and calls["notify"] and notes(d) == []


def test_main_crash_paths():
    for exc, out in ((KeyError("inbox"), "KeyError"), (KeyboardInterrupt(), "cancelled"),
                     (ValueError("caption download was not valid JSON"), "valid JSON")):
        code, calls, d = run_main(f"https://youtu.be/{V}", exc)
        assert code == 1 and out in (d / "run.log").read_text(), exc
        assert notes(d) == []
    d = run_main(f"https://youtu.be/{V}", y.yt_dlp.utils.DownloadError("ERROR: [youtube] x: This video is unavailable"))
    assert d[0] == 1 and notes(d[2]) == [] and "\tfailed\t" in (d[2] / "run.log").read_text()


def test_throttle_messages():
    msg = "ERROR: [youtube] x: This content isn't available, try again later. rate-limited by YouTube for up to an hour"
    with mock.patch.object(y.yt_dlp, "YoutubeDL") as ydl:
        ydl.return_value.__enter__.return_value.extract_info.side_effect = y.yt_dlp.utils.DownloadError(msg)
        try:
            y.fetch(V, 1)
        except y.Stop:
            pass
        else:
            assert False, "rate-limited message must be a throttle"


def test_retry_only_transient():
    from yt_dlp.networking.exceptions import HTTPError, TransportError
    wrap = lambda e: y.yt_dlp.utils.DownloadError("x", (type(e), e, None))
    for exc, calls in ((HTTPError(mock.Mock(status=403)), 1), (HTTPError(mock.Mock(status=404)), 1),
                       (HTTPError(mock.Mock(status=503)), 3), (TransportError("timed out"), 3),
                       (wrap(TransportError("[Errno 111] Connection refused")), 3), (wrap(HTTPError(mock.Mock(status=403))), 1),
                       (y.yt_dlp.utils.DownloadError("Video unavailable"), 1)):
        n = []

        def fn():
            n.append(1)
            raise exc
        try:
            y.with_retries(fn, 3)
        except (HTTPError, y.yt_dlp.utils.DownloadError, y.Stop):
            pass
        assert len(n) == calls, exc


def test_fetch_track_bad_json():
    with mock.patch.object(y.yt_dlp, "YoutubeDL") as ydl:
        ydl.return_value.__enter__.return_value.urlopen.return_value = io.BytesIO(b"<html>nope</html>")
        assert raises(y.fetch_track, "u", 1)


def test_misc_a():
    assert not y.ID_RE.fullmatch("é" * 11) and raises(y.parse_url, "https://youtu.be/" + "é" * 11)
    assert y.pick_track({"subtitles": {"en": [{"ext": "json3"}]}}) is None  # format without url
    assert y.stub_reason({}, Exception("Boom Loud")).endswith("Boom Loud")  # case kept
    assert "\\*" in y.render({"title": "a*b_c"}, V, "t") and "\\_" in y.render({"title": "a*b_c"}, V, "t")
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        with mock.patch.multiple(y, LOG=d / "run.log"):
            y.log_run("u", "failed", "line1\n\tline2")
        assert (d / "run.log").read_text().count("\n") == 1
        # a note with front matter still dedupes; a stub is recognised
        (d / "a.md").write_text(f"---\ntags: x\n---\n[T](https://www.youtube.com/watch?v={V})\n")
        assert y.find_existing(d, V) == d / "a.md"
        (d / "b.md").write_text(y.render({"title": "T"}, V, None, y.NO_CAPS))
        assert y.is_stub(d / "b.md") and not y.is_stub(d / "a.md")
        assert not y.is_stub(Path(d / "c.md").write_text("x") and d / "c.md")
        # clash cap: 99 names then an error
        for _ in range(99):
            y.write_atomic(d / "I", "N", "x")
        assert raises_os(y.write_atomic, d / "I", "N", "x")
        # config errors are readable ValueErrors, not tracebacks
        with mock.patch.object(y, "HERE", d):
            assert "not found" in err_of(y.load_config)
            (d / "config.toml").write_text('vault = "%s"\n' % d)
            assert "missing 'inbox'" in err_of(y.load_config)
            (d / "config.toml").write_text('vault = "%s"\ninbox = "I"\nnotify = "false"\n' % d)
            assert "notify must be auto, always, never" in err_of(y.load_config)
            (d / "config.toml").write_text('vault = "%s"\ninbox = "I"\nnotify = false\nopen_obsidian = "no"\n' % d)
            assert "true or false" in err_of(y.load_config)
            (d / "config.toml").write_text('vault = "%s"\ninbox = "I"\nretries = 0\n' % d)
            assert "retries must be a whole number" in err_of(y.load_config)
            (d / "config.toml").write_text('vault = "%s"\ninbox = "I"\nnotify = false\n' % d)
            assert y.load_config()["notify"] == "never"  # the old on/off form still reads
            (d / "config.toml").write_text('vault = "%s/nope"\ninbox = "I"\n' % d)
            assert "not a folder" in err_of(y.load_config)
            (d / "config.toml").write_text('vault = [oops\n')
            assert "line 1" in err_of(y.load_config)
            (d / "config.toml").write_text('vault = "%s"\ninbox = "I"\n' % d)
            assert y.load_config()["notify"] == "auto"


def raises_os(f, *a):
    try:
        f(*a)
    except OSError:
        return True
    return False


def err_of(f):
    try:
        f()
    except ValueError as e:
        return str(e)
    return ""


def test_cli():
    with mock.patch.object(y, "main", return_value=7), mock.patch.object(y, "repl", return_value=9), \
            mock.patch.object(y, "at_terminal", return_value=False):
        assert y.cli([]) == 7 and y.cli(["-i"]) == 9 and y.cli(["-h"]) == 0 and y.cli(["--help"]) == 0
        assert y.cli(["-i", "https://youtu.be/x"]) == 1 and y.cli(["--bogus"]) == 1
        with mock.patch.object(y, "settings_menu") as menu:
            assert y.cli(["--settings"]) == 0 and menu.called


def run_repl(lines, info=None, track=None, retry=None):
    """Drive y.repl() with scripted input against a tmp vault. Returns (output, tmp Path, opened paths)."""
    d = Path(tempfile.mkdtemp())
    (d / "vault").mkdir()
    (d / "config.toml").write_text(f'vault = "{d}/vault"\ninbox = "Inbox"\n')
    if retry:
        (d / "retry.txt").write_text(retry)
    opened, out = [], io.StringIO()
    feed = iter(lines)

    def fake_input(prompt=""):
        try:
            return next(feed)
        except StopIteration:
            raise EOFError

    fake = info if isinstance(info, BaseException) else None
    with mock.patch.multiple(y, HERE=d, LOG=d / "run.log", RETRY=d / "retry.txt", HISTORY=d / ".history",
                             fetch=lambda v, c: (_ for _ in ()).throw(fake) if fake else (info or {}),
                             fetch_track=lambda u, c: track, RETRY_DELAY=0, at_terminal=lambda: False,
                             notify=lambda m, u=False: opened.append(("toast", m)),
                             open_obsidian=lambda v, p: opened.append(("open", p)),
                             clipboard=lambda: "https://youtu.be/" + V), \
            mock.patch("builtins.input", fake_input), contextlib.redirect_stdout(out):
        assert y.repl() == 0
    return out.getvalue(), d, opened


def test_repl():
    info = {"title": "Cafe \x1b[31mTitle", "channel": "C", "upload_date": "20200101",
            "subtitles": {"en": [{"ext": "json3", "url": "u"}]}}
    track = {"events": [{"segs": [{"utf8": "hi"}]}]}
    out, d, opened = run_repl(["", "garbage", "# note", "?", f"https://youtu.be/{V}", "l", "o", "q"], info, track)
    # Enter alone pastes the clipboard; the second paste of the same video is a duplicate
    assert "saved (" in out and "Inbox/Cafe" in out and "duplicate: Inbox/" in out and "\x1b" not in out
    assert "fetching..." in out and "vault:" in out and "inbox: Inbox" in out and "yt-dlp" in out
    assert "failed: not a YouTube URL: 'garbage' (? for help)" in out and "<link>" in out
    assert "session: 1 saved, 1 duplicate" in out and "failed" not in out.split("session:")[1]
    # typos and comments are not logged; no toasts at a prompt; `l` and `o` find the note
    log = (d / "run.log").read_text()
    assert "garbage" not in log and "# note" not in log and log.count("\n") == 2
    assert not [o for o in opened if o[0] == "toast"] and [o for o in opened if o[0] == "open"]
    assert str(notes(d)[0]) in out  # `l` lists it; `o` opens it
    assert ("open", notes(d)[0]) in opened
    # only real links reach the history file
    hist = (d / ".history").read_text()
    assert f"https://youtu.be/{V}" in hist and "garbage" not in hist and "# note" not in hist


def test_repl_survives_errors():
    out, d, _ = run_repl([f"https://youtu.be/{V}", "q"], KeyError("boom"))
    assert "failed: KeyError" in out and "session: 1 failed" in out
    out, d, _ = run_repl([f"https://youtu.be/{V}", "q"], KeyboardInterrupt())
    assert "cancelled" in out and "session" not in out


def test_repl_throttle_and_retry():
    out, d, _ = run_repl([f"https://youtu.be/{V}", "q"], y.Stop("429", "throttled by YouTube"))
    assert "stopped: throttled by YouTube" in out and "press r" in out
    assert "1 URL waiting in retry.txt (r to retry)" in out and "1 stopped" in out
    assert (d / "retry.txt").read_text() == f"https://www.youtube.com/watch?v={V}\n"
    # `r`: the saved link leaves the queue; a throttle stops the run and keeps the rest
    info = {"title": "T", "subtitles": {"en": [{"ext": "json3", "url": "u"}]}}
    track = {"events": [{"segs": [{"utf8": "hi"}]}]}
    out, d, _ = run_repl(["r", "q"], info, track, retry=f"https://youtu.be/{V}\n")
    assert "saved (" in out and (d / "retry.txt").read_text() == "" and "waiting" not in out
    two = f"https://youtu.be/{V}\nhttps://youtu.be/AAAAAAAAAAA\n"
    out, d, _ = run_repl(["r", "q"], y.Stop("429"), retry=two)
    assert out.count("stopped:") == 1 and (d / "retry.txt").read_text() == two
    out, d, _ = run_repl(["r", "q"])
    assert "retry.txt is empty" in out


def test_batch_and_undo():
    ids = ["AAAAAAAAAAA", "BBBBBBBBBBB", "CCCCCCCCCCC"]
    assert y.urls_in("a\nhttps://youtu.be/x https://youtu.be/y\n") == ["https://youtu.be/x", "https://youtu.be/y"]
    assert y.urls_in("garbage in here") == ["garbage in here"] and y.urls_in(" one ") == ["one"]
    info = {"title": "T", "subtitles": {"en": [{"ext": "json3", "url": "u"}]}}
    track = {"events": [{"segs": [{"utf8": "hi"}]}]}
    # a pasted list: each link saved in turn (same title -> numbered names), then undo deletes the last, with a prompt
    out, d, _ = run_repl(["\n".join(f"https://youtu.be/{i}" for i in ids[:2]), "undo", "y", "undo", "n", "q"], info, track)
    assert "[1/2]" in out and "[2/2]" in out and "deleted" in out and "session: 1 saved" in out
    assert [p.name for p in notes(d)] == ["T.md"]  # the clash copy was the one undone
    out, d, _ = run_repl(["undo", "q"])
    assert "nothing to undo" in out
    # a throttle on the first link queues the untried ones, in canonical form, and stops
    out, d, _ = run_repl([" ".join(f"https://youtu.be/{i}?t=5" for i in ids), "q"], y.Stop("429"))
    assert out.count("stopped:") == 1 and "queued the other 2" in out
    assert (d / "retry.txt").read_text().split() == [f"https://www.youtube.com/watch?v={i}" for i in ids]


def test_settings():
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        cfgfile = d / "config.toml"
        cfgfile.write_text(f'vault = "{d}"  # mine\ninbox = "I I"  # box\nnotify = "auto"  # keep\ntimeout = 30\nnotfy = 1\n')
        text = lambda: cfgfile.read_text()
        with mock.patch.object(y, "HERE", d):
            y.set_value("notify", "never")  # rewritten in place, comment and other keys kept
            assert 'notify = "never"  # keep' in text() and "# mine" in text()
            y.set_value("inbox", "New Box")  # a quoted value with spaces is replaced whole
            assert 'inbox = "New Box"  # box' in text()
            y.set_value("open_obsidian", False)  # absent key is appended, lowercase
            assert text().endswith("open_obsidian = false\n")
            assert not list(d.glob("*.tmp")) and y.unknown_keys(y.load_config()) == ["notfy"]
            assert y.load_config()["notify"] == "never" and y.load_config()["inbox"] == "New Box"
            y.reset_settings()  # defaults back; inbox and keys that were absent are left alone
            c = y.load_config()
            assert c["notify"] == "auto" and c["open_obsidian"] is True and c["inbox"] == "New Box"
            assert 'notify = "auto"  # keep' in text() and "retries" not in text()
            # input rules
            assert y.parse_setting("timeout", " 45 ") == 45 and y.parse_setting("inbox", " Notes/Yt ") == "Notes/Yt"
            for key, bad in (("timeout", "0"), ("retries", "x"), ("retries", "-1"), ("inbox", ""), ("inbox", "/tmp/x"), ("inbox", "../x")):
                assert raises(y.parse_setting, key, bad)
            # the menu: flip (1), cycle (2), type a value (3, 4), bad input, leave
            feed = iter(["1", "2", "3", "Notes", "4", "0", "4", "", "x", "9", "q"])
            with mock.patch("builtins.input", lambda p="": next(feed)), mock.patch("builtins.print") as pr:
                y.settings_menu()
            shown = "\n".join(str(c.args[0]) for c in pr.call_args_list if c.args)
            assert "Open the note in Obsidian after saving: off" in shown
            assert "Desktop notifications: always (even at the prompt)" in shown
            assert "Inbox folder inside the vault: Notes" in shown and "Seconds to wait per fetch must be a whole number" in shown
            assert shown.count("pick 1-5") == 2 and "unknown keys ignored: notfy" in shown
            c = y.load_config()
            assert (c["open_obsidian"], c["notify"], c["inbox"], c["timeout"]) == (False, "always", "Notes", 30)
            feed = iter(["d", ""])
            with mock.patch("builtins.input", lambda p="": next(feed)), mock.patch("builtins.print"):
                y.settings_menu()
            assert y.load_config()["notify"] == "auto" and y.load_config()["inbox"] == "Notes"
            # a broken config returns to the caller with a message, not a traceback
            cfgfile.write_text("vault = [oops\n")
            with mock.patch("builtins.print") as pr:
                y.settings_menu()
            assert "Config problem" in str(pr.call_args)


def test_toast_modes():
    sent = []
    for mode, repl, term, want in (("auto", False, False, 1), ("auto", False, True, 0), ("auto", True, False, 0),
                                   ("always", True, True, 1), ("never", False, False, 0)):
        sent.clear()
        with mock.patch.object(y, "notify", lambda m, u=False: sent.append(m)), mock.patch.object(y, "at_terminal", return_value=term):
            y.toast({"notify": mode}, "m", repl)
        assert len(sent) == want, (mode, repl, term)


def test_settings_apply_to_next_paste():
    info = {"title": "T", "subtitles": {"en": [{"ext": "json3", "url": "u"}]}}
    track = {"events": [{"segs": [{"utf8": "hi"}]}]}
    out, d, opened = run_repl(["s", "1", "", f"https://youtu.be/{V}", "q"], info, track)
    assert "Open the note in Obsidian after saving: off" in out and "saved (" in out
    assert not [o for o in opened if o[0] == "open"]  # the toggle took effect with no restart
    out, d, opened = run_repl(["s", "1", "1", "b", f"https://youtu.be/{V}", "q"], info, track)
    assert [o for o in opened if o[0] == "open"]


def test_update_and_default_mode():
    out = io.StringIO()
    run = lambda rc: mock.Mock(returncode=rc, stdout="", stderr="no network")
    with contextlib.redirect_stdout(out):
        with mock.patch.object(y.subprocess, "run", return_value=run(1)):
            y.update_ytdlp()
        with mock.patch.object(y.subprocess, "run", return_value=run(0)):
            y.update_ytdlp()
        with mock.patch.object(y.subprocess, "run", side_effect=KeyboardInterrupt):
            y.update_ytdlp()
    assert "update failed: no network" in out.getvalue() and "already the latest" in out.getvalue()
    assert "update failed: cancelled" in out.getvalue()
    with mock.patch.object(y, "main", return_value=7), mock.patch.object(y, "repl", return_value=9):
        with mock.patch.object(y, "at_terminal", return_value=True), mock.patch.object(y.signal, "signal"):
            assert y.cli([]) == 9  # a terminal with no argument gets the prompt
        with mock.patch.object(y, "at_terminal", return_value=False):
            assert y.cli([]) == 7  # the hotkey has no terminal: clipboard mode


def test_clean_cap_rel():
    assert y.clean("a\x1b[31m\n b\t") == "a [31m b" and y.cap("x" * 300).endswith("…") and len(y.cap("x" * 300)) == 200
    assert y.rel("/v/Inbox/a.md", "/v") == "Inbox/a.md" and y.rel("/elsewhere/a.md", "/v") == "/elsewhere/a.md"
    assert len(err_of(lambda: y.parse_url("x" * 500))) < 100
    with tempfile.TemporaryDirectory() as d:
        a, b, gone = (str(Path(d) / n) for n in ("a.md", "b.md", "gone.md"))
        for n in (a, b):
            Path(n).write_text("x")
        rows = [f"t1\tu\tsaved\t", f"t2\tu\tstub\tno captions | {a}", f"t3\tu\tsaved\t{b}", f"t4\tu\tsaved\t{gone}",
                "t5\tu\tfailed\tx"]
        (Path(d) / "run.log").write_text("\n".join(rows) + "\n")
        with mock.patch.object(y, "LOG", Path(d) / "run.log"):
            assert y.recent_saves() == [("t2", a), ("t3", b)]  # old row, deleted note, failure: all left out
            assert y.recent_saves(1) == [("t3", b)]


def test_one_shot_flags_and_toasts():
    with mock.patch.object(y, "main", return_value=0) as m, mock.patch.object(y, "at_terminal", return_value=False):
        assert y.cli(["--no-open", "--no-notify", "u"]) == 0
        assert m.call_args.args == (["u"],) and m.call_args.kwargs == {"retry": False, "open_obsidian": False, "notify": "never"}
        assert y.cli(["--retry"]) == 0 and m.call_args.kwargs["retry"] is True
        assert y.cli(["--retry", "u"]) == 1  # a URL and --retry together make no sense
    info = {"title": "T", "channel": "C", "subtitles": {"en": [{"ext": "json3", "url": "u"}]}}
    track = {"events": [{"segs": [{"utf8": "hi"}]}]}
    code, calls, d = run_main(f"https://youtu.be/{V}", info, track)
    assert calls["notify"] == ["Saved: T"]  # real title, not the file stem
    code, calls, _ = run_main(f"https://youtu.be/{V}", info, track, tmp=d)
    assert calls["notify"] == ["duplicate: Inbox/T.md"], calls["notify"]  # hotkey shows the duplicate
    code, calls, _ = run_main(f"https://www.youtube.com/shorts/{V}")
    assert code == 0 and calls["notify"][0].startswith("skipped")
    # --retry: saves what it can, keeps what still throttles, exit 2
    d = Path(tempfile.mkdtemp())
    (d / "retry.txt").write_text(f"https://www.youtube.com/watch?v={V}\nhttps://www.youtube.com/watch?v=aaaaaaaaaab\n")
    cfg = {"vault": d, "inbox": "Inbox", "timeout": 1, "retries": 1}
    def fetch(vid, c):
        if vid == V:
            return info
        raise y.Stop("429", "throttled")
    with mock.patch.multiple(y, fetch=fetch, fetch_track=lambda u, c: track, LOG=d / "run.log", RETRY=d / "retry.txt",
                             LOCK=d / ".lock", at_terminal=lambda: False, notify=lambda m, u=False: None,
                             open_obsidian=lambda *a: None):
        assert y.main(retry=True, cfg=cfg) == 2
    assert (d / "retry.txt").read_text() == "https://www.youtube.com/watch?v=aaaaaaaaaab\n" and (d / "Inbox" / "T.md").exists()
    # notify builds the right command; failures are critical, successes time out
    with mock.patch.object(y.subprocess, "Popen") as pop:
        y.notify("m", True)
        y.notify("m")
    assert pop.call_args_list[0].args[0] == ["notify-send", "-a", "yt2obsidian", "-u", "critical", "m"]
    assert pop.call_args_list[1].args[0] == ["notify-send", "-a", "yt2obsidian", "-t", "3000", "m"]


def test_lock_serializes_runs():
    d = Path(tempfile.mkdtemp())
    with mock.patch.object(y, "LOCK", d / ".lock"), mock.patch.object(y, "_process", return_value="ran") as p:
        assert y.process("u", {}) == "ran"
        with mock.patch.object(y.fcntl, "flock", side_effect=[BlockingIOError, KeyboardInterrupt]):
            assert y.process("u", {}).outcome == "cancelled"  # lock busy, then Ctrl-C while waiting
    assert p.call_count == 1


if __name__ == "__main__":
    for name, f in list(globals().items()):
        if name.startswith("test_"):
            f()
            print("ok", name)
