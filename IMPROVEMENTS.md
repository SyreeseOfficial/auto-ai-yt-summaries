# Improvements

Fresh audit of `yt2obsidian.py` (331 lines) after the move to a CLI tool: `./yt` starts an interactive prompt (`-i`) with a settings menu (`open_obsidian` and `notify` toggles); the one-shot clipboard/argument mode and Hyprland bind still work. Line refs are `yt2obsidian.py` at commit 7eb4890 unless noted.

The earlier 300-item list is gone. Kept where it still applies (reworded and renumbered), dropped where it no longer made sense (the "never run for real" item, all "checked, no action" notes, and hotkey-only UX that the REPL replaced), and new items added for the REPL, the settings menu, and the new `yt` script. Nothing from the old list has been implemented yet.

Tags: **[V]** = observed by running it (today, or in the earlier audit; items I re-ran today say so). **[S]** = small (<10 min). **[M]** = medium (10-60 min). **[L]** = large. **[PRD]** = contradicts or changes a PRD decision, so you must say yes first. Untagged by [V] = read from the code, not run.

Leaning rule: if an item deletes code, it comes before an item that adds code.

Re-run today: the REPL ends on an unexpected error (`KeyError`) and on Ctrl-C mid-fetch; `ID_RE` accepts `ééééééééééé`; `safe_name("Café – Don’t Stop")` returns `Caf Dont Stop`; all existing tests pass.

## Do these first (top 8)

