# Build Plan: yt2obsidian

Source of truth for behavior: `PRD.md`. This file is the execution order. Written for the builder (Claude), not for humans.

## Decisions (made, don't re-litigate)

- **One file**: `yt2obsidian.py` (~250 lines). Split only if it passes ~400.
- **One dependency**: `yt-dlp` as a Python library, in `.venv`. It returns title, channel, upload_date, `live_status`, `availability`, and caption tracks in a single call. `youtube-transcript-api` would need a second call for metadata. Fallback if yt-dlp misbehaves: swap `fetch()` only.
- **Config**: `config.toml` read with stdlib `tomllib`. Keys: `vault`, `inbox`, `timeout` (30), `retries` (3). Copy from `config.example.toml`; real `config.toml` is gitignored.
- **State files** next to the script: `run.log`, `retry.txt` (one URL per line). Both gitignored.
- **Tests**: `test_yt2obsidian.py`, plain `assert`s on pure functions, run with `python test_yt2obsidian.py`. No pytest.
- **Open questions, defaults**: date = publish date. Fetch failure (non-throttle) = retry, then stub. Hyprland keybind = skipped in v1 (one-line snippet in README at the end).
- **Vault name for Obsidian URI**: the basename of `vault` path.

## Module layout (functions, in file order)

| Function | Pure? | Job |
|---|---|---|
| `load_config()` | no | read `config.toml`, apply defaults, expand `~` |
| `get_url(argv)` | no | argv[1] else `wl-paste` |
| `parse_url(s) -> (vid, kind)` | yes | regex; kind is `video` or `short`; raises on non-YouTube |
| `fetch(vid, cfg) -> info` | no | yt-dlp `extract_info(download=False)` with socket timeout and retries; raises `Throttled` on 429/bot-check |
| `pick_track(info) -> url or None` | yes | English only (`en*`), manual before auto, json3 format |
| `transcript_text(track_json) -> str` | yes | join segments, collapse whitespace |
| `stub_reason(info, exc) -> str` | yes | map live/upcoming/private/members/age/no-captions to PRD wording |
| `safe_name(title) -> str` | yes | strip bad chars, drop emoji and non-ASCII, collapse spaces, cap to 255 bytes minus `.md` and ` (99)` |
| `find_existing(inbox, vid) -> Path or None` | no | scan `*.md` for `youtube.com/watch?v=<vid>` |
| `render(info, vid, text, reason) -> str` | yes | note body per PRD 7.4 |
| `write_atomic(inbox, name, body)` | no | tmp file in same dir, `os.replace`; numbered suffix on name clash; never overwrite |
| `notify(msg)` / `open_obsidian(vault, path)` | no | `notify-send`; `xdg-open obsidian://open?vault=..&file=..` (URL-encode) |
| `main()` | no | orchestrate; log every run; exit codes |

## Phases

Each phase ends with a verifiable check. Do not start the next until the check passes. Commit after each phase.

### Phase 0: Scaffold (~5 min)
- `python -m venv .venv && .venv/bin/pip install yt-dlp`
- `.gitignore`: `.venv/`, `config.toml`, `run.log`, `retry.txt`, `__pycache__/`
- `config.example.toml`, empty `yt2obsidian.py` with `main()` stub.
- **Check**: `.venv/bin/python -c "import yt_dlp"` works. Ask user for vault path and inbox folder, write `config.toml`.

### Phase 1: Pure core, test-first (~20 min)
- Write `parse_url`, `safe_name`, `pick_track`, `transcript_text`, `stub_reason`, `render`.
- Tests cover: watch / youtu.be / extra params / `m.youtube.com` / `/shorts/` / `/live/` / `/embed/` / garbage; emoji and CJK stripped; all 9 forbidden chars; 255-byte cap with multibyte; manual beats auto; `en-GB` accepted, `fr` rejected; whitespace collapse; each stub reason; render with and without transcript.
- **Check**: `python test_yt2obsidian.py` passes.

### Phase 2: Fetch against real YouTube (~20 min)
- `fetch()` + `get_url()` + config load. Print the info and transcript to stdout; no writing yet.
- Hand-test with real URLs: captioned video, no-captions video, live/upcoming. Record the exact yt-dlp field values and error strings for private/members/age-restricted in a comment above `stub_reason`, then fix any wrong guesses. Sourcing private/members test URLs: ask the user, or fall back to a mocked `info` dict in tests.
- **Check**: the three videos print sane title, channel, date, status, transcript start.

### Phase 3: Write path (~20 min)
- `find_existing`, `write_atomic`, `open_obsidian`, `notify`, wire `main()`: parse -> dedupe (before any network call) -> fetch -> render -> write -> print path -> notify -> open.
- Tests: tmp-dir test for dedupe by video ID, name-clash suffix `(2)`, no overwrite, no leftover `.tmp` on a simulated failure.
- **Check**: run against a real URL into the real inbox. Note appears, Obsidian opens it, notification fires. Second run reports "already saved" and writes nothing.

### Phase 4: Failure paths (~20 min)
- Retries (cfg count) on network errors only. Timeout from cfg.
- `Throttled`: stop immediately, append URL to `retry.txt`, notify which failed, exit non-zero. No stub.
- Non-throttle fetch failure after retries: stub per default decision.
- Shorts: print skip message, exit 0, no log noise beyond one line.
- `run.log`: one line per run: ISO time, URL, outcome (`saved` / `stub` / `duplicate` / `skipped` / `failed`), error.
- Tests: monkeypatch `fetch` to raise `Throttled` / timeout; assert retry file, log line, exit code.
- **Check**: all 9 PRD section-10 cases pass (real where possible, mocked for throttle/private/members).

### Phase 5: Wrap (~10 min)
- 15-line README: setup, run, Hyprland bind snippet (`bind = SUPER, Y, exec, <path>/.venv/bin/python <path>/yt2obsidian.py`), how to update yt-dlp (`pip install -U yt-dlp`, the thing that breaks first).
- Final read-through for comment density, dead code.
- **Check**: fresh clone-style run from README steps works.

## Known risks to watch while building

- yt-dlp may need a JS runtime or hit bot-check on some videos; if so, treat as `Throttled`, don't work around it.
- `wl-paste` prints a trailing newline and may return non-text; strip and validate.
- Obsidian URI needs the vault *name* as registered in Obsidian; if the basename guess is wrong, ask the user.
- Stripping all non-ASCII can leave an empty filename; fall back to `video-<id>`.
