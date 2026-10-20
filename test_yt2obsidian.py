"""Plain-assert tests: python test_yt2obsidian.py"""
from yt2obsidian import *
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
              f"https://www.youtube.com/embed/{V}", f"  https://youtube.com/watch?v={V}\n"):
        assert parse_url(u) == (V, "video"), u
    assert parse_url(f"https://www.youtube.com/shorts/{V}") == (V, "short")
    for u in ("hello", "https://example.com/watch?v=" + V, "https://www.youtube.com/watch",
              "https://www.youtube.com/watch?v=short", "https://www.youtube.com/@channel", ""):
        assert raises(parse_url, u), u


def test_safe_name():
    assert safe_name('a/b\\c:d*e?f"g<h>i|j', V) == "abcdefghij"
    assert safe_name("Hello 🔥 World 日本語", V) == "Hello World"
    assert safe_name("日本語🔥", V) == f"video-{V}"
    assert safe_name("  .Title with  spaces. ", V) == "Title with spaces"
    long = safe_name("x" * 400, V)
    assert len((long + " (99).md").encode()) <= 255


def test_pick_track():
    t = lambda u: [{"ext": "vtt", "url": u + ".vtt"}, {"ext": "json3", "url": u}]
    assert pick_track({"subtitles": {"en-GB": t("manual")}, "automatic_captions": {"en": t("auto")}}) == "manual"
    assert pick_track({"automatic_captions": {"en": t("auto")}}) == "auto"
    assert pick_track({"subtitles": {"en-US": t("us")}}) == "us"
    assert pick_track({"subtitles": {"fr": t("fr")}, "automatic_captions": {"de": t("de")}}) is None
    assert pick_track({"subtitles": {"en": [{"ext": "vtt", "url": "x"}]}}) is None
    assert pick_track({}) is None
    # auto "en" that is really a translation of another language is rejected
    tr = [{"ext": "json3", "url": "https://x/timedtext?lang=ko&tlang=en"}]
    assert pick_track({"automatic_captions": {"en": tr}}) is None


def test_transcript_text():
    track = {"events": [{"segs": [{"utf8": "Hello  "}, {"utf8": "world"}]}, {"segs": [{"utf8": "\n"}]},
                        {"tStartMs": 5}, {"segs": [{"utf8": "second\nline"}]}]}
    assert transcript_text(track) == "Hello world second line"
    assert transcript_text({}) == ""


def test_stub_reason():
    assert stub_reason({"live_status": "is_upcoming"}) == y.LIVE
    assert stub_reason({"live_status": "is_live"}) == y.LIVE
    for info in ({"availability": "private"}, {"availability": "subscriber_only"}, {"age_limit": 18}):
        assert stub_reason(info) == y.RESTRICTED
    assert stub_reason({}, Exception("Private video. Sign in")) == y.RESTRICTED
    assert stub_reason({}, Exception("Join this channel to get access")) == y.RESTRICTED
    assert stub_reason({}, Exception("Premieres in 2 hours")) == y.LIVE
    assert stub_reason({"live_status": "not_live"}) == y.NO_CAPS
    assert "boom" in stub_reason({}, Exception("boom"))


def test_render():
    info = {"title": "My [Video]", "channel": "Chan", "upload_date": "20240131"}
    note = render(info, V, "the text")
    assert note == f"[My (Video)](https://www.youtube.com/watch?v={V})\nChannel: Chan\nDate: 2024-01-31\n\nthe text\n"
    assert not note.startswith(("#", "---"))
    stub = render(info, V, None, y.NO_CAPS)
    assert "Title: My [Video]" in stub and "Channel: Chan" in stub and "No transcript: no captions available" in stub
    assert "unknown" in render({}, V, "t")


