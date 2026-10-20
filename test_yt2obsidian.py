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


if __name__ == "__main__":
    for name, f in list(globals().items()):
        if name.startswith("test_"):
            f()
            print("ok", name)
