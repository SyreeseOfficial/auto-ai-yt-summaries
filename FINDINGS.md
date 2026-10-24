# yt2obsidian — Findings

Rounds 1 and 2 (both 2026-10-23), against `yt2obsidian.py` as of commit `293baf7`. This file lists **new** ideas only: anything already tracked in `IMPROVEMENTS.md` (300 items, most done) is not repeated except where the code still shows it undone (marked "still open"). Items marked [PRD] change a decision in `PRD.md` and need your yes first. Items run or reproduced today say "run today"; everything else is read from the code.

Effort: **XS** under 5 min · **S** about 15 min · **M** about an hour · **L** half a day. Sorted by value, then effort, then area.

**311 items.** 15 high, 192 medium, 104 low.

## Do these first

1. Bracket stripping eats real text _[Bug, XS]_
2. The word "youtube" counts as a link _[Bug, XS]_
3. Tests write to the real run.log _[Bug, XS]_
4. README says Python 3.14 tested but `requirements.txt` has only the yt-dlp floor; add `python_requires`… _[Docs, XS]_
5. `edit_config` breaks a symlinked config _[Bug, S]_
6. `find_existing` can match the wrong video _[Bug, S]_
7. An empty-event json3 body produces a false "no captions" stub that permanently blocks the video via dedupe _[Bug, S]_
8. Update PRD §4 to match reality _[Docs, S]_

## High value

1. [ ] **[XS]** _Bug_ — Bracket stripping eats real text. `transcript_text` removes every `[...]`, so a manual caption saying "use arr[i] and [Music] here" becomes "use arr and here" (run today). Only strip brackets that look like sound tags (letters/spaces/underscores, e.g. `[Music]`, `[ __ ]`), or only on auto tracks.
2. [ ] **[XS]** _Bug_ — The word "youtube" counts as a link. `urls_in("youtube is great https://youtu.be/dQw4w9WgXcQ")` returns `['youtube', 'https://...']` (run today), so the batch prints a `failed: not a YouTube URL: 'youtube'` for the stray word. Require `://` or a `.`/`/` in the token, or reuse `parse_url` to filter.
3. [ ] **[XS]** _Bug_ — Tests write to the real run.log. `run.log` holds three `u failed boom [yt-dlp ...]` rows from 14:14-14:20 on 2026-10-20 that came from the test suite, so your watch history is polluted by every test run. Point `LOG`, `RETRY`, `LOCK`, `HISTORY` at a temp dir in the test runner.
4. [ ] **[XS]** _Docs_ — README says Python 3.14 tested but `requirements.txt` has only the yt-dlp floor; add `python_requires` equivalent (a check at import: `sys.version_info >= (3, 11)` with a readable error) because `tomllib` fails with a bare ImportError on 3.10.
5. [ ] **[S]** _Bug_ — `edit_config` breaks a symlinked config. `config.toml` kept in a dotfiles repo and symlinked in gets replaced by a regular file on the first settings change (`os.replace` on the symlink path). Resolve the path first: `path = (HERE / "config.toml").resolve()`.
6. [ ] **[S]** _Bug_ — `find_existing` can match the wrong video. It looks for `watch?v=<id>` anywhere in the first 1 KB of every note, so a note that merely quotes another video's link (a description pasted at the top, a related-video list) makes that other video look like a duplicate and the save is refused. Anchor the match to the note's link line (or the frontmatter `url:`).
7. [ ] **[S]** _Bug_ — An empty-event json3 body produces a false "no captions" stub that permanently blocks the video via dedupe. Retry once, and if it is still empty write the stub with reason "caption track was empty" so `restub` can find it.
8. [ ] **[S]** _Docs_ — Update PRD §4 to match reality. It still lists "no playlist or channel processing" and "no background service" while this file proposes timers; decide once and write the rule down so later items can cite it.
9. [ ] **[S]** _Input_ — Timestamp links lose their start time. Pasting `youtu.be/ID?t=90` saves a note linking to the bare watch URL (`parse_url` drops `t`). Keep `&t=` in the note's link line (not in the dedupe key).
10. [ ] **[S]** _Network_ — Add a delay between batch items. `batch()` fires one fetch right after another; pasting 20 links is the likeliest way to get a 429. Sleep 1-3 s (jittered) between items after the first, setting `batch_delay`.
11. [ ] **[S]** _Obsidian_ — Optional YAML frontmatter. Obsidian properties, Dataview and Bases only read frontmatter, so today none of the notes' metadata (channel, date, url, duration) is queryable. Add `frontmatter = true` that writes `---\nurl:\nchannel:\ndate:\nduration:\n---` and teaches `find_existing`/`is_stub` to read it. [PRD: metadata layout is in §7.4]
12. [ ] **[S]** _Reliability_ — Add a per-URL overall deadline. `timeout` is per socket read and `retries` multiplies it, so a hung fetch can sit for `timeout x retries x 2 calls` (90 s with your 30 s setting) while a hotkey run shows nothing. Wrap `_process` in a wall-clock limit (e.g. `signal.alarm`) and queue the URL on expiry.
13. [ ] **[S]** _Tests_ — Run the tests in CI-like isolation: `python -I`, `HOME` set to a temp dir, no network. The suite imports the real module with the real `HERE`, so a dev's own `config.toml` or `retry.txt` could change results.
14. [ ] **[S]** _Transcript_ — Videos with no English captions become stubs even when a transcript exists. The stub says `no English captions (found: fr, de)` and stops. Add a `languages = ["en"]` setting (ordered) and fall back to the video's own `info["language"]` track, then note which language was used.
15. [ ] **[M]** _Automation_ — Retry queue is manual only. A throttle queues the URL and then nothing happens until you press `r`. Add a systemd user timer (`yt --retry` every 30 min, `OnFailure` quiet) and ship the unit files in the repo.

## Medium value