def test_write_path():
    import tempfile
    from pathlib import Path
    from unittest import mock
    with tempfile.TemporaryDirectory() as d:
        inbox = Path(d) / "deep" / "Inbox"  # created on demand
        a = write_atomic(inbox, "Title", render({"title": "T"}, V, "x"))
        assert a.name == "Title.md"
        b = write_atomic(inbox, "Title", "other")  # same name, different video
        assert b.name == "Title (2).md" and a.read_text().endswith("x\n")
        assert find_existing(inbox, V) == a
        assert find_existing(inbox, "AAAAAAAAAAA") is None
        assert [p.name for p in inbox.iterdir() if p.name.startswith(".")] == []
        # a failed write leaves no temp file and no note
        with mock.patch("os.link", side_effect=OSError("boom")):
            try:
                write_atomic(inbox, "Other", "x")
            except OSError:
                pass
        assert sorted(p.name for p in inbox.iterdir()) == ["Title (2).md", "Title.md"]


def run_main(url, fetch=None, track=None, tmp=None):
    """Run main() against a tmp vault with network/UI stubbed. Returns (code, calls, tmp Path)."""
    import tempfile
    from pathlib import Path
    from unittest import mock
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
                             notify=calls["notify"].append, open_obsidian=lambda *a: None):
        code = main([None, url], cfg)
    return code, calls, d


def notes(d):
    return sorted((d / "vault" / "Inbox").glob("*.md"))


def test_main_saved_and_duplicate():
    info = {"title": "Héllo 🔥 日本 World", "channel": "C", "upload_date": "20200101",
            "subtitles": {"en": [{"ext": "json3", "url": "u"}]}}
    track = {"events": [{"segs": [{"utf8": "hi there"}]}]}
    code, calls, d = run_main(f"https://youtu.be/{V}", info, track)
    assert code == 0 and [p.name for p in notes(d)] == ["Hllo World.md"]
    assert "hi there" in notes(d)[0].read_text() and "saved" in (d / "run.log").read_text()
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


def test_main_throttle_and_timeout():
    for exc, tries in ((y.Throttled("429"), 1), (TimeoutError("timed out"), 3),
                       (y.yt_dlp.utils.DownloadError("ERROR: Unable to download webpage: timed out"), 3)):
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
    from unittest import mock
    msg = "ERROR: [youtube] x: This content isn't available, try again later. rate-limited by YouTube for up to an hour"
    with mock.patch.object(y.yt_dlp, "YoutubeDL") as ydl:
        ydl.return_value.__enter__.return_value.extract_info.side_effect = y.yt_dlp.utils.DownloadError(msg)
        try:
            fetch(V, {"timeout": 1})
        except Throttled:
            pass
        else:
            assert False, "rate-limited message must be a throttle"


def test_retry_only_transient():
    import urllib.error
    for code, calls in ((403, 1), (404, 1), (503, 3)):
        n = []

        def fn():
            n.append(1)
            raise urllib.error.HTTPError("u", code, "x", {}, None)
        try:
            with_retries(fn, {"retries": 3})
        except (urllib.error.HTTPError, Throttled):
            pass
        assert len(n) == calls, code


def test_fetch_track_bad_json():
    import io
    from unittest import mock
    with mock.patch("urllib.request.urlopen", return_value=io.BytesIO(b"<html>nope</html>")):
        assert raises(fetch_track, "u", {"timeout": 1})