1. Catch unexpected errors and Ctrl-C in the REPL. One bad paste ends your session today. (#1)
2. Treat YouTube's "rate-limited" message as a throttle. (#12)
3. Stop writing junk stubs for deleted or mistyped IDs. (#28)
4. Fold accents before the ASCII strip. `Café – Don’t Stop` becomes `Caf Dont Stop`. (#164)
5. Stop logging typos from the prompt to `run.log`. (#31)
6. Document `./yt` and the settings menu. The README does not mention either. (#273)
7. Reject absolute or `..` inbox values. They save outside the vault and then crash the open. (#226)
8. Strip `♪` and `[...]` tags, then add paragraph breaks. (#136)

---

## A. Bugs and crash paths

**Status: done (28 of 30), 2026-10-20.** Not done: #16 (needs a PRD decision) and #18 (overlaps #213: decide whether deleting a note allows re-saving). #3 is covered by a catch-all inside `main`, so the `process()` split stays in section B (#49).

1. **[V][S]** **REPL dies on any unexpected error.** `repl()` calls `main()` bare (:327), so a `KeyError`, `OSError` (disk full), or bad JSON prints a traceback and ends the session. Wrap the call, print the error, log `failed`, return to the prompt. Reproduced by making `fetch` raise `KeyError`.
2. **[V][S]** **Ctrl-C during a fetch kills the REPL.** Only `input()` is guarded (:318-321). Catch `KeyboardInterrupt` around the `main` call, print `cancelled`, stay at the prompt. Reproduced.
3. **[S]** **One-shot runs have no catch-all either.** Put the same wrapper in the shared `process(url)` function (see E) so a hotkey run always ends in a log line and a toast.
4. **[V][S]** **Bad caption body crashes.** `json.load` in `fetch_track` (:140) raises `JSONDecodeError` on an HTML error page, and `with_retries` lets it through. Catch `ValueError` and fall to a stub or a failure.
5. **[S]** **Missing `config.toml`** gives a raw `FileNotFoundError` (:44). In the REPL it appears on the first paste, after the banner. Check at startup and print "copy config.example.toml to config.toml".
6. **[S]** **Missing `vault` or `inbox` key** gives a bare `KeyError` (:46, :265). Check both in `load_config`.
7. **[S]** **Hand-edited bad TOML kills the REPL.** `load_config` runs on every paste (:264) and on every settings redraw (:62). Catch `TOMLDecodeError`, print the line number, keep going.
8. **[S]** **A typo in `vault` silently creates a fake vault.** `write_atomic` uses `mkdir(parents=True)` (:220). Require `cfg["vault"].is_dir()`; allow `mkdir` only for the inbox itself.
9. **[S]** **`wl-paste` not installed** raises `FileNotFoundError` (:82), which `main` does not catch (:282 catches `ValueError` and `SubprocessError`). Add `OSError`. One-shot path only.
10. **[V][S]** **`ID_RE` uses `\w`** (:27), which matches Unicode letters. `https://youtu.be/ééééééééééé` parses as a valid ID (re-run today). Use `[A-Za-z0-9_-]{11}`.
11. **[S]** **Name-clash cap is inconsistent.** The loop runs to 999 (:226) but `MAX_NAME` reserves only `" (99)"` (:31). `" (999)"` can push past 255 bytes. Make the loop `range(1, 100)`.
12. **[V][S]** **Rate-limit message not matched.** yt-dlp says "This content isn't available, try again later ... rate-limited by YouTube for up to an hour" (`_video.py:4069`). `fetch` only matches `HTTP Error 429` and `not a bot` (:116). Result: a stub with a misleading reason and no retry entry. Add `rate-limited` and `try again later`.
13. **[S]** **HTTP 403/404 on the caption URL** is an `HTTPError` (an `OSError`), so `with_retries` retries it and then calls it "Throttled" (:128-133). Retry only timeouts, `URLError`, and 5xx; fail fast on other 4xx.
14. **[S]** **Log lines can break.** `log_run` writes raw strings (:253). yt-dlp errors are multi-line and can contain tabs. Collapse whitespace before writing.
15. **[S]** **Stubs are permanent.** A stub for a live or upcoming video blocks the real save later, and the REPL just says `Already saved: <path>` with no hint it is a stub. Say "stub, delete it to retry" (or replace it, which needs a [PRD] OK).
16. **[M][PRD]** **Unknown errors become permanent stubs.** A non-throttle `DownloadError` writes `transcript fetch failed: ...` (:183) and dedupe then blocks any retry. Safer: stub only for known reasons; queue the rest in `retry.txt`.
17. **[S]** **Dedupe reads only line 1** (:212). Add frontmatter or a heading to the note and the match fails, so a duplicate is saved. Search the first ~1 KB.
18. **[M]** **Moved notes get re-saved.** `find_existing` only globs the top of the inbox (:210). Move a note to another folder and the same video is saved again. Cheap fix: also treat `saved` lines in `run.log` as seen.
19. **[S]** **Retry sleeps are silent** (:134). A flaky run blocks the prompt for up to 6 s with no output. Print `retrying (2/3)...` per attempt.
20. **[S]** **`open_obsidian` `Popen` is unguarded** (:248). A missing `xdg-open` raises after the note is saved and logged, and in the REPL that now ends the session. Wrap it like `notify`.
21. **[S]** **`log_run` / `queue_retry` can raise** (disk full) and mask the real outcome. Wrap in `try/except OSError`.
22. **[S]** **Titles with `*` or `_` render as bold or italic** in the link text (:202). Escape them. Low priority.
23. **[S]** **`-i` plus an argument** (`yt2obsidian.py -i <url>`) falls to `main`, which reads `-i` as the URL. Only the exact `["-i"]` starts the REPL (:331).
24. **[S]** **`-h` / `--help` are treated as URLs** and logged as failures (`not a YouTube URL: '--help'`). Print a 5-line usage instead.
25. **[S]** **Non-boolean toggle values** (`notify = "false"` as a string) are truthy, so the toggle reads as on. Validate types in `load_config`.
26. **[S]** **`pick_track` assumes every format has `url`** (:155). Use `f.get("url", "")`.
27. **[V][S]** **Stub text is lowercased.** Output was `transcript fetch failed: this video is unavailable`. `stub_reason` lowercases the whole message for matching (:175) and reuses it for display (:183). Keep a separate lowercase copy for matching.
28. **[V][S]** **Deleted or mistyped ID writes a junk note.** `video-aaaaaaaaaaa.md` with `Title: aaaaaaaaaaa`, `Channel: unknown`, `Date: unknown`. "This video is unavailable" is not in the PRD stub list. Treat it as a failure: log, print, write no note.
29. **[V][S]** **yt-dlp prints its own `ERROR: ...` to stderr** on top of your message (seen on the deleted-video run and 3 times on a dead network). Pass a `logger` with no-op methods so only your line prints.
30. **[S]** **`notify-send` can stall up to 5 s** (`timeout=5`, :240) after a save or failure. In the REPL that is a visible freeze before the next prompt. Fire and forget with `Popen`, or skip it when a terminal is attached.

## B. Interactive mode (`./yt`)

**Status: done (36 of 39), 2026-10-20.** Not done: #47 (color), #59 (don't open stubs), #67 (count in the prompt), all taste. Added after your OK: #43 (several links per paste, one per line or space-separated), #44 (a throttle stops the batch and queues the untried links), #54 (`u` runs `pip install -U yt-dlp`; manual, not automatic), #60 (a bare `yt2obsidian.py` in a terminal opens the prompt; with no terminal, i.e. the hotkey, it still reads the clipboard), #65 (`undo` deletes the note saved last this session, after a y/N prompt). #41 shows the note path from `run.log`, not the real title (log rows do not hold titles yet, see #233). #42 is the `r` command; the `--retry` flag (#92) is still open. #51 vs #68: Enter on an empty line reads the clipboard, comment lines (`# ...`) are ignored. #55 hint now says to press `u`. #62 is in the README.

31. **[S]** **Don't log typos.** `run.log` already holds `garbage` and a pasted shell command as `failed` rows. In the REPL, print parse failures and skip `log_run`.
32. **[S]** **No toasts while a terminal is attached.** Failures call `notify` (:276) while you are looking at the prompt. Toast only when `sys.stdin` is not a tty (hotkey runs).
33. **[S]** **Print `fetching...` before the network call.** A first run takes 1-2 s with no output.
34. **[S]** **Show elapsed time** on the result line: `Saved (1.4s): ...`. PRD's success metric is "a few seconds"; nothing measures it.
35. **[S]** **Print the title on success**, not only the path. The filename has accents and non-ASCII stripped, so it can look wrong. Strip control characters before printing.
36. **[S]** **Show vault and inbox in the banner** so you know where notes will land.
37. **[S]** **Add `?` / `h` / `help`.** Today `help` is treated as a URL and fails. List `s`, `q`, and any commands you add.
38. **[S]** **`import readline`** so up-arrow history and line editing work in `input()`. One line; check it on your terminal.
39. **[S]** **Persist history** across sessions with `readline.write_history_file`. Store it next to the script and gitignore it. See Security: URL lines only.
40. **[S]** **`o` command: open the last saved note in Obsidian.** Your config has `open_obsidian = false`, so a manual open is the only way. Needs `main` to return the path (see below).
41. **[S]** **`l` command: list the last 5 notes** saved (from `run.log`) with title and path.
42. **[M]** **`r` command: retry `retry.txt`.** Today the file is write-only. Pairs with `--retry` in the one-shot section.
43. **[M][PRD]** **Accept several URLs on one line or one paste** (split on whitespace) and process each. PRD says one URL per run, but the REPL makes batch natural. Pasting a list of links already works line by line; this only covers one-line pastes.
44. **[S]** **Stop a batch at the first throttle** and queue the remaining URLs in `retry.txt`. Needed if multi-URL lands.
45. **[S]** **Session summary on quit:** `3 saved, 1 stub, 1 duplicate, 1 failed`. Counts come from the results `main` returns.
46. **[S]** **Use consistent result prefixes.** Today: `Saved:`, `Already saved:`, `Skipped:`, `Error:`, `Stopped:`. Pick one scheme (`saved`, `duplicate`, `skipped`, `failed`, `stopped`) so the output scans.
47. **[S]** **Color the status word** (green saved, red failed) and respect `NO_COLOR`. Low priority.
48. **[M]** **Return a result from `main`** (outcome, path, title) instead of only an exit code. `open_cmd`, the summary, and `list_cmd` all need it.
49. **[S]** **Replace the `main(["", line])` hack** (:327) with a `process(url, cfg)` function. `main` then only resolves argv or the clipboard, then calls it.
50. **[S]** **Duplicate: offer the existing note.** Print the path (already done) and let `o` open it. Optionally open it when `open_obsidian` is on.
51. **[S]** **Empty Enter reads the clipboard.** `get_url` already does it for one-shot runs; reuse it so the REPL can paste for you.
52. **[S]** **Shorter "not a URL" error:** echo at most 60 characters of the paste and add `(? for help)`. A pasted paragraph currently fills the screen and the log.
53. **[S]** **Show the yt-dlp version in the banner** (`yt_dlp.version.__version__`). Most breakage is a stale yt-dlp, and this makes it visible.
54. **[S][PRD]** **`u` command: run `pip install -U yt-dlp`** on request. PRD forbids auto-update; an explicit manual command is not auto.
55. **[S]** **Hint on extractor breaks.** When the error says `Unable to extract` or `nsig`, add "try: u (update yt-dlp)".
56. **[V][S]** **Short message when the network is down.** Today the raw yt-dlp text (200+ chars, `ERROR: [youtube] id: Unable to download API page: [Errno 111] ...`) is printed. Print "Network down, queued for retry" and keep the detail in `run.log`.
57. **[S]** **Cap any error text printed to ~200 characters;** the full text stays in `run.log`.
58. **[S]** **Print the path relative to the vault** (`Transcripts/Title.md`). Shorter and still unambiguous.
59. **[S]** **Don't open stubs in Obsidian.** A stub has nothing to read. Taste; could be a toggle (see Settings).
60. **[S][PRD]** **Start the REPL by default when stdin is a tty** and keep clipboard mode for non-tty (hotkey). Then `./yt` needs no `-i`. Changes today's behavior of running with no args in a terminal.
61. **[S]** **Make `./yt` pass arguments through:** `./yt <url>` for one shot, `./yt` for the REPL. Today `yt` hardcodes `-i` (see `yt`).
62. **[S]** **Put `yt` on your PATH:** `ln -s "$PWD/yt" ~/.local/bin/yt`. The script already resolves symlinks with `readlink -f`. Add the line to the README.
63. **[S]** **On quit, mention waiting retries:** `2 URLs waiting in retry.txt (r to retry)`.
64. **[S]** **After a throttle, say what to do:** YouTube's message says up to an hour. Print "wait, then press r".
65. **[S][PRD]** **`undo` command:** delete the note saved last in this session. Fixes a mis-paste. PRD says never overwrite; deleting your own just-written note is a different thing, but it is your call.
66. **[S]** **Mark stubs visibly in output** (`stub:`) so a no-transcript save does not look like a success at a glance.
67. **[S]** **Show the count in the prompt** (`[3]> `) so a long session shows progress. Taste.
68. **[S]** **Whitespace-only and comment lines** (`# note`) should be ignored without a log row. Check they are.
69. **[S]** **Exit cleanly on SIGTERM / SIGHUP** (terminal closed mid-run): a half-written temp file should not stay behind. `write_atomic` has `finally`, but a signal skips it.

## C. Settings menu

**Status: done (17 of 22), 2026-10-20.** Done: #70-75, #76 (`inbox` is editable), #77 (`timeout` and `retries` are editable and validated, so #230 no longer applies), #78, #79, #80 (`notify` is `auto` / `always` / `never`; old `true` / `false` still read as auto / never), #86, #87, #88, #89, #90, #91. Tests #245-247 are in `test_settings`, `test_toast_modes`, and `test_settings_apply_to_next_paste`. Not done: #81-85 (toggles for features that do not exist yet, or that need a PRD decision). `d` resets the settings that have defaults and keeps `inbox`; it rewrites lines already in the file and does not add new ones. Also validated in `load_config`: `timeout` and `retries` must be whole numbers, 1 or more (covers #221 and #132's `retries = 0` case).

70. **[S]** **`set_toggle` writes the config non-atomically** (:56). A crash mid-write truncates `config.toml` and loses your vault path. Write a temp file, then `os.replace`.
71. **[S]** **`set_toggle` reads and writes without `encoding`** (:54, :56). Use `encoding="utf-8"`.
72. **[S]** **Invalid input is silently ignored** (:74). `x` or `9` just redraws the menu. Print "pick 1-2".
73. **[S]** **Accept `q` / `b` to leave the menu** as well as Enter, to match the main prompt.
74. **[S]** **Confirm each change:** `Notifications: off`. The redraw shows it, but a one-line echo is clearer.
75. **[S]** **Show the config file path and the current vault/inbox** at the top of the menu, read-only.
76. **[M]** **Make `inbox` editable in the menu** (text value) so you can switch folders without editing TOML. Needs value typing in `TOGGLES`.
77. **[M]** **Make `timeout` and `retries` editable** with validation, or delete them from config (see Config). Pick one.
78. **[S]** **`d` = reset to defaults:** remove the toggle lines from `config.toml`.
79. **[S]** **`--settings` flag** to open the menu without starting the REPL.
80. **[M]** **Turn `notify` into `auto` / `always` / `never`.** `auto` = toast only when no terminal (see Interactive). The menu cycles the three values.
81. **[S]** **Toggle: write stub notes** (on) or just report the failure (off). PRD says stubs, so default on.
82. **[S]** **Toggle: open stubs in Obsidian** (default on to match today).
83. **[S]** **Toggle: paragraph breaks** (default on) once they land, so you can compare against the raw one-line version.
84. **[S]** **Toggle: extra metadata lines** (`Captions:`, `Duration:`) if you adopt them [PRD].
85. **[S]** **Toggle: color output** if you add color.
86. **[S]** **Settings take effect on the next paste** (config reloads per run, :264). Add a test that proves it, since it is easy to break by caching `cfg`.
87. **[S]** **`settings_menu` can raise** if `load_config` fails inside the loop (:62). Catch it, print the error, and return to the prompt.
88. **[S]** **List the toggles in `config.example.toml`** with comments. Today a fresh clone does not show they exist.
89. **[S]** **Show a legend:** `[x]` on, `[ ]` off, so the checkbox style needs no guessing.
90. **[S]** **Document `s` in the README.** It is only mentioned in the banner.
91. **[S]** **Unknown config keys** (typo `notfy = false`) are ignored silently. Warn on keys not in the schema.

## D. One-shot and hotkey path

**Status: done (13 of 14), 2026-10-20.** Not done: #103 and #104 (need a real test from the Hyprland bind; if `node`/`deno` is missing there, set `js_runtimes`). #92/#93 are `--retry` (removes saved lines, keeps throttled ones, exit 2); the REPL `r` shares the code. #94 is `--no-open` / `--no-notify`. #95 duplicate and skipped now toast (hotkey only under `auto`). #96/#97 failures are `-u critical`, successes `-t 3000`, `-a yt2obsidian`. #98 the toast shows the real title. #99 short stub reasons in the toast. #100 `.lock` file with `flock` (second run waits, then reports a duplicate). #101 `wl-paste --type text`. #102 `yt` no longer forces `-i`, so the bind can call it. #105 exit codes are in `--help` and the README.

92. **[M]** **Add `--retry`.** Loop `retry.txt`, remove lines that succeed, stop at the first throttle. Without it the retry list is write-only; with it the REPL's `r` is one call.
93. **[S]** **Remove a URL from `retry.txt` once it saves** (by hand or in the REPL). Otherwise old entries stay forever.
94. **[S]** **`--no-open` and `--no-notify` flags** override the config for one run (batch use).
95. **[S]** **Notify on duplicate and skipped Shorts** in hotkey mode. Both return 0 and are silent (:285-287), so a bind appears to do nothing.
96. **[S]** **`notify-send -u critical`** for failures and `-t 3000` for successes.
97. **[S]** **Use `-a yt2obsidian`** instead of passing the name as the summary. Cleaner in notification history.
98. **[S]** **Show the real title in the toast,** not `path.stem` (accents stripped, :307).
99. **[S]** **Shorten the stub reason for the toast** (`RESTRICTED`, `LIVE` are long, :33-34). Keep the long wording in the note.
100. **[S]** **Double-tap race** (from reading, not reproduced). Two overlapping hotkey runs both pass `find_existing` and write `Title.md` and `Title (2).md`. Take `fcntl.flock` on a lock file in `HERE`; the second run waits, then reports a duplicate.
101. **[S]** **`wl-paste --type text`** so an image on the clipboard does not stream bytes into Python.
102. **[S]** **Hyprland bind via `yt`:** once `yt` passes arguments through and the REPL is the tty default (see Interactive mode), the bind can call `yt` instead of hardcoding `.venv/bin/python`. Document it.
103. **[V][S]** **PATH differs between terminal and bind.** `node` lives in mise shims. yt-dlp accepts `deno` and `node` as JS runtimes (`/usr/bin/deno` exists). Test once from the actual bind.
104. **[S]** **Set `js_runtimes` explicitly** to the system `deno` path if the bind test fails.
105. **[S]** **Document exit codes** (0 ok, 1 bad input, 2 stopped). They are undocumented (:283, :300).

## E. Remove or simplify code

**Status: done (25 of 29), 2026-10-20.** Not done, after testing against live YouTube: #108 (with `ignore_no_formats_error` a deleted video returns `None` instead of raising, which would break the "video unavailable" failure), #109 and #112 (depend on #108; private/members-only still arrive as exceptions), #110 (`skip: translated_subs` still returns 1085 `tlang=` URLs for the test video, so the check stays). #118 was already done in D (`finish`); the success path now uses it too (#119), so a save toasts through the same code as a failure. #114/#115/#120: network errors are classified by type (`transient`) and the caption fetch uses `ydl.urlopen`; a 403/404 on the caption URL fails at once (checked live: 404 is not retried). #128: `write_atomic` is a temp file + `os.replace` after an `exists()` check (the run lock covers the race); this also removes the hard-link need (#208). #134: kept both `/v/` and `music.youtube.com` (you might paste them). `Throttled` is now `Stop`; `fetch`, `fetch_track`, `with_retries` take ints; `main(args)` takes the URL as `args[0]`. Tests use `y.` everywhere and imports sit at the top.

106. **[S]** **Delete `from yt2obsidian import *`** in the tests (`test_yt2obsidian.py:2`). It is already imported as `y`. Pick one style.
107. **[S]** **Delete `skip_download` and `noplaylist`** from the yt-dlp options (:110). `extract_info(download=False)` already skips the download, and the URL is a single `watch?v=` link.
108. **[V][S]** **Add `ignore_no_formats_error: True`** (real option, `YoutubeDL.py:261`). Upcoming and format-less videos then return `info` instead of raising, so the `exc` path in `stub_reason` shrinks.
109. **[S]** **Delete the `exc` param of `stub_reason`** if the previous item works. The message-matching branches (:175-183) exist only for exceptions.
110. **[V][S]** **Delete the `tlang=` check in `pick_track`** (:155) and its test by passing `extractor_args={"youtube": {"skip": ["translated_subs"]}}`. `_video.py:4237` skips translated subs when that is set. Keep the check if you don't trust the arg.
111. **[S]** **Return `(vid, is_short)` from `parse_url`** instead of the string `kind` (:89-105).
112. **[S]** **Delete substring checks in `stub_reason`** (`your age`, `members-only`, :180) once `availability` covers them. Keep only strings seen in a real run.
113. **[S]** **Replace the "yt-dlp behavior" comment block** (:166-172) with real values. It mixes findings and a to-do inside the code.
114. **[M]** **Replace `NET_RE`** (:26) with a type check on `e.exc_info` (yt-dlp keeps the original `urllib`/`socket` error there). Removes a fragile regex.
115. **[S]** **Delete the `isinstance` ternary in `with_retries`** (:129) after the previous item.
116. **[S]** **One `watch_url(vid)` helper.** `https://www.youtube.com/watch?v={vid}` is built in three places (:114, :200, :289). Delete `canonical` and `url = ""` in `main`.
117. **[S]** **Rename `Throttled` to `Stop`.** It is raised for a dead network too (:133). Name matches behavior; shorten the docstring to "Stop the run and queue the URL."
118. **[M]** **Replace the `done()` closure and `ping()`** (:268-277) with a module-level `finish(url, outcome, msg, code)`. The closure reads `url` from the enclosing scope, which is why `url = ""` exists.
119. **[M]** **Fold the success tail into the same path** (:304-307 repeats print, log, notify that `done()` does). One exit path instead of two.
120. **[S]** **Use `ydl.urlopen`** for the caption fetch (:140). One HTTP stack, same proxy and headers, and it drops the `urllib.request`/`urllib.error` imports. Extra reason: `urllib` sends `Python-urllib` as User-Agent.
121. **[S]** **Delete the `Path(inbox)` casts** (:210, :219). `inbox` is already a `Path` from `main`.
122. **[S]** **Delete `.lower()` after `u.hostname`** (:91). `hostname` is already lowercase.
123. **[S]** **Strip the URL once.** `get_url` strips (:81, :85) and `parse_url` strips again (:90).
124. **[S]** **Drop the extra parentheses** in `if (old := find_existing(...)):` (:286).
125. **[S]** **Pass ints, not `cfg`,** into `fetch`, `fetch_track`, `with_retries`. They only use `timeout` or `retries`. Test fakes become `lambda u, t: track`.
126. **[S]** **Default `argv` to `sys.argv[1:]`** so `get_url` checks `argv[0]` and tests stop passing `[None, url]`.
127. **[S]** **`HERE = Path(__file__).resolve().parent`** (:18). A symlink in `~/.local/bin` would otherwise look for `config.toml` next to the symlink.
128. **[M]** **Simplify `write_atomic`** (:217-235). Temp file + `os.link` + `unlink` + `FileExistsError` loop is 20 lines; `os.replace` after `dest.exists()` is half. The race it guards against does not exist for one user. Also drops `mkstemp` and `chmod`.
129. **[S]** **One `ask(prompt)` helper** for the `input()` + EOF/Ctrl-C block that `repl` (:317-321) and `settings_menu` (:67-71) both repeat. Returns `None` on quit.
130. **[S]** **Drop `quiet` and `no_warnings`** once a no-op `logger` is passed (see yt-dlp stderr).
131. **[S]** **Move `tempfile`/`Path`/`mock` imports to the top of the test file;** three functions re-import them.
132. **[S]** **`with_retries` returns `None` if `retries < 1`** (loop never runs, :123). Validate in `load_config` or `raise` after the loop.
133. **[S]** **`queue_retry` opens the file twice** (:257-259) and has no `encoding`. One `a+` open reads and appends.
134. **[S]** **Decide on `music.youtube.com` and the `/v/` path** (:28, :100). Delete them if you never paste those; keep if you do.

## F. Transcript quality

**Status: done (10 of 21 open items), 2026-10-20.** Checked against 13 real tracks (3 manual, 10 auto; Rick Astley, TED, Lex Fridman, Joe Rogan...). Done: #136 and #147 (every `[...]` tag and `♪` is dropped; real tracks only use brackets for `[Music]`, `[laughter]`, and the `[ __ ]` censor), #139 (each `>>` becomes a blank line, so speaker turns show), #143 (`en` before `en-US` / `en-orig`), #145 (`no English captions (found: fr, de)`; lists manual tracks and `-orig` auto tracks only, since the auto list holds every machine translation), #149, #150, #151 (tests). Checked, no action: #141 (no HTML entities in any sample), #154 (no `<c>`/`<i>` markup), #155 (doubled words like `I I` are real speech, not join bugs). Not done: #135/#137/#138/#140/#148 (you marked them for the skipped section), #153 (paragraph work, same group), #142 (NFC, low value), #144 (every sample offered `json3`; `vtt` fallback would be new parser code), #146 (only useful with the `Captions:` line, #156 [PRD]), #152 (cannot measure Obsidian from here).

135. **[M][PRD]** **Add paragraph breaks.** The transcript is one line (:163), 2,089 chars for a 3-minute video, 100k+ for a long one. Break on `tStartMs` gaps over ~2 s. PRD allows "light cleanup"; a blank line fits. (MOVE TO SKIPPED SECTION)
136. **[V][S]** **Strip `♪` and `[...]` tags.** The Rick Astley transcript starts `[♪♪♪] ♪ We're no strangers to love ♪ ♪ You know...`. `re.sub(r"\[[^\]]*\]|♪|>>", "", text)`. Check manual captions first; some use brackets meaningfully.
137. **[V][S]** **Use `info["chapters"]` as paragraph breaks when present** (3 on a test video), else pause gaps. [PRD] if you also want headings. (MOVE TO SKIPPED SECTION)
138. **[S]** **Cap paragraph length** (~600 chars) so a track with no pauses still gets breaks. Split at the next sentence end or space. (MOVE TO SKIPPED SECTION)
139. **[S]** **Split on `>>`** (speaker change in manual captions) instead of deleting it.
140. **[M]** **Detect repeated rolling lines in auto captions.** Check a real sample first; it may already be fine. (MOVE TO SKIPPED SECTION)
141. **[S]** **Decode HTML entities** (`&amp;`, `&#39;`) if any show up in real tracks. Check one first.
142. **[S]** **NFC-normalize the transcript** (`unicodedata.normalize`) so Obsidian search matches. Cheap, low value.
143. **[S]** **Prefer `en` over `en-US/GB`** within a key. Dict order decides today (:151). Pick `en` first explicitly.
144. **[M]** **Fall back to `vtt`** if `json3` is missing. Today `pick_track` returns `None` and a "no captions" stub is saved (:157), which would be wrong. Log the formats seen.
145. **[S]** **Say which languages exist:** `no English captions (found: fr, de)` instead of `NO_CAPS`. More honest.
146. **[V][S]** **Return which dict a track came from** (`subtitles` vs `automatic_captions`) from `pick_track`. Manual and auto URLs look the same (both contain `caps=asr`), so you can't tell from the URL.
147. **[S]** **Check for `[ __ ]` censor tags** in auto captions and strip them with the music tags.
148. **[M][PRD]** **Optional timestamps** every N minutes (`[05:00]`). PRD says none in v1; only if you want them later. (MOVE TO SKIPPED SECTION)
149. **[S]** **`en-orig`** (original-language auto track) matches `startswith("en-")` (:152). Add a test line so nobody breaks it.
150. **[S]** **Empty text after cleanup** (all music tags) should give the no-captions stub, not an empty note. `transcript_text` returns `""`, which is falsy, so check the stub reason says so.
151. **[S]** **Check non-English characters in the body** survive the write. The body path uses utf-8 and nothing strips them, but only the filename is tested.
152. **[S]** **Measure Obsidian on a 100k-char single line** before deciding how urgent paragraphs are. Not measured.
153. **[M]** **Break at sentence ends** when captions have punctuation (manual tracks), in addition to pause gaps.
154. **[S]** **Strip stray markup** (`<c>`, `<i>`) if a manual track has any. Check a sample.
155. **[S]** **Collapse doubled words at event joins** (`the the`) if the join (:162) creates them. Check a sample.

## G. Note format

**Status: done (6 of 8), 2026-10-20.** Added after your OK: #157 (`Duration:`, h:mm:ss or m:ss, left out when YouTube gives none) and #160 (`Saved:` date; both lines are in real notes and stubs, PRD 7.4 updated). #159: you said no. Done: #158 (a stub with no title says `Title: unknown`), #161 (already `No transcript: <reason>`; no change), #162 and #163 (tests; `write_atomic` already writes `\n`). Not done: #156 (`Captions:`; not requested), #159 (chapter headings; declined).

156. **[PRD][S]** **`Captions: manual|auto` line.** Tells you how much to trust the text. Needs `track_kind` from above.
157. **[PRD][S]** **`Duration:` line.** `info["duration"]` exists (213 for the test video).
158. **[S]** **Stub `Title:` shows the raw ID** when yt-dlp has no title. Print `unknown` (moot after junk stubs are removed).
159. **[M][PRD]** **Chapter headings** (`## Chapter title`) when chapters exist. Pairs with paragraph breaks.
160. **[PRD][S]** **`Saved:` date line** to tell when you captured it vs when it was uploaded. Taste.
161. **[S]** **Stub wording:** `No transcript: <reason>` reads well; keep the reason sentences short and lowercase-safe.
162. **[S]** **`upload_date` malformed** (`"2024"`) gives `Date: unknown` (:198). Add a test.
163. **[S]** **Write `\n` newlines explicitly** with `newline="\n"` so a future Windows run does not write CRLF.

## H. Filenames

**Status: done (13 of 18), 2026-10-20.** Done: #164, #165, #166 (one allowlist after NFKD; `BAD_CHARS` and the ASCII encode are gone), #169 and #175 (`strip(" .,;-_")`), #171 (fallback is `<channel> video-<id>`), #173 (clash check ignores case), tests #170, #176, #177, #178, #180. Not done: #167 and #172 (need a PRD change; say yes first), #168 and #181 (taste), #174 (you only sync to laptop and phone), #179 (`render` shows the bare ID as the link label, the filename uses the fallback; different purposes, left alone). PRD 7.5 updated.

164. **[V][S]** **Fold accents first.** `safe_name("Café – Don’t Stop")` returns `'Caf Dont Stop'` (re-run today). Run `unicodedata.normalize("NFKD", t)` before the ASCII encode and `Café` becomes `Cafe`. Side effect: `ﬁ` becomes `fi`.
165. **[S]** **Map curly quotes and dashes** (`’ “ ” – —`) to ASCII before stripping, so `Don’t` becomes `Don't`.
166. **[S]** **Replace `BAD_CHARS` and the ASCII encode/decode** (:29, :189) with one allowlist after NFKD: `re.sub(r"[^A-Za-z0-9 '(),.&!+=@$%~_-]", "", s)`. No 25-character denylist to keep complete.
167. **[M][PRD]** **Keep Unicode letters in filenames.** Japanese, Chinese, Arabic, Cyrillic titles become `video-<id>.md` today (tested: `日本語🔥`). Obsidian handles them fine. Needs a PRD change (7.5) and a byte-length cap instead of a character cap.
168. **[S]** **Cap the filename at ~120 characters** for readability. 247 is legal but ugly in the file list. Taste.
169. **[V][S]** **Strip trailing punctuation.** `10 Hours of Rain Sound ... Meditation, Yoga,.md` was saved. Use `strip(" .,;-_")` after the ASCII strip.
170. **[S]** **Test that `'` survives** (it is not in `BAD_CHARS`).
171. **[S]** **Fallback name `<channel> video-<id>`** instead of `video-<id>`, so notes stay findable.
172. **[S][PRD]** **Optional date prefix** (`2024-01-31 Title`). Sorting aid. PRD says filename = title.
173. **[S]** **Names that differ only by case** (`Title.md` / `title.md`) collide on case-insensitive filesystems (phone sync). Fold case when checking for a clash.
174. **[S]** **Windows-reserved names** (`CON`, `NUL`, `AUX`). Only matters if the vault syncs to Windows. You have laptop and phone; skip unless that changes.
175. **[S]** **Leading `-`, `_`, or `.`** can confuse tools. Obsidian is fine; strip a leading `.` so the note is not hidden (`strip(" .")` covers it).
176. **[S]** **Test a 400-character CJK title** against the 255-byte cap. The existing test uses ASCII only.
177. **[S]** **Titles ending in `(2)`** become `Part (2) (2).md` on a clash. Harmless; leave a test so it stays so.
178. **[S]** **Titles that reduce to punctuation only** fall back to `video-<id>`. Add a test.
179. **[S]** **Empty `title` from yt-dlp:** `render` falls back to `vid`, `safe_name` to `video-<id>`. Make them consistent.
180. **[S]** **Keep `&` in names;** Obsidian allows it. The allowlist item includes it. Add a test.
181. **[S]** **Different videos with identical titles** get `(2)`, `(3)`. Consider appending the channel or video ID instead, so names stay meaningful.

## I. URL parsing

**Status: done (12 of 14), 2026-10-20.** Done: #182 (`youtube-nocookie.com`), #183 (scheme-less), #184 (wrapping `<>()[]"'` and trailing `.,;!?` stripped), #185 (already worked through `urls_in`; test added), #186, #190, #194 (tests), #187, #188, #191 (clear messages for playlist, clip, channel/handle URLs), #193 (`run.log` and `retry.txt` get the canonical `watch?v=` URL). Not done: #189 (bare IDs, optional), #192 (Shorts message already names the ID; the batch prints `[n/N]`), #195 (skip).

182. **[V][S]** **Add `youtube-nocookie.com`** (embed links; currently rejected). Two lines in `HOSTS`.
183. **[S]** **Accept scheme-less pastes** (`youtu.be/ID`, `youtube.com/watch?v=ID`). `urlparse` gives no hostname, so they are rejected. Prepend `https://` when there is no `://`.
184. **[S]** **Strip wrapping characters** (`<url>`, `"url"`, `'url'`, trailing `.` or `,`). The log has a case where a trailing period came along.
185. **[S]** **Find the first YouTube URL inside pasted text** (`Check this https://youtu.be/ID`). Handy from chat apps.
186. **[S]** **Test `watch?v=ID&list=PL...`.** It works since `v` is read; it is the most common real paste (the log has `&pp=...`).
187. **[S]** **Say "playlists are not supported"** for `/playlist?list=` instead of `no video id in URL`.
188. **[S]** **Say "clip links are not supported"** for `/clip/<id>` (clip IDs are not video IDs).
189. **[S]** **Accept a bare 11-character video ID** as input? Convenient, but `hello`-style garbage tests still must fail. Optional.
190. **[S]** **`youtu.be/IDextra` is rejected** (verified earlier). Keep; add a test.
191. **[S]** **Clear message for channel/handle URLs** (`/@name`, `/channel/...`): "that is a channel, paste a video link".
192. **[S]** **Shorts message** says `Skipped: Shorts are not processed (ID)`. Fine; add the full URL if multi-URL lands.
193. **[S]** **Log the canonical URL,** not the raw paste with `&pp=...` tracking (the log has such rows). Makes grepping a video ID reliable.
194. **[S]** **Test `/live/ID`** (supported, :100) including `?feature=share`. Exists for one form only.
195. **[S]** **`www.youtu.be`, `gaming.youtube.com`:** almost never seen. Skip unless the log shows them.

## J. Retry, throttle, network

**Status: done (8 of 12), 2026-10-20.** Already done in earlier sections: #203 (`encoding` on `retry.txt`), #204 (`--retry` stops at the first throttle), #206 (caption fetch uses `ydl.urlopen`). Done now: #197 (`retries` counts attempts; menu and example file say so, key name kept so your config still works), #198 (default `timeout` is 15; your `config.toml` still says 30), #200 (failed and stopped rows in `run.log` end with `[yt-dlp <version>]`), #202 (test: `youtu.be/ID` and `watch?v=ID&pp=...` queue one line). Not done: #196 (a URL fetched seconds ago does not expire; a re-fetch would not fix a real 403), #199 (a hard deadline needs threads; `timeout` x `retries` is the cap), #201 (nothing would read the reason), #205 (probably no), #207 (skip; saves about 5 s on a dead network only).

196. **[S]** **Treat 403 on the caption URL as a stop-and-refetch.** Expired signed URLs come back 403. Re-fetch `info` once instead of retrying the same URL.
197. **[S]** **`retries = 3` means three tries,** not three retries. Rename the key `attempts` or document it.
198. **[V][S]** **Consider `timeout = 15`.** A dead network gave up in 6.2 s (3 tries). With real timeouts it is up to 30 s x 3 plus sleeps, about 96 s with no feedback (computed, not measured).
199. **[M]** **One overall deadline per URL** instead of per-attempt timeouts, so a slow run can't exceed ~45 s.
200. **[S]** **Log the yt-dlp version on failures.** Most breakage is a stale yt-dlp.
201. **[S]** **Store a reason in `retry.txt`** (`url<TAB>throttled|network`), so `--retry` can wait longer for throttles.
202. **[S]** **Canonicalize URLs before queueing** so `youtu.be/ID` and `watch?v=ID` don't both sit in `retry.txt`. `main` queues `canonical` (:299), so verify and add a test.
203. **[S]** **`retry.txt` read/write without `encoding`** (:257, :259). Add `encoding="utf-8"`.
204. **[S]** **`--retry` stops at the first throttle** and leaves the rest queued.
205. **[M]** **Optional `cookiesfrombrowser`** for bot checks and age-restricted videos. [PRD] says restricted gets a stub; this would turn some stubs into notes at a privacy and complexity cost. Probably no.
206. **[S]** **Check the caption fetch User-Agent.** `urllib` sends `Python-urllib/3.x`; using `ydl.urlopen` fixes it (see Remove).
207. **[S]** **Check for network up front** (cheap DNS lookup) so a dead network fails in 1 s, not 6.

## K. Dedupe and write path

**Status: done (9 of 13), 2026-10-20.** Already done in earlier sections: #208 (no hard links since E #128). Done now: #211 (`duplicate` rows in `run.log` hold the existing note's path), #212 (`find_existing` searches subfolders of the inbox, so a note you filed into a subfolder still dedupes), #219 (matches the video ID in a `watch?v=` or `youtu.be/` link, so a retyped link still dedupes), tests #215 (BOM, CRLF, a note starting with a heading), #216 (invalid bytes), #217 (read-only inbox gives `failed: [Errno 13] Permission denied: ...`), #218 (disk full leaves no temp file), #220 (already covered by the duplicate test). Not done: #209 (the temp file must sit on the same filesystem as the note for `os.replace`, and it is a dotfile), #210 (not measured; fine at hundreds of notes), #213 (a note moved or deleted *outside* the inbox is still re-saved; treating `run.log` as "seen" would stop you re-saving a note you deleted on purpose, so it needs your call; same as A #18), #214 (needs a PRD OK).

208. **[S]** **Hard links fail on exFAT/FAT/some network mounts** with `OSError` (:229). If the vault ever lives there, every write fails. Fall back to `os.replace`, or simplify (see Remove).
209. **[S]** **The temp file `.yt2obsidian-*.tmp`** (:221) briefly sits in the vault. Obsidian ignores dotfiles, but Sync may upload it. Write the temp file outside the vault if on the same filesystem.
210. **[S]** **`find_existing` opens every note** on every run (:210). Fine at hundreds; measure at thousands before fixing.
211. **[S]** **Log the existing note's path** for `duplicate` rows. Today the log has only the URL.
212. **[S]** **Search subfolders** (`**/*.md`) in `find_existing` so moved notes are found. Slower; measure.
213. **[M]** **Treat `saved` rows in `run.log` as "seen"** so even deleted-and-moved notes aren't re-saved. Decide whether deleting a note should allow re-saving (probably yes).
214. **[M][PRD]** **Re-check stubs.** A command that re-fetches stub notes and replaces ones whose captions now exist. PRD says never overwrite; replacing a stub is different, but it needs your OK.
215. **[S]** **`find_existing` with a BOM or CRLF on line 1** (e.g. a note edited on Windows) may miss. Strip before matching; add a test.
216. **[S]** **Keep `errors="replace"`** on read (:211); it is right. Add one test with invalid bytes in a note.
217. **[S]** **Read-only inbox or vault** raises `PermissionError`; make it a clean failure message (covered by the REPL catch-all, but the text should be readable).
218. **[S]** **Disk full mid-write:** `write_atomic`'s `finally` unlinks the temp; test it with a patched write that raises.
219. **[S]** **Match on the video ID,** not `youtube.com/watch?v=<id>` in line 1, so a note you retyped with `youtu.be/<id>` still dedupes.
220. **[S]** **Saving the same video twice quickly** (REPL double-paste) should not create `(2)`. Covered by dedupe in one process; add a test.

## L. Config

221. **[S]** **Validate `retries >= 1` and `timeout > 0`.** `retries = 0` makes `with_retries` return `None` and crash later.
222. **[V][S]** **`config.example.toml` says "its basename is the vault name"** (line 1). Becomes false if you switch to `obsidian://open?path=`; update the comment.
223. **[S]** **Use `obsidian://open?path=<abs path>`** and delete `relative_to`, `quote(vault.name)`, and the vault-name assumption (:245-248). One line, and works if the vault display name differs from the folder.
224. **[S]** **Add `open_obsidian` and `notify` to `config.example.toml`** (commented, default true).
225. **[S]** **Reject a relative `vault`** or resolve it against `HERE`. A hotkey run starts in `$HOME`, so a relative path means a different place than in your terminal.
226. **[S]** **Absolute `inbox` escapes the vault.** `cfg["vault"] / "/tmp/x"` is `/tmp/x`, so the note saves outside the vault and `open_obsidian`'s `relative_to` (:246) raises `ValueError` after saving. Reject absolute or `..` inboxes.
227. **[S]** **Warn if `vault` has no `.obsidian/` folder.** It means a wrong path or an unopened vault.
228. **[S]** **`YT2OBSIDIAN_CONFIG` env var** to point at another config. Only if you ever run two vaults.
229. **[M]** **First-run setup in the REPL:** if `config.toml` is missing, ask for vault and inbox and write it. Replaces "copy the example file".
230. **[S][PRD]** **Delete `timeout`/`retries` from config** and make them constants. You haven't changed them; PRD 7.8 says config "includes" them, so it is a PRD call.
231. **[S]** **Mark `timeout` and `retries` optional** in `config.example.toml`.
232. **[S]** **Include the config path in config errors** so the message says which file to fix.

## M. Logging

233. **[S]** **Log the title and note path** on `saved` and `stub` rows. Today a row has URL and outcome only.
234. **[S]** **Log elapsed seconds** per run.
235. **[S]** **Add a `source` column** (`repl`, `clipboard`, `argv`) to separate hotkey runs from terminal runs.
236. **[S]** **Truncate non-URL text in the log** to ~60 chars (see Security).
237. **[S]** **Include the UTC offset in timestamps** (`isoformat(timespec="seconds")` on an aware datetime). Local naive time is fine on one machine; skip if you never travel.
238. **[S]** **Rotate or cap `run.log`.** Not needed at this volume (7 rows). Revisit past ~10k lines.
239. **[S]** **Document the columns** (time, URL, outcome, detail; tab-separated) in the README so it can be grepped.
240. **[S]** **Log `duplicate` and `skipped`** rows consistently (they log today); add the existing path.
241. **[S]** **`yt2obsidian.py --stats`:** count outcomes from `run.log`. Or just `cut -f3 run.log | sort | uniq -c`; put that in the README instead.
242. **[S]** **Log the exception class** (`DownloadError`, `Throttled`) in the detail column for easier grouping.

## N. Tests

243. **[S]** **Test `repl` dispatch** with patched `input`: `q`, `quit`, `s`, blank line, a URL, and EOF. The suite has no REPL test (it only covers `main`).
244. **[S]** **Test the REPL survives an exception and Ctrl-C** after the catch-all lands.
245. **[S]** **Test `set_toggle` keeps comments and other keys** (use a temp `config.toml`, patch `HERE`).
246. **[S]** **Test `set_toggle` appends a missing key** and writes lowercase `true`/`false`.
247. **[S]** **Test `settings_menu`:** number flips the toggle, Enter leaves, invalid input prints a hint.
248. **[S]** **Test `load_config`** defaults, `~` expansion, and the missing-file and missing-key messages.
249. **[S]** **Test `get_url`:** argv, clipboard happy path, empty clipboard, missing `wl-paste` (patch `subprocess.run`).
250. **[S]** **Test `open_obsidian` builds the right URI** for a vault path with spaces (patch `Popen`).
251. **[S]** **Test `notify` swallows a missing binary** (patch `run` to raise `FileNotFoundError`).
252. **[S]** **Test the toggles in `main`:** `notify = false` sends no toast on failure, `open_obsidian = false` skips the open. `run_main` never sets either key in `cfg` (:106) and patches `open_obsidian` to a no-op, so the toggles are untested.
253. **[S]** **Test HTML-in-JSON failure** from `fetch_track`.
254. **[S]** **Test Unicode IDs** are rejected.
255. **[S]** **Test `fetch()`** maps 429, `not a bot`, and `rate-limited` to `Throttled` by patching `yt_dlp.YoutubeDL`. `run_main` replaces `fetch` wholesale, so `fetch` has no test. Use the real text from `_video.py:4072`.
256. **[S]** **Test `fetch_track` on 429 and 403** (patch `urlopen`, or `ydl.urlopen` after the swap).
257. **[S]** **Test accent folding** after the filename change.
258. **[S]** **Test the playlist-with-`v=` URL** and the scheme-less and wrapped pastes.
259. **[S]** **Test `queue_retry` doesn't append the same URL twice.**
260. **[S]** **Test a non-network `DownloadError`** ("Video unavailable") passes `with_retries` after one call.
261. **[S]** **Test "too many name clashes"** once the cap is 99: create 99 files, expect `OSError`.
262. **[S]** **Test an empty-text track** gives the no-captions stub, not an empty note.
263. **[S]** **Commit one real captured json3 track** (~10 events). The earlier sample lived in a session scratch folder that is gone; capture a new one. Synthetic tracks miss real quirks like `♪`.
264. **[S]** **Commit one real `info` subset** (`availability`, `live_status`, `age_limit`, caption keys). `stub_reason` tests use hand-built dicts.
265. **[S]** **Tests leak temp dirs and print a lot** (`run_main` uses `mkdtemp`, never cleans up; `Saved stub ...` and `Stopped: ...` lines show up). Use `TemporaryDirectory` and patch `print`.
266. **[S]** **Runner prints a summary** (`N passed`) and exits non-zero on failure. Today it stops at the first assert with a traceback.
267. **[S]** **Opt-in `--live` test** that fetches a known captioned video (~2 s). A canary after `pip install -U yt-dlp`.
268. **[S]** **Tests for paragraph breaks** once built: gap, chapter, and length cap.
269. **[S]** **Tests for `♪` / `[...]` / `>>` stripping** with real examples.
270. **[S]** **Test dedupe** with a BOM, CRLF, and a note whose first line is a heading.
271. **[S]** **Test `main`/`process` return values** once it returns (outcome, path).
272. **[S]** **Test `--retry`:** removes saved lines, stops at the first throttle, leaves the rest.

## O. Docs (README, PRD, BUILD_PLAN)

273. **[S]** **README: document `./yt`, interactive mode, and the settings menu.** None of them are mentioned; the README still describes only the one-shot and hotkey flow.
274. **[S]** **README: list the prerequisites** (`wl-clipboard`, `libnotify`, `xdg-utils`, Python 3.11+ for `tomllib`, Obsidian with URI support). A fresh machine fails at `wl-paste` otherwise.
275. **[S]** **README: say what a stub is** and that stubs block re-saves.
276. **[S]** **README troubleshooting, four bullets:** no notification, nothing opens (check `open_obsidian`), rate-limited, stale yt-dlp.
277. **[S]** **README: show one concrete Hyprland line** (not `<path>` twice) and note quoting for paths with spaces. Mention the `yt` wrapper as the shorter bind.
278. **[S]** **README: one sentence on "non-ASCII removed from filenames"** so missing characters aren't a surprise. Update it if filenames go Unicode.
279. **[S]** **README: state the tested versions** (yt-dlp 2026.8.19, Python 3.14). A future breakage is then easy to attribute.
280. **[V][S]** **README: rebuild the venv after an Arch Python upgrade.** `.venv/bin/python` is a symlink to `/usr/bin/python`. `rm -rf .venv && python -m venv .venv && .venv/bin/pip install -r requirements.txt`.
281. **[S]** **README: "when it stops working" in this order:** update yt-dlp, rebuild `.venv`, check `run.log`.
282. **[S]** **README: a canary line.** After upgrading yt-dlp run `.venv/bin/python yt2obsidian.py https://youtu.be/dQw4w9WgXcQ` and check the note appears. No code.
283. **[S]** **README: keep the `retry.txt` line only if `--retry` gets built.** Otherwise delete the line and the feature.
284. **[S]** **PRD §6 (workflow) still says clipboard first.** Rewrite to lead with the interactive prompt, then clipboard/hotkey.
285. **[S]** **PRD §4 says "no multi-URL batch input"** and "no preview step". Update if you build multi-URL or the REPL stays.
286. **[S]** **PRD §7.5 contradicts itself** ("not truncated" vs "capped") and says non-English characters are removed. Rewrite after the filename decisions; also §9 says "open-source Python library" where it is now yt-dlp.

## P. Repo hygiene and packaging

287. **[M]** **Delete `BUILD_PLAN.md`.** It says "Written for the builder (Claude)" and Phases 0-5 are done. Move the "Known risks" list into the README if you want it.
288. **[S]** **Trim `PRD.md`:** §4 Non-Goals (17 lines of "no X"; keep the 5 that guard scope: no AI, no overwrite, no Shorts, no playlists, no sponsor removal), §14 Open Questions (two are decided), §15 Future Versions (mark unscheduled or delete), §11/§13 (merge into 3 lines).
289. **[S]** **`requirements.txt` has no version floor.** Use `yt-dlp>=2026.8` so a clean install isn't ancient. Don't pin exactly; you need updates.
290. **[S]** **`git tag v1`** once the top fixes land. A cheap restore point before the next yt-dlp upgrade.
291. **[S]** **Pre-commit hook** (`.git/hooks/pre-commit`, one line) that runs the tests. They take well under a second.
292. **[S]** **Run `uvx ruff check .` once** as a one-off, not a dependency. No linter is installed, so dead imports would go unnoticed.
293. **[S]** **Rename the folder and repo** `auto-ai-yt-summaries` to `yt2obsidian`. The tool does no AI and no summaries; everything else is already named `yt2obsidian`.
294. **[S]** **Add a `LICENSE`** only if you plan to share (PRD: "clean enough to share later"). If you do share: README must say Wayland-only.

## Q. Security and privacy

295. **[S]** **Truncate non-URL text** in the log, toast, and terminal echo to ~60 chars. A password pasted by mistake lands in `run.log` verbatim today (`log_run(url, ...)` in the parse-failure path).
296. **[S]** **Reject `inbox` values that are absolute or contain `..`** (see Config). They write outside the vault.
297. **[S]** **Strip control characters and escape sequences** before printing any title or yt-dlp message, once titles are echoed.
298. **[S]** **Don't persist non-URL lines** in readline history. Pasted secrets would sit in `.history` in plaintext.
299. **[S]** **`run.log` is a watch history.** It is gitignored; also `chmod 600` it on creation.
300. **[S]** **Re-check URI quoting** after switching to `obsidian://open?path=`. Keep `quote(..., safe="")` on the absolute path.

## Things I would not build

These came up and are scope creep for a small CLI. Not tasks, not counted.

- Summaries or key points (PRD says no).
- A GUI, TUI framework (`curses`, `textual`), or tray icon. `input()` is enough.
- Playlist and channel support.
- A database or index of saved videos. The inbox folder is the database.
- A config option for every filename rule.
- Parallel fetches or `asyncio`.
- A plugin or hook system.
- Docker or a system install. PRD says run from the project folder.
- Audio transcription fallback (Whisper).
- Thumbnails or channel avatars.
- Switching to `youtube-transcript-api`. yt-dlp gives metadata and captions in one call.
- `argparse`. A hand-rolled `-i`, `-h`, `--retry` is a few lines; revisit past ~5 flags.
- The `logging` module. A tab-separated `run.log` is greppable.
- Type hints, a `Config` dataclass, or pydantic.
- Caching yt-dlp `info` on disk.
- `tenacity` or another retry library. `with_retries` is 12 lines.
- A clipboard-watching daemon (PRD: no background service).
- An Obsidian plugin, web UI, or phone share target.
- Splitting `yt2obsidian.py` into modules. 331 lines.
- A Makefile, `pyproject.toml`, or CI for one script and one user.
- Auto-updating yt-dlp (PRD non-goal). `u` on request is the limit.

---

## Suggested order

1. Crash paths in the REPL: #1, #2, #20, #7, #5 (~30 min total).
2. Throttle and failure messages: #12, #28, #56, #29, #57 (~30 min).
3. Refactor for the CLI shape: #49, #48, #129, #118 (~45 min). Most Interactive mode items depend on these.
4. Interactive polish: #31, #32, #38, #40, #37, #45 (~30 min).
5. yt-dlp option cleanup: #107, #108, #110, #120 (~15 min, re-run tests after).
6. Note quality: #136, #135, #164, #165, #169 (~45 min).
7. Make the retry list real (#92, #42) or delete it. Then doc trims.

Total: 300 tasks.
