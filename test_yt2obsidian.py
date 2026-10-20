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
                             LOG=d / "run.log", RETRY=d / "retry.txt",
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
    with mock.patch.object(y, "main", return_value=7), mock.patch.object(y, "repl", return_value=9):
        assert cli([]) == 7 and cli(["-i"]) == 9 and cli(["-h"]) == 0 and cli(["--help"]) == 0
        assert cli(["-i", "https://youtu.be/x"]) == 1 and cli(["--bogus"]) == 1


if __name__ == "__main__":
    for name, f in list(globals().items()):
        if name.startswith("test_"):
            f()
            print("ok", name)