def test_misc_a():
    assert not ID_RE.fullmatch("é" * 11) and raises(parse_url, "https://youtu.be/" + "é" * 11)
    assert pick_track({"subtitles": {"en": [{"ext": "json3"}]}}) is None  # format without url
    assert stub_reason({}, Exception("Boom Loud")).endswith("Boom Loud")  # case kept
    assert "\\*" in render({"title": "a*b_c"}, V, "t") and "\\_" in render({"title": "a*b_c"}, V, "t")
    import tempfile
    from pathlib import Path
    from unittest import mock
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        with mock.patch.multiple(y, LOG=d / "run.log"):
            log_run("u", "failed", "line1\n\tline2")
        assert (d / "run.log").read_text().count("\n") == 1
        # a note with front matter still dedupes; a stub is recognised
        (d / "a.md").write_text(f"---\ntags: x\n---\n[T](https://www.youtube.com/watch?v={V})\n")
        assert find_existing(d, V) == d / "a.md"
        (d / "b.md").write_text(render({"title": "T"}, V, None, y.NO_CAPS))
        assert is_stub(d / "b.md") and not is_stub(d / "a.md")
        assert not is_stub(Path(d / "c.md").write_text("x") and d / "c.md")
        # clash cap: 99 names then an error
        for _ in range(99):
            write_atomic(d / "I", "N", "x")
        assert raises_os(write_atomic, d / "I", "N", "x")
        # config errors are readable ValueErrors, not tracebacks
        with mock.patch.object(y, "HERE", d):
            assert "not found" in err_of(load_config)
            (d / "config.toml").write_text('vault = "%s"\n' % d)
            assert "missing 'inbox'" in err_of(load_config)
            (d / "config.toml").write_text('vault = "%s"\ninbox = "I"\nnotify = "false"\n' % d)
            assert "true or false" in err_of(load_config)
            (d / "config.toml").write_text('vault = "%s/nope"\ninbox = "I"\n' % d)
            assert "not a folder" in err_of(load_config)
            (d / "config.toml").write_text('vault = [oops\n')
            assert "line 1" in err_of(load_config)
            (d / "config.toml").write_text('vault = "%s"\ninbox = "I"\n' % d)
            assert load_config()["notify"] is True


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
    from unittest import mock
    with mock.patch.object(y, "main", return_value=7), mock.patch.object(y, "repl", return_value=9), \
            mock.patch.object(y, "at_terminal", return_value=False):
        assert cli([]) == 7 and cli(["-i"]) == 9 and cli(["-h"]) == 0 and cli(["--help"]) == 0
        assert cli(["-i", "https://youtu.be/x"]) == 1 and cli(["--bogus"]) == 1


def run_repl(lines, info=None, track=None, retry=None):
    """Drive repl() with scripted input against a tmp vault. Returns (output, tmp Path, opened paths)."""
    import contextlib, io, tempfile
    from pathlib import Path
    from unittest import mock
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
                             notify=lambda m: opened.append(("toast", m)),
                             open_obsidian=lambda v, p: opened.append(("open", p)),
                             clipboard=lambda: "https://youtu.be/" + V), \
            mock.patch("builtins.input", fake_input), contextlib.redirect_stdout(out):
        assert repl() == 0
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
    out, d, _ = run_repl([f"https://youtu.be/{V}", "q"], y.Throttled("429", "throttled by YouTube"))
    assert "stopped: throttled by YouTube" in out and "press r" in out
    assert "1 URL waiting in retry.txt (r to retry)" in out and "1 stopped" in out
    assert (d / "retry.txt").read_text() == f"https://www.youtube.com/watch?v={V}\n"
    # `r`: the saved link leaves the queue; a throttle stops the run and keeps the rest
    info = {"title": "T", "subtitles": {"en": [{"ext": "json3", "url": "u"}]}}
    track = {"events": [{"segs": [{"utf8": "hi"}]}]}
    out, d, _ = run_repl(["r", "q"], info, track, retry=f"https://youtu.be/{V}\n")
    assert "saved (" in out and (d / "retry.txt").read_text() == "" and "waiting" not in out
    two = f"https://youtu.be/{V}\nhttps://youtu.be/AAAAAAAAAAA\n"
    out, d, _ = run_repl(["r", "q"], y.Throttled("429"), retry=two)
    assert out.count("stopped:") == 1 and (d / "retry.txt").read_text() == two
    out, d, _ = run_repl(["r", "q"])
    assert "retry.txt is empty" in out