16. [ ] **[XS]** _Bug_ — `urls_in` splits `a,b` pastes wrong. Two links joined by a comma or semicolon (`url1,url2`) stay one token and fail as "no video id". Split on `[\s,;]+`.
17. [ ] **[XS]** _Bug_ — `parse_url` is case-sensitive in places. `HTTPS://WWW.YOUTUBE.COM/WATCH?V=dQw4w9WgXcQ` is rejected (run today) because the path `WATCH` and query key `V` are compared exactly; a caps-lock paste or an uppercased link from a chat client fails with "no video id". Lowercase the path's first segment and the query keys before matching.
18. [ ] **[XS]** _Bug_ — A pasted link with a trailing encoded space (`...v=dQw4w9WgXcQ%20`) fails with "no video id in URL" (run today); `unquote` the query value before validating, and strip control characters from the whole paste first.
19. [ ] **[XS]** _Filename_ — Titles that are only digits (`2024`) or look like dates (`2026-10-23`) are saved as such and sort oddly among date-named notes; add an optional prefix/suffix (`Title [id]`) setting to keep names unique and recognizable.
20. [ ] **[XS]** _Input_ — `youtube.com/watch/<id>` (a path-style watch link some bots produce) is rejected (run today); accept `/watch/<id>` and `/e/<id>` the same way `/v/<id>` is accepted.
21. [ ] **[XS]** _Input_ — `youtu.be/-----------` parses as a valid ID because `ID_RE` allows all 11-character strings of `[A-Za-z0-9_-]`; it only fails later at YouTube. Reject IDs that are all `-`/`_` (no real ID is) to fail fast with a clear message.
22. [ ] **[S]** _Bug_ — `rglob("*.md")` in `find_existing` descends into hidden folders (`.trash`, `.git`, `.obsidian/plugins/*/README.md`) if the inbox ever holds them. Skip dot-directories.
23. [ ] **[S]** _Bug_ — The settings menu `d` (reset) rewrites only keys already present in `config.toml`; keys the user deleted are not restored, so "reset to defaults" can leave an unset key at its default silently while the menu shows the default. Verify and print which keys were reset.
24. [ ] **[S]** _Bug_ — `parse_setting` for `str` settings (`inbox`) accepts a value with leading/trailing quotes pasted from TOML (`"Transcripts"` with quotes) and creates a folder literally named with quote characters. Strip one layer of matching quotes.
25. [ ] **[S]** _Bug_ — `show_setting` for a bool-or-dict `notify` uses `allowed[v]`; a hand-edited unknown value raises KeyError inside the menu before validation runs (load_config rejects first, but only on reload). Test the path.
26. [ ] **[S]** _Bug_ — `recent_saves` splits on the last ` | ` to find the path, so a note path containing ` | ` (the allowlist excludes `|`, but older notes may include it) is cut wrong. Store the path in its own column.
27. [ ] **[S]** _Bug_ — `stub_reason` returns `transcript fetch failed: ...` for any other exception text, which becomes permanent stub text; it includes the yt-dlp message (possibly with a URL and request details). Truncate and strip URLs from it before writing it into a note.
28. [ ] **[S]** _Bug_ — `render` interpolates `info.get('title')` into the stub's `Title:` line without `clean()`; a title containing a newline or `---` would add lines to the note's header. Run it through `clean`.
29. [ ] **[S]** _Bug_ — `render` for transcript notes uses `title.replace("[", "(")` but not `|` or backticks; a title with a backtick or `]` run can break the link line in some Markdown renderers. Escape those too.
30. [ ] **[S]** _Bug_ — `render` writes `Date: unknown` for livestream archives lacking `upload_date` even though `release_timestamp` exists; fall back to it.
31. [ ] **[S]** _Bug_ — `Duration` of 0 seconds (`info["duration"] == 0`) is falsy and omitted; fine for live, but a real 0:30 short video prints correctly while 0 prints nothing. Use `is not None`.
32. [ ] **[S]** _Bug_ — `watch_url` always writes `www.youtube.com`; videos pasted from `music.youtube.com` are saved with a normal watch link, which is good, but the original host is lost. Log it in the detail column.
33. [ ] **[S]** _Bug_ — `toast` with `mode == "auto"` and `repl=False` relies on `sys.stdin.isatty()`; a hotkey run started from a terminal multiplexer pane has a tty and never toasts. Add `--notify` to force it, and mention the case in the README.
34. [ ] **[S]** _Bug_ — `get_url` strips only whitespace; a clipboard holding several lines (a copied paragraph with a link) is passed whole to `urls_in`, which handles it, but a clipboard with 5,000 lines is read fully into memory. Cap clipboard size at 10 KB.
35. [ ] **[S]** _Bug_ — `wl-paste --type text` with no `WAYLAND_DISPLAY` (SSH session, tty) hangs or errors; add a clear "no Wayland session" message and optional `xclip`/`xsel`/`pbpaste` fallbacks.
36. [ ] **[S]** _Bug_ — `clipboard()` timeout of 5 s raises `TimeoutExpired`, a `SubprocessError` caught in `main` but not in the REPL path's `url = line or clipboard()` ... it is, via the tuple; add a test since the tuple is easy to break.
37. [ ] **[S]** _Bug_ — `with_retries` retries `RequestError` that are not transient (e.g. SSL certificate failures are `TransportError` subclasses) three times with sleeps. Treat `CertificateVerifyError` as final.
38. [ ] **[S]** _Bug_ — `fetch_track` ignores `HTTPError` 5xx beyond retries; the track URL returning 200 with an empty body (`{}`) yields `transcript_text == ""` and a "no captions" stub though captions exist. Treat an empty parse as a retryable failure once.
39. [ ] **[S]** _Bug_ — `urls_in` runs on clipboard text from `wl-paste`, which can contain `\r\n`; `split()` handles it, but `get_url` returns the stripped text for logging; verify CRLF clipboards from Windows apps.
40. [ ] **[S]** _CLI_ — `--dry-run`: parse, fetch, render, print the note and the destination, write nothing. Cheapest way to test a filename or template change.
41. [ ] **[S]** _CLI_ — `--json` output for scripting: one line per URL with `{outcome, path, title, seconds}`. `Result` already has the fields.
42. [ ] **[S]** _CLI_ — `-q/--quiet` for cron/timer runs: print only failures.
43. [ ] **[S]** _CLI_ — `--vault` and `--inbox` flags to override config for a single run (useful for a second vault).
44. [ ] **[S]** _CLI_ — Read URLs from stdin or a file: `yt -f urls.txt` and `echo url | yt -`. Today batches only come from a paste.
45. [ ] **[S]** _CLI_ — `yt --list-stubs` prints the stub notes with their reason and age (`is_stub` already detects them) so you know what could be retried.
46. [ ] **[S]** _CLI_ — `--version` flag printing the tool, yt-dlp, Python and JS-runtime versions; the info you paste into a bug report.
47. [ ] **[S]** _CLI_ — `--check` doctor command: config readable, vault exists, wl-paste/notify-send/xdg-open on PATH, a JS runtime found, yt-dlp version fresh, lock file writable. One screen replaces the README troubleshooting list.
48. [ ] **[S]** _CLI_ — Exit code 3 for "saved a stub" so a script can tell stub from full save; today both are 0.
49. [ ] **[S]** _CLI_ — `--print-path` (print only the note path to stdout, everything else to stderr) so scripts can do `yt --print-path URL | xargs nvim` or `obsidian` URIs without parsing human output.
50. [ ] **[S]** _CLI_ — `--config PATH` and `YT2OBSIDIAN_CONFIG` for testing a second vault without touching `config.toml` (a single-line change in `load_config`).
51. [ ] **[S]** _CLI_ — `--version` printing tool version (git describe), yt-dlp, Python, JS runtime (`node`/`deno` path and version), and `wl-paste`/`notify-send`/`xdg-open` availability; paste it into bug reports.
52. [ ] **[S]** _CLI_ — `--no-color` flag in addition to the `NO_COLOR` environment variable, for terminals where setting env vars is awkward (e.g. a Hyprland bind).
53. [ ] **[S]** _CLI_ — `yt --log [N]` pretty-prints the last N rows of `run.log` with colors and aligned columns; today the file is tab-separated and needs `column -t`.
54. [ ] **[S]** _CLI_ — `yt --failures` lists failed URLs grouped by reason from `run.log` with a one-line fix per reason (stale yt-dlp, throttled, restricted) and `--retry-failed` to re-queue them.
55. [ ] **[S]** _CLI_ — Shell completion (bash/zsh/fish) for flags; the flag set is small and static, so a hand-written completion file in the repo is enough.
56. [ ] **[S]** _Code health_ — `_process` is ~55 lines with 8 return paths; extract `fetch_everything(vid, cfg) -> (info, text, exc)` and `save(info, text, reason, cfg)` so each is testable without mocking YoutubeDL.
57. [ ] **[S]** _Code health_ — `finish` takes 11 parameters; return a small dataclass from `_process` and let the caller print/log. `Result` is already the carrier.
58. [ ] **[S]** _Code health_ — Module-level `LOG/RETRY/LOCK/HISTORY` globals force tests to monkeypatch the module; pass a `Paths` object (or `state_dir`) into functions instead.
59. [ ] **[S]** _Code health_ — `SETTINGS` mixes UI labels, defaults and validation in one dict of tuples; a tiny `Setting` dataclass reads better and makes the menu easier to extend.
60. [ ] **[S]** _Code health_ — Split the 800-line file once it passes ~1000 lines: `urls.py`, `transcript.py`, `config.py`, `repl.py`. Today one file is fine and easier to ship; revisit at the next feature.
61. [ ] **[S]** _Code health_ — Type hints on the public functions plus `python -m mypy --strict` once; `Result` fields and the `info` dict shape get documented for free.
62. [ ] **[S]** _Code health_ — Run `ruff check` and `ruff format --check` once (IMPROVEMENTS #292) and add a `[tool.ruff]` section with line length 140 to match the file.
63. [ ] **[S]** _Config_ — Move runtime files (`run.log`, `retry.txt`, `.history`, `.lock`) to `$XDG_STATE_HOME/yt2obsidian/` and config to `$XDG_CONFIG_HOME`. Right now a `pipx`/symlinked install writes into the install directory.
64. [ ] **[S]** _Config_ — `HERE`-relative state files break when the project is read-only or lives on a sync folder; the XDG move fixes both.
65. [ ] **[S]** _Config_ — Validate `notify` value case-insensitively ("Always" now errors) and print the allowed list with the config path.
66. [ ] **[S]** _Config_ — Reload-on-change: the REPL calls `load_config` per line; cache by mtime to skip the read, and show a one-line diff of changed keys when it differs.
67. [ ] **[S]** _Config_ — `vault` accepts `$VAR` expansion (`os.path.expandvars`) so one config works across machines.
68. [ ] **[S]** _Config_ — Add `max_name = 120` setting for filename length and `ascii_names = false` to keep Unicode letters (IMPROVEMENTS #167 left it as a PRD question).
69. [ ] **[S]** _Config_ — Add `lang_fallback`, `batch_delay`, `frontmatter`, `template` to `config.example.toml` as commented examples once each exists.
70. [ ] **[S]** _Config_ — `inbox` is created silently (`mkdir(parents=True)`) on first save; a typo creates a new folder in the vault. Ask once on first creation (REPL) or require `inbox_create = true` for hotkey runs.
71. [ ] **[S]** _Config_ — `vault` accepts one path; support `vaults = [...]` with a `--vault NAME` selector for people with a work and personal vault.
72. [ ] **[S]** _Config_ — Document and validate every key in a `config.schema.md` (or print a table with `yt --settings --explain`); errors name the file but not the allowed values for strings like `notify`.
73. [ ] **[S]** _Docs_ — Add a 10-line "Architecture" section to the README: the order of stages (parse, dedupe, fetch, track, render, write, open, log, toast) and where each lives.
74. [ ] **[S]** _Docs_ — Document `retry.txt` format and that you can edit it by hand.
75. [ ] **[S]** _Docs_ — Document the lock behavior and that a stale `.lock` file is harmless (it is the flock, not the file).
76. [ ] **[S]** _Docs_ — Add a troubleshooting row for "wl-paste: Nothing is copied" and for running under X11 (the tool is Wayland-only).
77. [ ] **[S]** _Docs_ — Add a CHANGELOG.md; the git log has section letters (A-Q) that mean nothing to a future reader.
78. [ ] **[S]** _Docs_ — Record the IMPROVEMENTS.md "not done" items in one place; there are 20+ spread over 17 section banners.
79. [ ] **[S]** _Docs_ — README: add a GNOME/KDE/Hyprland keybinding table and a macOS/X11 note, a sample note screenshot, and a "what the stub looks like" example.
80. [ ] **[S]** _Docs_ — PRD says "no timestamps, tags, thumbnails"; list the current deviations (Duration, Saved date) in one "decisions log" table with dates so the PRD stays true.
81. [ ] **[S]** _Docs_ — Document how dedupe works (first 1 KB, watch/youtu.be forms) and what breaks it (frontmatter longer than 1 KB, a note whose link line was edited); users who add frontmatter must know.
82. [ ] **[S]** _Docs_ — Document the exit codes in `--help` per outcome and add a short "using it in a script" section (examples with `--print-path`, exit code 2 for throttle).
83. [ ] **[S]** _Features_ — Import from Watch History export / a text file of URLs with progress and resume (retry queue already gives resume).
84. [ ] **[S]** _Filename_ — Support a `Title [videoId].md` naming mode: the ID in the name makes duplicates impossible to miss, survives cross-device sync races (two machines saving the same video produce the same filename, which Obsidian Sync turns into one conflict instead of two notes), and lets `find_existing` match by filename first.
85. [ ] **[S]** _Filename_ — Strip emoji and decorative symbols from titles explicitly (they are already dropped by the allowlist) but keep a count: when more than half of a title is removed (e.g. "🔥🔥 ULTIMATE ...") fall back to the channel-name form, which reads better than a stub-like remainder.
86. [ ] **[S]** _Input_ — Share-sheet and redirect wrappers are not understood. `youtube.com/attribution_link?u=%2Fwatch%3Fv%3D<id>` (what the mobile share menu emits) fails (run today), as do `youtube.com/redirect?q=<encoded url>` and `youtube.com/oembed?url=`. Unwrap one level of these and re-run `parse_url` on the inner URL.
87. [ ] **[S]** _Logging_ — Add a `--stats` command (counts by outcome, average seconds, failures by yt-dlp version). IMPROVEMENTS #241 said `cut | uniq -c` is enough; add it only if you want failure-by-version.
88. [ ] **[S]** _Logging_ — Log rotation by size (1 MB): keep `run.log.1`. At 7 rows it is irrelevant now; only needed once automation (timer, `watch`) lands.
89. [ ] **[S]** _Logging_ — Log the `Captions` kind and language used, so failures can be correlated with auto vs manual tracks.
90. [ ] **[S]** _Logging_ — Add a `-v` debug flag that sends yt-dlp's logger to stderr instead of `Quiet` (a stderr dump is the first thing you want when a new extractor error appears).
91. [ ] **[S]** _Logging_ — Save the raw `info` JSON of failed runs to `failures/<id>.json` (gitignored, last 20 kept) so a bug can be reproduced offline and turned into a fixture.
92. [ ] **[S]** _Network_ — Respect `HTTPS_PROXY`/`all_proxy` and a `proxy` setting; yt-dlp supports it and the caption `urlopen` goes through the same handler, so one option covers both.
93. [ ] **[S]** _Network_ — Backoff for 429: after a throttle, record `retry_after` in `retry.txt` so `--retry` skips entries before then instead of re-hitting YouTube immediately.
94. [ ] **[S]** _Network_ — Pre-flight DNS check so a dead network fails in ~1 s with "offline" instead of waiting `timeout x retries` (IMPROVEMENTS #207 never landed).
95. [ ] **[S]** _Network_ — Distinguish "offline" from "YouTube blocked this IP" in the stop message; the second needs a VPN/cookies, the first needs nothing.
96. [ ] **[S]** _Network_ — Retry the info fetch with a different `player_client` (`web`, `tv`, `android`) on `nsig`/extract failures before giving up; yt-dlp exposes this as an extractor arg.
97. [ ] **[S]** _Network_ — Log which `player_client` succeeded in run.log so a pattern of one client failing becomes visible.
98. [ ] **[S]** _Note format_ — Put the video description in the note (below the transcript, collapsed in a `> [!note]- Description` callout). Descriptions often hold the links and chapter list you wanted to keep. [PRD]
99. [ ] **[S]** _Note format_ — Add the channel as a wikilink (`[[Channel Name]]`) so channel pages auto-build in graph view. [PRD: related-note links are out of scope]
100. [ ] **[S]** _Note format_ — Add the YouTube category and tags as a `Tags:` line, converted to Obsidian-safe `#tags`. [PRD: tags are out of scope]
101. [ ] **[S]** _Note format_ — Chapter headings (`## 03:12 Chapter title`) from `info["chapters"]`; the chapter titles are in the fixture's info already. See IMPROVEMENTS #159.
102. [ ] **[S]** _Note format_ — Stub notes should record the date they were created and the yt-dlp version, so `stubs` can tell which are old enough to retry.
103. [ ] **[S]** _Note format_ — Titles containing `\`, `<` or `>` are written unescaped into the link text. A title like `AC\DC <live>` renders as broken Markdown/HTML in Obsidian reading view; escape backslashes and replace `<`/`>` the same way `[`/`]` are replaced in `render`.
104. [ ] **[S]** _Note format_ — Escape a leading `#`, `>`, `-`, `+` or digit-period at the start of each transcript paragraph so a sentence starting "1. First" or "# hashtag" doesn't turn into a list or heading in Obsidian.
105. [ ] **[S]** _Note format_ — `Saved:` uses the machine's local date and never the time; two saves of different videos on the same day cannot be ordered. Add `Saved: 2026-10-23 14:05` (local time with offset) so a Dataview query can sort by capture order.
106. [ ] **[S]** _Note format_ — Include `Language: en` and `Source: auto|manual` in the metadata block (the track kind is known at `pick_track`); a reader can then trust or discount the text, and a future re-fetch can target auto-caption notes only.
107. [ ] **[S]** _Note format_ — Add `Views` and `Uploader URL` lines (both are in `info`) behind a `extra_meta = true` setting; they make a note self-contained when the video later disappears.
108. [ ] **[S]** _Note format_ — Record the chapter list as a bullet list of `[mm:ss](url&t=)` links above the transcript when chapters exist, even before paragraph breaks are built; chapter titles are the cheapest table of contents.
109. [ ] **[S]** _Note format_ — When a video is later deleted or goes private, the note keeps working but nothing says so. Add a `Status: available|gone` line that a `--check` run can update by probing `watch_url` with a HEAD-like yt-dlp call.
110. [ ] **[S]** _Notifications_ — Clickable toast: `notify-send --action=open=Open` then `xdg-open` the note. Needs a `--wait` background thread; or use `dunstify`/`mako` actions where available.
111. [ ] **[S]** _Notifications_ — Reuse one toast per batch via `-h string:x-canonical-private-synchronous:yt2obsidian` so 10 links produce one updating notification, not ten.
112. [ ] **[S]** _Notifications_ — A batch summary toast ("8 saved, 1 stub, 1 failed") instead of per-video toasts in hotkey mode.
113. [ ] **[S]** _Notifications_ — Add the channel name to the toast body so two videos with similar titles are distinguishable.
114. [ ] **[S]** _Notifications_ — Set a notification icon (`-i`) from the system theme (`text-x-generic` / `emblem-documents`).
115. [ ] **[S]** _Obsidian_ — `obsidian://open` opens the vault root note instead of the file when the path contains `%2F`? Verify on your Obsidian version; if it misbehaves use `obsidian://open?vault=<name>&file=<relative path>`.
116. [ ] **[S]** _Obsidian_ — Append a link to today's daily note (`- [[Title]]` under a `## Watched` heading). A common reason people save transcripts is "what did I watch this week". [PRD]
117. [ ] **[S]** _Obsidian_ — Warn when the inbox folder is excluded in Obsidian's `app.json` `userIgnoreFilters`; notes saved there never appear in search or graph.
118. [ ] **[S]** _Obsidian_ — Respect the vault's "new note location" if no inbox is configured (read `.obsidian/app.json`), so a first-run user needs only `vault`.
119. [ ] **[S]** _Packaging_ — Pin an upper bound for yt-dlp in a lock file (`requirements.lock`) while keeping the floor in `requirements.txt`; a known-good pair is more useful than "latest" when YouTube changes.
120. [ ] **[S]** _Packaging_ — `yt` wrapper fails with an unhelpful `No such file` if `.venv` is missing; check and print the two setup commands.
121. [ ] **[S]** _Packaging_ — Provide a `.desktop` file so the tool can be launched from the app menu and registered as a handler for `yt2obsidian://` (a bookmarklet could then send the current tab).
122. [ ] **[S]** _Perf_ — Open the YoutubeDL object once per run. `fetch` and `fetch_track` each construct and tear down a `YoutubeDL`; reusing one halves setup and keeps cookies/headers the same between info and caption calls.
123. [ ] **[S]** _Perf_ — Avoid format extraction. `extract_info` resolves every format, which is what needs the JS runtime and triggers `nsig` failures, yet only captions are used. Try `extractor_args={"youtube": {"skip": ["hls", "dash", "translated_subs"]}}` and measure time and failure rate before/after on the fixtures.
124. [ ] **[S]** _Perf_ — Print timing per stage (info 1.9 s, captions 0.4 s) at `-v`. Right now you cannot tell whether slowness is YouTube, the JS runtime or the disk.
125. [ ] **[S]** _Platform_ — Clipboard/open/notify are Linux-Wayland-only (`wl-paste`, `xdg-open`, `notify-send`). Put them behind a small `platform.py` with macOS (`pbpaste`, `open`, `osascript`), X11 (`xclip`/`xsel`) and Windows (`clip`/PowerShell) implementations so the tool can be shared.
126. [ ] **[S]** _Platform_ — Detect the desktop session and give a specific message for the common failure (no `WAYLAND_DISPLAY` under SSH/tmux) with the fix (`export WAYLAND_DISPLAY=wayland-1`), rather than "clipboard is empty or not text".
127. [ ] **[S]** _Platform_ — GNOME/KDE notification fallbacks (`gdbus` Notifications, `kdialog --passivepopup`) when `notify-send` is missing; and a terminal-bell fallback for headless runs.
128. [ ] **[S]** _Platform_ — Provide a `.desktop` file and a `yt2obsidian://` URL handler script for browser bookmarklets (`javascript:location.href='yt2obsidian://save?url='+encodeURIComponent(location.href)`), avoiding the clipboard hop.
129. [ ] **[S]** _Quality_ — Replace the ad-hoc test runner (`test_yt2obsidian.py`, `__main__` loop) with `pytest` (or `unittest` discovery) so failures report one-by-one and CI can parallelize; keep the offline default and the `--live` marker.
130. [ ] **[S]** _Quality_ — Add golden-note tests for unusual videos built from real `info` dicts: live, upcoming/premiere, members-only, age-gated, 12-hour stream (duration over 10 hours: `Duration: 12:05:03`), Shorts, music with lyrics, non-English only; commit trimmed fixtures like `rick_info.json`.
131. [ ] **[S]** _Quality_ — Run the suite with `python -W error -X dev` to surface ResourceWarnings (unclosed files in `find_existing` readers, lingering `Popen` handles from `notify`/`open_obsidian`).
132. [ ] **[S]** _Quality_ — Reap child processes: `notify()` and `open_obsidian()` use `Popen` without `wait`, leaving zombies in a long REPL session (one per toast/open). Use `start_new_session=True` and a tiny reaper, or `subprocess.Popen(...).wait` in a thread.
133. [ ] **[S]** _Quality_ — Type the module (`Result`, config dict, info dict subset as `TypedDict`) and run `mypy`; most helpers take loose dicts, and the `info` keys read are an implicit contract.
134. [ ] **[S]** _Quality_ — Split the 800-line module along its natural seams (`urls.py`, `ytdlp.py`, `notes.py`, `config.py`, `repl.py`) once the next feature lands; tests already import the module as a whole, so keep a thin `yt2obsidian.py` re-export.
135. [ ] **[S]** _Quality_ — Add `ruff format` + `ruff check` with the line length the file already uses, and a pre-commit hook; a first run will likely flag the long lines and one-line `if` bodies.
136. [ ] **[S]** _REPL_ — `l` should print numbers and let `o 2` open the second entry (today `o` opens only the last note).
137. [ ] **[S]** _REPL_ — Tab-complete the command words (`undo`, `settings`, `retry`) with `readline.set_completer`.
138. [ ] **[S]** _REPL_ — Add `stubs` and `queue` commands that list stubs and `retry.txt` entries with their URLs.
139. [ ] **[S]** _REPL_ — Show the count of queued retries in the banner when `retry.txt` is non-empty.
140. [ ] **[S]** _REPL_ — `undo` only covers this session's last save. Let `undo 2` or `undo all` step back further, and also remove the matching `retry.txt`/log row consistently.
141. [ ] **[S]** _REPL_ — `!!`-style repeat: Enter on an empty line pastes the clipboard (done), but there is no way to re-run the previous failed URL. `again` re-runs the last non-saved URL.
142. [ ] **[S]** _REPL_ — Echo "queued N links, working..." with a progress line `[3/12] title` for batches, replacing bare `[3/12]`.
143. [ ] **[S]** _REPL_ — `/` search: `find <text>` greps saved transcripts in the inbox and prints matching note names. Keeps you in one tool.
144. [ ] **[S]** _REPL_ — `w` command: show what `watch` would capture for the current clipboard without saving (dry-run on the clipboard).
145. [ ] **[S]** _REPL_ — Add `d` (duplicate) behavior: when a link is a duplicate, print the existing note path and offer `o` to open it (today the path is printed but `o` opens the last *saved* note, not the duplicate).
146. [ ] **[S]** _REPL_ — Show a one-line preview after save: first 120 characters of the transcript and the word count, so you know the note has real content without opening Obsidian.
147. [ ] **[S]** _REPL_ — Add `x` to delete the last stub and re-queue its URL for a retry in one step (stubs block re-saving; today it's manual: delete the file, then paste again).
148. [ ] **[S]** _REPL_ — `l` shows only paths; include title, outcome and age (`2h ago`), and let `l 20` show more than 5.
149. [ ] **[S]** _REPL_ — Show elapsed time and a spinner while fetching (`fetching...` is static for up to `timeout x retries` seconds).
150. [ ] **[S]** _REPL_ — Warn when the clipboard (Enter on an empty line) contains no YouTube link, and show what it did contain (first 40 characters) so a mis-copy is obvious.
151. [ ] **[S]** _Reliability_ — If the info fetch succeeds but the caption URL 403s (signed URL expired), refetch info once and retry the track (IMPROVEMENTS #196, still open).
152. [ ] **[S]** _Reliability_ — `write_atomic` uses a single temp name and `os.replace`; if Obsidian Sync writes the same name between the `taken` snapshot and the replace, the other file is silently overwritten. Use `os.link`-free `open(dest, "x")` to claim the name atomically.
153. [ ] **[S]** _Reliability_ — `fcntl.flock` lock is per project folder, so two *different* projects/vaults serialize needlessly; negligible, but note a lock timeout (give up after 60 s) so a wedged run cannot block the hotkey forever.
154. [ ] **[S]** _Reliability_ — Handle `SIGINT` while holding the lock during the retry `sleep`; it already cancels, but add a test with `time.sleep` patched to raise.
155. [ ] **[S]** _Reliability_ — Verify the written file after `os.replace` (exists and size > 0) before claiming "saved"; a full or read-only sync overlay can accept the rename and drop the data.
156. [ ] **[S]** _Reliability_ — If `open_obsidian` fails to launch (no handler for `obsidian://`), say so once instead of silently doing nothing.
157. [ ] **[S]** _Reliability_ — Guard against a symlink loop in `rglob` (`find_existing`) with a visited set; a vault with a symlinked folder to a parent hangs the dedupe scan.
158. [ ] **[S]** _Reliability_ — `find_existing` reads 1 KB per note with `errors="replace"`; a 4 GB file mistakenly named `.md` is still just 1 KB, but a FIFO named `.md` would block forever. Check `is_file()`.
159. [ ] **[S]** _Reliability_ — Two machines sharing a vault via Obsidian Sync can both pass the duplicate check before sync delivers the other's note; the lock is local to one project folder. Detect Obsidian Sync/Syncthing conflict copies (`Title (conflicted copy).md`, `*.sync-conflict-*`) in `find_existing` and report them as duplicates.
160. [ ] **[S]** _Reliability_ — `write_atomic` renames a temp file from the inbox to the final name, but the temp file shares the inbox with synced notes; if the process is killed between write and rename, `.yt2obsidian.tmp` stays and a later run overwrites it silently. Include the PID in the temp name and clean up stale temp files older than a minute on start.
161. [ ] **[S]** _Reliability_ — `KeyboardInterrupt` during `write_atomic` leaves the lock held until the process exits (fine) but the retry queue is not updated for the URL being processed; on Ctrl-C mid-fetch the link is lost rather than queued. Queue the URL on cancel (the log row says `cancelled` but retry.txt never gets it).
162. [ ] **[S]** _Reliability_ — `urls_in` treats a paste of 500 links as a batch and processes all of them serially with retries; add a confirmation above a threshold (e.g. 25) with the estimated time, and a `--max` cap.
163. [ ] **[S]** _Reliability_ — `with_retries` sleeps `RETRY_DELAY * attempt` blindly; honor `Retry-After` from yt-dlp's HTTPError headers when present and abort the batch early on a 429 instead of retrying the same IP.
164. [ ] **[S]** _Reliability_ — A config problem is rediscovered on every paste in the REPL (`load_config` per line). Cache the parsed config by file mtime and print the error once with the line number until it changes.
165. [ ] **[S]** _Security_ — `run.log` keeps full URLs including `list=` and `si=` tracking params for invalid rows? Canonical for valid ones, raw for invalid; strip query strings from invalid rows too (`si=` identifies you).
166. [ ] **[S]** _Security_ — `.history` keeps the URLs you pasted in plaintext in the project folder (mode 600). Offer `history = false` and wipe on `clear history`.
167. [ ] **[S]** _Security_ — Never follow a symlinked inbox out of the vault: `inbox` pointing at a symlink to `/` passes `check_inbox` (it only checks the string). `resolve()` and verify it stays under the vault.
168. [ ] **[S]** _Tests_ — Add a golden-file test for `render`: store the expected note text for the Rick fixture and diff on change, so format changes are deliberate.
169. [ ] **[S]** _Tests_ — Fuzz `parse_url` with `hypothesis` (or a 200-case table): never raises anything but ValueError, output ID always matches `ID_RE`.
170. [ ] **[S]** _Tests_ — Fuzz `safe_name`: result never empty, never contains `/`, `\0`, `..` and is always <= `MAX_NAME` bytes (the existing test uses a few handpicked strings; bytes vs characters is the risk with CJK).
171. [ ] **[S]** _Tests_ — Measure coverage once (`coverage run`) and list uncovered lines in `repl()` and `settings_menu()`; those are the largest functions and are tested with mocked input.
172. [ ] **[S]** _Tests_ — Test `edit_config` through a symlinked config (the bug in this file).
173. [ ] **[S]** _Tests_ — Test `urls_in` with `youtube`-the-word, comma-joined links, and Markdown-wrapped links `[text](url)`.
174. [ ] **[S]** _Tests_ — Test the bracket-stripping rule with `arr[i]`, `[Music]`, `[ __ ]`, `[Speaker 1]`.
175. [ ] **[S]** _Tests_ — Test that a runtime failure inside `finish` (e.g. `notify` raising) cannot lose the saved note's log row.
176. [ ] **[S]** _Tests_ — Test `with_retries` timing: patch `time.sleep` and assert the delays are 2 s then 4 s.
177. [ ] **[S]** _Tests_ — Test two simultaneous processes (multiprocessing) produce one note and one duplicate result; the current lock test is single-process.
178. [ ] **[S]** _Tests_ — Contract test against the real yt-dlp info keys the code reads (`availability`, `live_status`, `age_limit`, `subtitles`, `automatic_captions`, `chapters`, `channel`, `uploader`, `duration`, `upload_date`); fail loudly if a yt-dlp upgrade renames one.
179. [ ] **[S]** _Tests_ — Make `--live` assert the Rick transcript starts with a known phrase and has more than N characters; today it only checks a note was written.
180. [ ] **[S]** _Transcript_ — Paragraph breaks are still not implemented (verified in code: only `>>` splits). json3 events carry `tStartMs`/`dDurationMs`; start a new paragraph on a gap over ~2 s or every ~600 characters at the next sentence end. See IMPROVEMENTS #135-138 for the PRD decision.
181. [ ] **[S]** _Transcript_ — Capitalize standalone `i` in auto captions ("i think i can") and the first letter after a paragraph break. Pure string work, no model.
182. [ ] **[S]** _Transcript_ — Decode `​`, `﻿` and soft hyphens before whitespace collapse; zero-width characters make Obsidian search miss words.
183. [ ] **[S]** _Transcript_ — Collapse repeated words created by the event join ("the the") only when the two occurrences straddle an event boundary, not inside one event ("had had").
184. [ ] **[S]** _Transcript_ — Mark where captions have gaps ("[unavailable]") when the track has empty-event stretches over 30 s, so a clipped auto track doesn't read as a complete transcript.
185. [ ] **[S]** _Transcript_ — Record `Captions: manual|auto` and the language code; the pick_track branch already knows which dict it came from (IMPROVEMENTS #146/#156).
186. [ ] **[S]** _Transcript_ — Join sentence fragments for manual tracks: manual captions are split in 2-line subtitle chunks, so "word-\nwrap" breaks leave odd spaces. Detect lines that end without punctuation and merge.
187. [ ] **[S]** _Transcript_ — Remove speaker-dash markers (`- ` at line starts) from manual dialogue tracks, or turn them into paragraph breaks like `>>`.
188. [ ] **[S]** _Transcript_ — Strip "Subtitles by the Amara.org community" style credit lines that some manual tracks append.
189. [ ] **[S]** _Transcript_ — Option to keep sound tags as italic `*[music]*` instead of dropping them, for talks where "[Applause]" matters. `keep_sound_tags` setting.
190. [ ] **[S]** _yt-dlp_ — Classify failures by yt-dlp exception attributes (`ExtractorError.expected`, `video_id`, `exc_info`) instead of substring-matching English messages (`THROTTLE`, `stub_reason`); YouTube text changes more often than exception types do.
191. [ ] **[S]** _yt-dlp_ — Warn when the installed yt-dlp is older than ~30 days (`yt_dlp.version.RELEASE_GIT_HEAD`/`__version__` date) at REPL start with "press u to update"; most failures are staleness and the banner already prints the version.
192. [ ] **[S]** _yt-dlp_ — Set `extractor_args={"youtube": {"player_client": ["web", "tv"]}}` order explicitly and expose `player_client` as a setting; YouTube's client mix changes which captions endpoint requires a PO token.
193. [ ] **[S]** _yt-dlp_ — Pass `cachedir` into the project folder (`.cache/`) and gitignore it, so the nsig/player cache survives venv rebuilds and a hotkey run doesn't depend on the user's home cache permissions.
194. [ ] **[S]** _yt-dlp_ — `fetch()` uses the full `extract_info` pipeline; try `process=False` plus a direct call to the player response for captions only, falling back to the full path. Measure time and failure rate with the live canary before adopting.
195. [ ] **[S]** _yt-dlp_ — Let users add yt-dlp options in `config.toml` under `[ytdlp]` (proxy, cookiefile, sleep_interval, source_address) rather than editing the module; validate against an allowlist so config can't inject arbitrary options.
196. [ ] **[M]** _CLI_ — `yt --restub`: re-fetch stub notes and replace those that now have captions (IMPROVEMENTS #214 left this undecided; auto captions often appear hours after upload).
197. [ ] **[M]** _Features_ — Browser bookmarklet / extension button: send the current tab URL to a local `yt2obsidian://save?url=...` handler, no clipboard needed.
198. [ ] **[M]** _Features_ — `yt --watch`: run `wl-paste --watch` and auto-save every copied YouTube link (opt-in, with a toast). [PRD: no background service]
199. [ ] **[M]** _Features_ — Playlist support as an explicit command: `yt --playlist URL` expands to video URLs and runs them through `batch` with the delay and a confirmation of the count. [PRD: single videos only]
200. [ ] **[M]** _Features_ — Channel "latest N" import: `yt --channel @name --last 5`. [PRD]
201. [ ] **[M]** _Features_ — Whisper fallback for videos without captions (`faster-whisper` on the audio), off by default. [PRD: no model use; this is speech-to-text but still a model]
202. [ ] **[M]** _Note format_ — Template file. Let `template.md` in the project folder control the note layout with `{title} {url} {channel} {date} {duration} {saved} {text}` placeholders; the built-in layout stays the default. [PRD §7.4]
203. [ ] **[M]** _Obsidian_ — Detect whether Obsidian Sync/Syncthing is mid-sync (`.sync-conflict` siblings) and avoid writing a name that collides with a conflict copy.
204. [ ] **[M]** _Packaging_ — Add `pyproject.toml` with a `yt2obsidian` console script and `pipx install .` instructions; removes the `.venv/bin/python` shell wrapper and the Arch-Python-upgrade breakage (pipx rebuilds with `reinstall-all`).
205. [ ] **[M]** _Perf_ — Fetch several URLs concurrently with a small pool (2-3 workers) once the batch delay exists. Serial is ~3.5 s each (run.log) so 10 links is ~35 s.
206. [ ] **[M]** _Security_ — Cookie support behind an explicit setting (`cookies_from_browser = "firefox"`), off by default, never logged. Gets age-restricted/members videos and rides out bot checks. [PRD says restricted = stub]
207. [ ] **[M]** _Transcript_ — Support `vtt` and `srv3` as fallbacks when json3 is missing; `pick_track` currently returns None and writes a "no captions" stub for a video that has captions in another format.

## Low value / nice to have

208. [ ] **[XS]** _Cleanup_ — `HISTORY`, `LOG`, `RETRY`, `LOCK` constants and `.history` file names are scattered; move to a `STATE` dict so the XDG migration is one change.
209. [ ] **[XS]** _Cleanup_ — `USAGE` and the README repeat the flags; generate the README usage block from `USAGE` in a test so they can't drift.
210. [ ] **[XS]** _Cleanup_ — `SETTINGS` menu labels and `config.example.toml` comments say the same thing twice; generate the example file from `SETTINGS` (one source of truth).
211. [ ] **[XS]** _Cleanup_ — `ANSI` color table has `blue` only for the duplicate outcome; drop unused entries or use them for the banner consistently.
212. [ ] **[XS]** _Cleanup_ — The `ponytail:` comments in the module document shortcuts but there is no ledger; run the `ponytail-debt` harvest once and paste the output into `docs/DEBT.md`.
213. [ ] **[XS]** _Code health_ — `Quiet` can be three lines shorter: `class Quiet: debug = info = warning = error = lambda self, m: None`.
214. [ ] **[XS]** _Code health_ — `ANSI` map and `paint` could drop `bold`/`dim` if unused (both used; keep). Delete the unused `OUTCOME_COLOR["invalid"]` duplicate of `failed` by aliasing.
215. [ ] **[XS]** _Code health_ — `USAGE` and `HELP` strings duplicate command names with the dispatch in `repl()`; a single table of `(name, help, handler)` would remove the drift risk.
216. [ ] **[XS]** _Code health_ — `SUMMARY` and `OUTCOME_COLOR` and `LOG_AS` are three parallel dicts keyed by outcome; one `OUTCOMES` table would hold color, log name and summary order.
217. [ ] **[XS]** _Code health_ — `recent_saves` re-reads and re-splits the whole run.log on every `l`; fine now, but tail the last 200 lines instead of the whole file.
218. [ ] **[XS]** _Code health_ — `clean()` is defined at module level and again inside `safe_name`; rename the inner one `fold`.
219. [ ] **[XS]** _Code health_ — `rel()` swallows `ValueError` to return the absolute path; use `Path.is_relative_to` for clarity.
220. [ ] **[XS]** _Code health_ — The `ponytail:` comment on `write_atomic` claims one temp name is safe; add a comment where the lock is taken pointing back to it, so removing the lock later is not safe by accident.
221. [ ] **[XS]** _Code health_ — `update_ytdlp` calls `pip` with the running interpreter; `uv pip` environments have no `pip` module. Detect and print "run `uv pip install -U yt-dlp`".
222. [ ] **[XS]** _Code health_ — Constants `RETRY_DELAY = 2` is untested magic; derive it from `timeout` or put it in `SETTINGS`.
223. [ ] **[XS]** _Code health_ — `toast()` has a `repl=False` positional that is unused in two call sites; keyword-only.
224. [ ] **[XS]** _Code health_ — `Result` uses `defaults=(None, None)` for `path/title` only; `outcome == "cancelled"` returns `Result(1, "cancelled")`. Make `cancelled` a first-class entry in `OUTCOME_COLOR`.
225. [ ] **[XS]** _Code health_ — Replace `re.sub(r"^\w+", lambda ...)` in `finish` with a split on the first colon; the regex colors the first word even for messages without a status word.
226. [ ] **[XS]** _Code health_ — `ID_RE` and `HOSTS` are constants near the top, `NOT_VIDEO` is another; group URL constants in one block.
227. [ ] **[XS]** _Code health_ — `KEEP` allowlist includes `$%~=@+!`; none of those matter for Obsidian, but `%` and `#`-like characters can break `obsidian://` links. Audit each character you keep.
228. [ ] **[XS]** _Docs_ — IMPROVEMENTS.md status banners say "done (28 of 30)" but only list the exceptions in prose; add a plain "open items" table at the top.
229. [ ] **[XS]** _Docs_ — Add the date and commit for each "Status" banner so stale ones are obvious.
230. [ ] **[S]** _Config_ — `config.toml` comments are preserved on edit; add a test with trailing comments after a quoted value containing `#`.
231. [ ] **[S]** _Config_ — Provide `yt --init` to write a starter `config.toml` after asking for vault and inbox (IMPROVEMENTS #229).
232. [ ] **[S]** _Config_ — Support multiple named profiles (`[work]`, `[personal]`) with `--profile`.
233. [ ] **[S]** _Config_ — Validate that `vault` is not a parent of the project folder or the home directory root.
234. [ ] **[S]** _Config_ — Check at load time that `inbox` is writable and warn once (not on every paste).
235. [ ] **[S]** _Docs_ — Add a short FAQ: why ASCII filenames, why stubs block re-saves, why Shorts are skipped.
236. [ ] **[S]** _Docs_ — Add screenshots or an asciinema of the prompt and a note in Obsidian.
237. [ ] **[S]** _Docs_ — List the exact fixtures (`rick_info.json`, `rick_track.json`) and how to refresh them from a live run.
238. [ ] **[S]** _Docs_ — State the licensing for yt-dlp use and the YouTube terms in one sentence for anyone you share it with.
239. [ ] **[S]** _Docs_ — Add Hyprland bind variants (with and without a terminal: `exec, kitty --class yt -e yt` for the prompt).
240. [ ] **[S]** _Docs_ — Add a `man`-style `--help` that includes the settings list and exit codes in one screen.
241. [ ] **[S]** _Feature_ — Obsidian community plugin counterpart: a tiny plugin command "Save transcript from clipboard" that shells out to this tool, so Obsidian users on any platform can trigger it from the command palette.
242. [ ] **[S]** _Feature_ — Optional `Related` section listing other saved notes from the same channel (wikilinks) generated at save time from filenames and `Channel:` lines; no AI, just a directory scan.
243. [ ] **[S]** _Feature_ — Export a reading view: a sibling `.html` or `.epub` of a transcript for e-readers, generated with the standard library only.
244. [ ] **[S]** _Feature_ — Text-to-speech companion: `yt --read NOTE` pipes the transcript to `espeak-ng`/`say`; handy for videos you want to listen to as text.
245. [ ] **[S]** _Feature_ — Daily digest: `yt --digest` writes a note listing everything saved today with links, for the daily review workflow.
246. [ ] **[S]** _Feature_ — Watch-later import: parse a Google Takeout `watch-later.csv` or a pasted text file of links and save them in batches with throttling and resume (`retry.txt` already gives resume).
247. [ ] **[S]** _Feature_ — Subscribe-by-RSS: read a channel's public RSS feed (`youtube.com/feeds/videos.xml?channel_id=`) and offer "save the latest N" interactively; no API key needed and no scraping of channel pages. [PRD]
248. [ ] **[S]** _Filename_ — `MAX_NAME` is computed in bytes minus 8 but `[:MAX_NAME]` slices characters; a CJK title that survives the allowlist (none do now) would exceed 255 bytes. Test with the allowlist widened.
249. [ ] **[S]** _Filename_ — Avoid Windows-reserved base names (`CON`, `NUL`, `COM1`) if a Windows device ever opens the vault via Obsidian Sync. `safe_name("CON")` returns `CON` (run today).
250. [ ] **[S]** _Filename_ — Case-insensitive duplicate-name handling uses `.lower()`, which differs from Unicode case-folding on exotic names; use `casefold()`.
251. [ ] **[S]** _Filename_ — Add a numeric suffix style that Obsidian shows nicely (`Title 2` vs `Title (2)`); the parenthesis form is fine, but the second link in Obsidian becomes `[[Title (2)]]`, which needs quoting in some plugins.
252. [ ] **[S]** _Filename_ — Strip a trailing ` - YouTube` and common channel-suffix patterns ("| Official Video") optionally via a regex list in config.
253. [ ] **[S]** _Filename_ — Date-prefix filenames (`2024-01-31 Title`) behind `filename_date = true` for sorted file lists (IMPROVEMENTS #172).
254. [ ] **[S]** _Filename_ — Allow a custom `filename = "{channel} - {title}"` template.
255. [ ] **[S]** _Input_ — Accept `music.youtube.com/watch?v=...&si=` and `youtube.com/live/ID` (supported) plus `youtube.com/attribution_link?u=%2Fwatch%3Fv%3D...` which share sheets generate.
256. [ ] **[S]** _Input_ — Accept `https://www.google.com/url?q=<youtube url>` redirect wrappers pasted from search results and email.
257. [ ] **[S]** _Input_ — Accept a bare 11-character ID after confirming it with a `[y/N]` (IMPROVEMENTS #189 left it open).
258. [ ] **[S]** _Input_ — Accept `yt:ID` shorthand for REPL speed.
259. [ ] **[S]** _Input_ — Accept Markdown links `[title](url)` as pasted from Obsidian: today the `(` stripped by `parse_url` works only if the whole token is wrapped.
260. [ ] **[S]** _Input_ — Strip `&list=` from a `watch?v=ID&list=PL...` paste only after telling the user a playlist was ignored.
261. [ ] **[S]** _Input_ — Detect `youtube.com/shorts/ID` and offer to save it as a normal watch URL (Shorts are skipped by PRD; add `shorts = "skip|save"` if the rule changes).
262. [ ] **[S]** _Input_ — Support `/embed/ID?start=30` start offsets as in the timestamp item.
263. [ ] **[S]** _Input_ — Return the original pasted line in the log's detail on `skipped`, not just the ID.
264. [ ] **[S]** _Note format_ — Heading line `# Title` before the link line so Obsidian's outline pane shows the title.
265. [ ] **[S]** _Note format_ — Add `aliases:` frontmatter with the original (unfolded, Unicode) title when the filename had to be ASCII-folded. Solves the "title looks wrong" complaint without changing filenames.
266. [ ] **[S]** _Note format_ — Add a thumbnail embed `![](thumbnail-url)` behind a setting. [PRD: thumbnails out of scope]
267. [ ] **[S]** _Note format_ — Add `Language:` and `Captions:` lines to the metadata block.
268. [ ] **[S]** _Note format_ — Store `Video ID:` as its own line so dedupe can match on it and not on the URL.
269. [ ] **[S]** _Note format_ — `Saved:` uses local date only; add the time for sorting multiple saves in a day.
270. [ ] **[S]** _Note format_ — Escape `#` at the start of transcript paragraphs (Obsidian would render `# foo` as a heading).
271. [ ] **[S]** _Note format_ — Escape `---` lines inside the transcript so they are not read as a frontmatter or horizontal rule.
272. [ ] **[S]** _Note format_ — Wrap very long transcripts in a collapsible callout? No; makes search worse.
273. [ ] **[S]** _Packaging_ — Add `.editorconfig` and a `Makefile` with `test`, `live`, `lint` targets.
274. [ ] **[S]** _Packaging_ — Add a GitHub Actions workflow that runs the offline tests on push (3.11-3.14) and a weekly `--live` canary that opens an issue on failure.
275. [ ] **[S]** _Packaging_ — Dependabot/renovate for the yt-dlp floor, since it is the one dependency that rots.
276. [ ] **[S]** _Packaging_ — Tag releases (`v1.0.0`) and ship the changelog; IMPROVEMENTS #290 suggested a tag, none exists.
277. [ ] **[S]** _Packaging_ — Choose a license (MIT) if sharing; none today.
278. [ ] **[S]** _Packaging_ — Provide an AUR-style PKGBUILD or Nix flake only if others will install it.
279. [ ] **[S]** _Perf_ — `find_existing` rescans the inbox for every URL. Measured today: 3,000 notes of 5 KB take 0.08 s, so this only matters past ~50,000 notes; if the vault ever gets there, build the `{video_id: path}` index once per batch.
280. [ ] **[S]** _REPL_ — Show a spinner (`fetching |/-\`) during network waits; `fetching...` is static for up to 45 s.
281. [ ] **[S]** _REPL_ — Color the prompt (`>`) per last outcome (green/red) for at-a-glance state.
282. [ ] **[S]** _REPL_ — `clear` command to clear the screen and `history` to show the last 20 pasted URLs.
283. [ ] **[S]** _REPL_ — `version` and `where` commands: print yt-dlp version and the paths of config, log, queue.
284. [ ] **[S]** _REPL_ — Warn when the clipboard Enter-paste contains more than 20 links before starting.
285. [ ] **[S]** _REPL_ — Ctrl-C during a batch cancels the current URL but continues? Current behavior stops and queues the rest; add a confirmation on the second Ctrl-C.
286. [ ] **[S]** _REPL_ — Allow `s` subcommands: `s notify never` to change a setting without the menu.
287. [ ] **[S]** _REPL_ — Remember the last-used settings choice ordering (cursor position) when the menu redraws.
288. [ ] **[S]** _REPL_ — Echo the exact queue file path when URLs are queued.
289. [ ] **[S]** _Transcript_ — Option to output the transcript as a bullet list per sentence for easier clipping.
290. [ ] **[S]** _Transcript_ — Option `no_breaks` for a single-line transcript for people pasting into LLMs.
291. [ ] **[S]** _Transcript_ — Word count and estimated read time in the metadata block (`Words: 2,089 (~9 min read)`).
292. [ ] **[S]** _Transcript_ — Mark long silent intervals as a paragraph break even when the next caption starts with a lowercase letter.
293. [ ] **[S]** _Transcript_ — Normalize curly quotes in the transcript to straight quotes (or the reverse) for consistent search.
294. [ ] **[S]** _Transcript_ — Replace `&nbsp;`-like non-breaking spaces (`\xa0`) before collapse; verify they are already caught by `\s` (they are) and add a test so it stays true.
295. [ ] **[S]** _Transcript_ — Drop filler "um", "uh" tokens in auto captions behind a `clean_fillers` setting.
296. [ ] **[S]** _Transcript_ — Keep a copy of the raw json3 next to the note (hidden `.raw/ID.json3`) so transcripts can be re-rendered when the format improves, without refetching.
297. [ ] **[S]** _Transcript_ — Handle `en-US` and `en-GB` tracks both present by preferring the video's `info["language"]` region.
298. [ ] **[S]** _Transcript_ — If both a manual and auto English track exist, optionally merge: use manual text but keep auto timing for paragraph breaks.
299. [ ] **[M]** _Features_ — Local web UI (`yt --serve`) with a paste box and recent-saves list for use from a phone on the LAN. [PRD: mobile trigger out of scope]
300. [ ] **[M]** _Features_ — iOS/Android Share-sheet shortcut that posts the URL to a tiny local endpoint behind Tailscale. [PRD]
301. [ ] **[M]** _Features_ — Tag notes automatically from the channel's name via a mapping file (`channels.toml`: channel to folder/tags).
302. [ ] **[M]** _Features_ — Per-channel subfolder routing (`Transcripts/<Channel>/`) with a setting; dedupe already searches subfolders.
303. [ ] **[M]** _Features_ — Index note (`Transcripts/_index.md`) regenerated on each save listing all notes by date and channel. [PRD: index page out of scope]
304. [ ] **[M]** _Features_ — Export formats: also write `.srt` or `.txt` next to the note on request (`--also srt`).
305. [ ] **[M]** _Features_ — Highlights: a `yt mark` command that appends the current clipboard text as a quote to the last note.
306. [ ] **[M]** _Features_ — Detect and merge translated duplicate videos (same title, other language) into one note's links.
307. [ ] **[M]** _Features_ — Summarize via a local model and store in a separate file. [PRD: no model use]
308. [ ] **[M]** _Features_ — OPML/RSS channel subscriptions pulling new videos into a "to review" queue instead of straight into the vault.
309. [ ] **[M]** _Features_ — Integrate with `yt-dlp --download-archive` style ID list so IDs processed elsewhere are treated as seen.
310. [ ] **[L]** _Features_ — A TUI (Textual) for browsing the log, retrying failures and viewing stubs.
311. [ ] **[L]** _Features_ — Rewrite as a small library plus CLI so other scripts (Obsidian plugin, Raycast-style launcher) can call `save(url)`.