def test_batch_and_undo():
    ids = ["AAAAAAAAAAA", "BBBBBBBBBBB", "CCCCCCCCCCC"]
    assert urls_in("a\nhttps://youtu.be/x https://youtu.be/y\n") == ["https://youtu.be/x", "https://youtu.be/y"]
    assert urls_in("garbage in here") == ["garbage in here"] and urls_in(" one ") == ["one"]
    info = {"title": "T", "subtitles": {"en": [{"ext": "json3", "url": "u"}]}}
    track = {"events": [{"segs": [{"utf8": "hi"}]}]}
    # a pasted list: each link saved in turn (same title -> numbered names), then undo deletes the last, with a prompt
    out, d, _ = run_repl(["\n".join(f"https://youtu.be/{i}" for i in ids[:2]), "undo", "y", "undo", "n", "q"], info, track)
    assert "[1/2]" in out and "[2/2]" in out and "deleted" in out and "session: 1 saved" in out
    assert [p.name for p in notes(d)] == ["T.md"]  # the clash copy was the one undone
    out, d, _ = run_repl(["undo", "q"])
    assert "nothing to undo" in out
    # a throttle on the first link queues the untried ones, in canonical form, and stops
    out, d, _ = run_repl([" ".join(f"https://youtu.be/{i}?t=5" for i in ids), "q"], y.Throttled("429"))
    assert out.count("stopped:") == 1 and "queued the other 2" in out
    assert (d / "retry.txt").read_text().split() == [f"https://www.youtube.com/watch?v={i}" for i in ids]


def test_update_and_default_mode():
    import contextlib, io
    from unittest import mock
    out = io.StringIO()
    run = lambda rc: mock.Mock(returncode=rc, stdout="", stderr="no network")
    with contextlib.redirect_stdout(out):
        with mock.patch.object(y.subprocess, "run", return_value=run(1)):
            update_ytdlp()
        with mock.patch.object(y.subprocess, "run", return_value=run(0)):
            update_ytdlp()
        with mock.patch.object(y.subprocess, "run", side_effect=KeyboardInterrupt):
            update_ytdlp()
    assert "update failed: no network" in out.getvalue() and "already the latest" in out.getvalue()
    assert "update failed: cancelled" in out.getvalue()
    with mock.patch.object(y, "main", return_value=7), mock.patch.object(y, "repl", return_value=9):
        with mock.patch.object(y, "at_terminal", return_value=True), mock.patch.object(y.signal, "signal"):
            assert cli([]) == 9  # a terminal with no argument gets the prompt
        with mock.patch.object(y, "at_terminal", return_value=False):
            assert cli([]) == 7  # the hotkey has no terminal: clipboard mode


def test_clean_cap_rel():
    assert clean("a\x1b[31m\n b\t") == "a [31m b" and cap("x" * 300).endswith("…") and len(cap("x" * 300)) == 200
    assert rel("/v/Inbox/a.md", "/v") == "Inbox/a.md" and rel("/elsewhere/a.md", "/v") == "/elsewhere/a.md"
    assert len(err_of(lambda: parse_url("x" * 500))) < 100
    import tempfile
    from pathlib import Path
    from unittest import mock
    with tempfile.TemporaryDirectory() as d:
        a, b, gone = (str(Path(d) / n) for n in ("a.md", "b.md", "gone.md"))
        for n in (a, b):
            Path(n).write_text("x")
        rows = [f"t1\tu\tsaved\t", f"t2\tu\tstub\tno captions | {a}", f"t3\tu\tsaved\t{b}", f"t4\tu\tsaved\t{gone}",
                "t5\tu\tfailed\tx"]
        (Path(d) / "run.log").write_text("\n".join(rows) + "\n")
        with mock.patch.object(y, "LOG", Path(d) / "run.log"):
            assert recent_saves() == [("t2", a), ("t3", b)]  # old row, deleted note, failure: all left out
            assert recent_saves(1) == [("t3", b)]


if __name__ == "__main__":
    for name, f in list(globals().items()):
        if name.startswith("test_"):
            f()
            print("ok", name)
