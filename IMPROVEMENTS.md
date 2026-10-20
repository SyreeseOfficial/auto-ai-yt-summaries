# Improvements and removals

Audit of `yt2obsidian.py` (277 lines), `test_yt2obsidian.py`, docs, and repo. Line refs are `yt2obsidian.py` unless noted.

Tags: **[V]** = verified by running it or reading yt-dlp source. **[S]** = small (<10 min). **[M]** = medium (10-60 min). **[L]** = large. **[PRD]** = contradicts or changes a PRD decision, so you must say yes first.

Leaning rule: if an item deletes code, it comes before an item that adds code.

## Do these first (top 7)

1. Add a top-level exception handler (#1). Hotkey runs fail silently today.
2. Treat YouTube's "rate-limited" message as a throttle (#9).
3. Open the existing note on duplicate, and notify (#46).
4. Use `obsidian://open?path=` instead of the vault-basename guess (#10).
5. Normalize accents before the ASCII strip (#78).
6. Do one real end-to-end run: no `run.log` exists, so `main()` has never run for real (#14).
7. Delete `skip_download` and `noplaylist` from the yt-dlp options (#31).

---

## A. Bugs and crash paths (1-24)

1. **[V][S] No catch-all.** Any uncaught error (bad JSON, KeyError, disk full) prints a traceback only. From a Hyprland bind nobody sees it: no log line, no notification. Wrap the body of `main()` (:231) so unexpected exceptions go through `done("failed", ...)`.
2. **[V][S] Bad caption body crashes.** `json.load` in `fetch_track` (:109) raises `JSONDecodeError` on an HTML error page, and `with_retries` lets it through. Catch `ValueError` there and fall to a stub or a failure.
3. **[S] Missing `config.toml`** gives a raw `FileNotFoundError` (:40). Print "copy config.example.toml to config.toml".
4. **[S] Missing `vault` or `inbox` key** gives a bare `KeyError` (:233). Check both in `load_config`.
5. **[S] Typo in `vault` silently creates a fake vault.** `write_atomic` uses `mkdir(parents=True)`, so a wrong path makes a folder Obsidian never sees. Require `cfg["vault"].is_dir()`; keep `mkdir` only for the inbox itself.
6. **[S] `wl-paste` not installed** raises `FileNotFoundError`, which `main` does not catch (:246 only catches `ValueError` and `SubprocessError`). Add `OSError`.
7. **[V][S] `ID_RE` uses `\w`** (:23), which matches Unicode letters. `https://youtu.be/ééééééééééé` parses as a valid ID. Use `[A-Za-z0-9_-]{11}`.
8. **[S] Name-clash cap is inconsistent.** The loop runs to 999 (:194) but `MAX_NAME` reserves only `" (99)"` (:27). `" (999)"` can push past 255 bytes. Make the loop `range(1, 100)`.
9. **[V][S] Rate-limit message not matched.** yt-dlp says "This content isn't available, try again later ... rate-limited by YouTube for up to an hour" (`_video.py:4069`). `fetch` only matches "HTTP Error 429" and "not a bot" (:84). Result today: a stub note with a misleading reason, and no retry entry. Add `"rate-limited"` and `"try again later"`.
10. **[S] Vault name guess.** `open_obsidian` assumes the vault display name equals the folder basename (:215). Obsidian's `path=` URI parameter takes an absolute path and needs no vault name. See #51 for the removal.
11. **[S] HTTP 403/404 on the caption URL** is an `HTTPError`, which is an `OSError`, so `with_retries` retries it and then calls it "Throttled" (:96-101). Retry only timeouts, `URLError`, and 5xx. Fail fast on 4xx other than 429.
12. **[S] Parse failures log an empty URL.** If `get_url` raises, `url` is still `""` when `done` logs (:234, :247). Log the raw clipboard text.
13. **[S] Log lines can break.** `log_run` writes raw strings (:221). yt-dlp errors are multi-line and can contain tabs. Collapse whitespace before writing.
14. **[V][S] Never run against the real vault.** `run.log` and `retry.txt` do not exist in the project dir. Round 2 ran `main()` end to end into a scratch vault and it works (see #186). Still do one run into the real vault with real notify and open.
15. **[S] Stub is permanent.** A stub saved for a live or upcoming video blocks the real save later (`Already saved`, :250). Either let the duplicate message say "stub, delete it to retry", or treat stubs as replaceable. Replacing needs a [PRD] OK ("never overwrite").
16. **[M][PRD] Unknown errors become permanent stubs.** A non-throttle `DownloadError` that is not restricted or live writes `transcript fetch failed: ...` and then dedupe blocks any retry. A flaky error can freeze a good video as a stub. Safer: only stub for known reasons; queue the rest in `retry.txt`.
17. **[S] Dedupe reads only line 1** (:180). If you add frontmatter or a heading to the note, the match fails and a duplicate is saved. Read the first ~1 KB and search that.
18. **[M] Moved notes get re-saved.** `find_existing` only globs the top of the inbox (:178). Move a note to another folder and the same video is saved again. Cheap fix: also treat `saved` lines in `run.log` as "seen", or glob `**/*.md` in the vault (slower).
19. **[S] `RETRY_DELAY * attempt` sleeps after the last non-final try only**, which is right, but `time.sleep` blocks a hotkey run for up to 6 s with no feedback. Print "retrying (2/3)..." once per attempt.
20. **[S] `open_obsidian` runs after notify**, so a failure to open is silent. The `Popen` result is never checked. Fine for now, but log it if it raises `OSError` (missing `xdg-open`).
21. **[S] `notify` ignores non-zero exit.** If no notification daemon runs, `subprocess.run` returns quietly (:208). Acceptable; just note it in the README troubleshooting.
22. **[S] Title with `*` or `_` renders as bold or italic** in the link text (:171). Escape or strip `*_` in `label`. Low priority.
23. **[S] Title with `|` breaks Obsidian tables only if used in one.** Ignore. (Listed so nobody "fixes" it.)
24. **[S] `get_url` ignores extra argv** silently. Fine for single-URL v1. Ignore.

## B. Remove / delete (code) (25-45)

25. **[S] Delete `from yt2obsidian import *`** in the tests (`test_yt2obsidian.py:2`). You already import it as `y`. Pick one style.
26. **[S] Delete `skip_download`** from the yt-dlp options (:78). `extract_info(download=False)` already does it. See #31.
27. **[S] Delete `noplaylist`** (:78). The URL is rebuilt as a single `watch?v=` link, so there is no playlist to skip.
28. **[S] Delete `no_warnings`** only if you want to see yt-dlp deprecation notes. Keep `quiet`. Decide; default is to leave it.
29. **[S] Delete the `tlang=` check in `pick_track`** (:123) and its test, by passing `extractor_args={"youtube": {"skip": ["translated_subs"]}}` to yt-dlp. **[V]** `_video.py:4237` skips translated subs when `translated_subs` is in `skip`. Fewer lines, and yt-dlp does less work. Keep the check if you do not trust the arg.
30. **[S] Delete `kind` return value.** `parse_url` returns `(vid, kind)` only to detect shorts (:73). Return `(vid, is_short)` or let `main` check the path. Shorter and clearer.
31. **[V][S] Combine #26 and #27 into one edit** and add `ignore_no_formats_error: True`. It is a real yt-dlp option (`YoutubeDL.py:261`). Upcoming and format-less videos then return `info` instead of raising, so the `exc` path in `stub_reason` shrinks.
32. **[S] Delete `exc` param from `stub_reason`** if #31 works. The message-matching branch (:143-148, :150) only exists for exceptions.
33. **[S] Delete the `"your age"` and `"members-only"` substring checks** once `availability` from yt-dlp covers them. Keep only strings you saw in a real run (see the comment above `stub_reason`: private/members/age were "NOT reproduced live").
34. **[S] Delete the "yt-dlp behavior" comment block** (:134-140) once real values replace the guesses. It is a to-do note in the middle of the code.
35. **[M] Delete `NET_RE`** (:22) by catching `yt_dlp.utils.DownloadError` whose `exc_info` is a `urllib`/`socket` error. yt-dlp exposes the original exception as `e.exc_info`. Replaces a fragile regex with a type check.
36. **[S] Delete the `isinstance` ternary in `with_retries`** (:97) after #35. One line shorter.
37. **[S] Delete `RETRY_DELAY` as a module constant** and inline `2 * attempt`... but the tests patch it (`RETRY_DELAY=0`). Leave it. (Listed so you know it is deliberate.)
38. **[M] Delete the `done()` closure** and make `main` a flat sequence of early returns with a small `finish(url, outcome, msg, code)` helper at module level. The closure reads `url` from the enclosing scope, which is why `url = ""` exists at :234.
39. **[S] Delete `url = ""` and `canonical`** by building the canonical URL once from `vid`. `render` rebuilds the same URL (:168). Pass or share one helper `watch_url(vid)`. Three places now build `https://www.youtube.com/watch?v={vid}` (:82, :168, :253).
40. **[S] Delete `Throttled` for network failures** by renaming it to `Stop`. It is raised for a dead network too (:101). Name matches behavior. Rename only; no logic.
41. **[S] Delete `tempfile.mkstemp` + `os.chmod`** if you simplify the write path (#59). Fewer syscalls, no `0o644` fix-up.
42. **[S] Delete the `music.youtube.com` host** only if you never paste Music links. Otherwise keep.
43. **[S] Delete `"v"` from the `parts[:1] in (...)` tuple** (:68) if you never see `/v/ID` links (very old embeds). Rare.
44. **[S] Delete `fetch_track`'s own `urllib` path** by using `ydl.urlopen(url)` inside the same `YoutubeDL` context. One HTTP stack, same proxy, same cookies, same headers. Removes `import urllib.request` and `urllib.error` imports.
45. **[S] Delete the `Path(inbox)` casts** in `find_existing` and `write_atomic` (:178, :187). `inbox` is already a `Path` from `main`. Keep only if tests pass strings (they pass a `Path`).

## C. UX when launched from a hotkey (46-62)

46. **[S] Duplicate: open the old note and notify.** Today a duplicate prints to a terminal you do not have and does nothing (:250-251). `open_obsidian(vault, old)` plus `notify("Already saved: ...")` is two lines and the most useful hotkey behavior.
47. **[S] Notify on skipped Shorts.** Same reason: `done("skipped", ...)` has `code=0`, so no notification (:249, :239).
48. **[S] Notify on every outcome**, not only failures. Make `done()` always notify; the exit code only decides urgency.
49. **[S] Use `notify-send -u critical`** for failures and `-t 3000` for successes so errors stay visible.
50. **[S] Add `-a yt2obsidian`** (app name) instead of passing it as the summary. Cleaner in notification history.
51. **[S] Use `obsidian://open?path=<abs path>`** and delete `relative_to`, `quote(vault.name)`, and the vault-name assumption (:213-216). One line.
52. **[S] Notification body should show the title**, not only `path.stem` (which has accents stripped). `info["title"]` is available.
53. **[S] Print the clipboard text** when it is not a YouTube URL. "not a YouTube URL: 'hello'" is good; make sure the notification carries it too.
54. **[S] Play nice with no clipboard tool in SSH/X11.** Not needed; Wayland only per PRD. Ignore.
55. **[M] Add `--retry`.** `retry.txt` is write-only today: nothing reads it. A 10-line `--retry` that loops the file, removes lines that succeed, and stops at the first throttle makes the retry list real. Without it, delete the retry file feature (see #112).
56. **[S] Show progress in the terminal** ("fetching metadata", "fetching captions"). The first run takes several seconds with no output.
57. **[S] Exit codes are 0/1/2** (:247, :264) but undocumented. One line in the README.
58. **[S] After a stub, notification says "(stub: reason)"** but the reason string is long (:271). Shorten the RESTRICTED and LIVE constants for the toast; keep the long wording in the note.
59. **[M] Optional `--no-open` flag** for batch use. Only worth it if you add `--retry`.
60. **[S] Wrapper script for the Hyprland bind.** The bind must hardcode `<path>/.venv/bin/python`. A 2-line `run.sh` is easier to change than the bind. Or skip: one bind line is already short.
61. **[S] Bind should not need a terminal.** README snippet uses `exec`, which is right. Add "output goes nowhere; read `run.log` or the notification".
62. **[S] A "working..." notification** at start for slow runs. Optional; adds one more toast per run, so probably no.

## D. Transcript quality (63-76)

63. **[M][PRD] Add paragraph breaks.** The transcript is one giant line (:131). Break on gaps in `tStartMs` over ~2 s, or every ~5 sentences. Huge readability win in Obsidian. PRD says "plain text" and "light cleanup", so a blank line between paragraphs fits.
64. **[S] Strip noise tags** like `[Music]`, `[Applause]`, `>>` from auto captions: `re.sub(r"\[[^\]]*\]|>>", "", text)`. Check on real videos first; some manual captions use brackets meaningfully.
65. **[S] Skip events with no `segs`** — already handled by `or []`. Nothing to do. (Listed to close the question.)
66. **[M] Detect repeated lines in auto captions.** YouTube auto captions sometimes repeat rolling text. Check a real json3 sample before adding code. Might already be fine.
67. **[S] Decode HTML entities** (`&amp;`, `&#39;`) if any show up in real tracks. Probably not needed in json3; check one.
68. **[S] Fix music-note chars** (`♪`) the same way as #64.
69. **[S] Unicode normalize the transcript** (`unicodedata.normalize("NFC", ...)`) so search matches. Cheap, low value.
70. **[S] Collapse stray spaces before punctuation** (` ,` `.`)? Raw output is acceptable per PRD §7.2. Skip.
71. **[M][PRD] Optional timestamps** every N minutes (`[05:00]`). PRD says no timestamps in v1. Only if you want it later.
72. **[M] Prefer manual over auto is already right** (:118 order). Add a test that a manual `en-GB` loses to nothing and beats auto `en` — exists (test_pick_track). Done.
73. **[S] Prefer `en` over `en-US/GB`** within manual tracks? Dict order decides today. Pick `en` first explicitly, or ignore.
74. **[S] `en-orig`** is an original-language auto track. It matches `startswith("en-")`. Good. Add one test line so nobody breaks it.
75. **[M] Fall back to the other format** if `json3` is missing but `vtt` exists. Today `pick_track` returns `None` and a "no captions" stub is saved (:121-125), which would be wrong. Log the formats seen in that case.
76. **[S] Distinguish "no English track" from "no captions at all"** in the stub: "no English captions (found: fr, de)". More honest than `NO_CAPS`.

## E. Filename (77-90)

77. **[S] Cap the filename at ~120 chars** for readability. 247 chars is legal but ugly in Obsidian's file list. [PRD] says only the 255 limit; trimming is a taste call.
78. **[V][S] Normalize accents first.** `safe_name("Café – Don’t Stop")` returns `'Caf Dont Stop'` today. Run `unicodedata.normalize("NFKD", t)` before `encode("ascii", "ignore")` and `Café` stays `Cafe`.
79. **[S] Map curly quotes and dashes** (`’ “ ” – —`) to ASCII before stripping, so `Don’t` becomes `Don't`.
80. **[S] Use the apostrophe**: `'` is not in `BAD_CHARS`, so it survives. Good. Add a test.
81. **[S] Strip a trailing channel suffix** like ` - YouTube`. yt-dlp titles don't have it. Ignore.
82. **[S] Windows-reserved names** (`CON`, `NUL`, `AUX`). Only matters if the vault syncs to Windows. You have laptop and phone only. Skip.
83. **[S] Leading `-` or `_`** can confuse some tools. Obsidian is fine. Skip.
84. **[S] Names that differ only by case** (`Title.md` vs `title.md`) collide on case-insensitive filesystems (phone sync?). Rare. Skip unless Obsidian Sync complains.
85. **[S] Fallback name `video-<id>`** is fine. Better: `<channel> video-<id>` so notes are findable.
86. **[S] Date prefix option** (`2024-01-31 Title`). Taste only; helps sorting. [PRD] says filename = title.
87. **[S] Empty `title`** from yt-dlp falls back to `vid` in `render` but `safe_name(info.get("title"), vid)` makes `video-<id>`. Both fine; consistent.
88. **[S] The 255 limit counts the `.md`**; fine. Add a test with 400 chars and CJK combined (exists for ASCII only).
89. **[S] Double spaces inside names** are collapsed (:158). Good. Test exists.
90. **[S] Filenames ending in a period** are stripped (`strip(" .")`). Good.

## F. URL parsing (91-98)

91. **[S] Add `youtube-nocookie.com`** (embed links; **[V]** currently rejected). Two lines in `HOSTS`.
92. **[S] Add `www.youtu.be` and `gaming.youtube.com`**? Almost never seen. Skip.
93. **[S] `/watch/ID`** is rejected (**[V]**). Real? Almost never. Skip.
94. **[S] Accept a bare 11-char video ID** as input? Convenient, but "garbage" test uses `"hello"`. Skip.
95. **[S] Playlist link with `v=`** (`watch?v=ID&list=PL...`) works since `v` is read. Add a test, it's the most common real paste.
96. **[S] `youtu.be/ID` with trailing junk** (`youtu.be/IDextra`) is rejected (**[V]**). Good.
97. **[S] Clipboard with extra text** (`"Check this https://youtu.be/ID"`). Rejected today. Optional: regex-find the first YouTube URL in the clipboard. Handy when copying from chat apps.
98. **[S] Strip tracking params** is moot: you rebuild the canonical URL. Good. Nothing to do.

## G. Retry, throttle, network (99-108)

99. **[S] Add `"rate-limited"` to the throttle check** (#9). Biggest real-world miss.
100. **[S] Treat HTTP 403 on the caption URL as a stop**, not a retry. Expired signed URLs come back 403. Re-fetch `info` once instead.
101. **[S] Caption URLs from yt-dlp expire.** Fetch the track right after `fetch`; the code already does. Fine.
102. **[M] Add jitter** to retry delay. For three attempts it is noise. Skip.
103. **[S] Retry count means tries, not retries.** `retries=3` is 3 attempts. Rename the key `attempts` or document it.
104. **[S] Single `timeout` is used for both** yt-dlp and the caption fetch. Fine.
105. **[M] Optional cookies from browser** (`cookiesfrombrowser`) for bot-check and age-restricted videos. [PRD] says restricted gets a stub; this would turn some stubs into real notes. Adds a privacy and complexity cost. Probably no.
106. **[S] Print the yt-dlp version in `run.log`** on failures. Most breakage is a stale yt-dlp.
107. **[S] Suggest `pip install -U yt-dlp` in the failure notification** when the error looks like an extractor break ("Unable to extract", "nsig").
108. **[M] Auto-update yt-dlp** is a PRD non-goal. Keep it off.

## H. Dedupe and write path (109-118)

109. **[M] Simplify `write_atomic`.** Temp file + `os.link` + `unlink` + `FileExistsError` loop is clever but 20 lines. `os.replace` after `dest.exists()` is half the code. The race it guards against does not exist for a single-user tool.
110. **[S] Hard links fail on exFAT/FAT/some network mounts** with `OSError`. If the vault ever lives there, every write fails. Add a fallback to `os.replace`, or do #109.
111. **[S] Temp file in the vault** (`.yt2obsidian-*.tmp`, :189) may briefly show in file watchers. Obsidian ignores dotfiles. Fine.
112. **[S] If you skip #55, delete retry list code** (`queue_retry`, `RETRY`, the "Queued in" message, 2 tests). A write-only file is clutter. PRD §7.10 requires the list, so this is a [PRD] call.
113. **[S] `queue_retry` reads the whole file each time** (:225). Fine for a handful of lines.
114. **[S] `queue_retry` opens without `encoding`** (:227). Use `encoding="utf-8"` like the log.
115. **[S] `RETRY.read_text()`** same, no encoding. Add it.
116. **[S] `find_existing` opens every note** in the inbox on every run. At thousands of notes this is slow. Fine at hundreds. Measure before fixing.
117. **[S] `errors="replace"`** on read is good; keep.
118. **[S] Return the existing note's path in the log** (`duplicate`, path). Today the log only has the URL.

## I. Config (119-124)

119. **[S] Rename `inbox` to `folder`.** Taste. Skip.
120. **[S] Validate `retries >= 1` and `timeout > 0`.** `retries = 0` makes `with_retries` return `None` and crash later.
121. **[V][S] Comment in `config.example.toml`** says vault basename is the vault name. Becomes false after #51; update.
122. **[S] Allow `LOG`/`RETRY` paths in config?** No. Keep next to the script.
123. **[S] Use XDG paths** (`~/.local/state/yt2obsidian/run.log`). Only if you ever install the tool outside the project folder (PRD says you won't). Skip.
124. **[S] Delete `timeout`/`retries` from config** and make them constants. PRD §7.8 says config "includes" them, but you have never changed them. [PRD] Less to explain in the README.

## J. Logging and observability (125-129)

125. **[S] Log the title and note path** on success. Today the log has URL and outcome only.
126. **[S] Log the elapsed time** per run. PRD success metric is "a few seconds"; nothing measures it.
127. **[S] Rotate or cap `run.log`.** Not needed at hobby volume. Skip.
128. **[S] Make timestamps UTC or include the offset.** Local naive time (:221) is fine for one machine.
129. **[S] Add a `--log` print** (`tail run.log`)? Just use `tail`. Skip.

## K. Tests (130-143)

130. **[S] Add a test for HTML-in-JSON failure** (#2).
131. **[S] Add a test for a missing `config.toml`** (#3).
132. **[S] Add a test for a non-existent vault** (#5).
133. **[S] Add a test for `wl-paste` missing** by patching `subprocess.run` to raise `FileNotFoundError` (#6).
134. **[S] Add a test for Unicode IDs** (#7).
135. **[S] Add a test for the rate-limited message** (#9). Use the real text from `_video.py:4072`.
136. **[S] Add a test for 403 on captions** (#11).
137. **[S] Add a test for accents** after #78.
138. **[S] Add a test for the playlist-with-`v=` URL** (#95).
139. **[S] Tests write to `tempfile.mkdtemp()` and never clean up** (`run_main`, :106). Use `TemporaryDirectory` or delete after. `/tmp` fills slowly.
140. **[S] Tests print a lot** (`Saved stub ...`, `Stopped: 429`). Redirect stdout in `run_main` so the output only shows `ok name`.
141. **[S] Test runner swallows nothing** but stops at the first failure. Fine; keep it. (No pytest dependency, per BUILD_PLAN.)
142. **[S] `raises()` helper** only checks `ValueError`; fine. Keep.
143. **[S] One test that runs `main()` with a real `fetch_track` against a local `http.server`** to cover the HTTP error paths. Overkill; only if #11 bites.

## L. Docs: README, PRD, BUILD_PLAN (144-160)

144. **[S] README: add the 3 prerequisites** (`wl-clipboard`, `libnotify`, Python 3.11+ for `tomllib`). A fresh machine fails at `wl-paste` otherwise.
145. **[S] README: say what a stub is** and that stubs block re-saves (#15).
146. **[S] README: document the exit codes** (0 ok, 1 bad input, 2 stopped; #57).
147. **[S] README: troubleshooting** — no notification, nothing opens, rate-limited, stale yt-dlp. Four bullets.
148. **[S] README: the Hyprland line** uses `<path>` twice. Show a concrete example once.
149. **[S] README: one sentence on "non-ASCII removed from filenames"** so the missing characters are not a surprise.
150. **[M] Delete `BUILD_PLAN.md`.** It says "Written for the builder (Claude)" and is a finished execution log (Phases 0-5 are done). Its decisions are now in the code and git history. Less to maintain. If you want it, move the "Known risks" list into the README.
151. **[S] Trim `PRD.md` §4 "Non-Goals"** — 17 lines of "no X" that restate the goals. Keep the 5 that guard against real scope creep (no AI, no overwrite, no Shorts, no batch, no playlists).
152. **[S] PRD §14 "Open Questions"** — two were decided by BUILD_PLAN (date, stub-on-failure). Move them to "Decided".
153. **[S] PRD §15 "Future Versions"** — mark everything unscheduled, or delete the section. It is a wish list in a requirements doc.
154. **[S] PRD §11 "Success metrics"** and §13 "Risks" are not used by anything. Merge into 3 lines or drop.
155. **[S] PRD §9 "Technical Approach"** says "open-source Python library that reads captions" — it is now yt-dlp. Update.
156. **[S] PRD §7.5** says non-English chars are removed. If you accept #78, update the wording to "accents are folded to ASCII".
157. **[S] PRD and README duplicate** the "no AI, free" line. Keep it in one.
158. **[S] The source docstring points to PRD.md** (:1). Fine; keep.
159. **[S] Comment density.** The code is clean. The `Phase 2` comment (:134) is the only stale one.
160. **[S] BUILD_PLAN "~250 lines, split at ~400"** — you are at 277. No action. Do not split.

## M. Repo hygiene and packaging (161-170)

161. **[S] Add a `LICENSE`** only if you plan to share (PRD: "clean enough to share later"). Otherwise skip.
162. **[S] `requirements.txt` pins nothing.** Pin `yt-dlp` with `>=2026.8` so a clean install is not ancient. Do not pin exactly; you need updates.
163. **[S] `.gitignore`: add `.DS_Store`** — not needed on Linux. Skip.
164. **[S] `.gitignore` is correct** for the files that exist. Add `.pytest_cache/` only if you adopt pytest (you shouldn't).
165. **[S] Commit message style** ("Phase N: ...") is fine. Next ones should drop the phase prefix.
166. **[S] Remove tracked `__pycache__`?** It is ignored and untracked. Nothing to do.
167. **[S] Add `if __name__ == "__main__":` guard** — exists. Good.
168. **[M] Add a `pyproject.toml`?** No. One file, one dependency. Skip.
169. **[S] Add a pre-commit hook that runs the tests.** `.git/hooks/pre-commit` with one line. Tests take well under a second.
170. **[S] Add `ruff`** as a one-off check (`uvx ruff check .`), not a dependency. No linter is installed now, so unused imports (`json`, `os`) would go unnoticed if they became dead.

## N. Security and privacy (171-174)

171. **[S] The vault path comes from config only.** No injection from the URL. Good.
172. **[S] `xdg-open` receives a URI built with `quote(..., safe="")`.** Good; after #51 re-check quoting of the absolute path.
173. **[S] `subprocess` calls use lists, not a shell.** Good. Keep it that way.
174. **[S] The log stores the full clipboard text** when parsing fails. If you copy a password by mistake and run the hotkey, it lands in `run.log`. Truncate to ~200 chars or log only URL-shaped strings. **[V]** `done()` writes `url` verbatim once #12 is applied, so do both together.

## O. Ideas I would not build (175-185)

These came up while auditing. All are scope creep for a one-command tool.

175. **Summaries or key points** (PRD already says no).
176. **A GUI or tray icon.** The hotkey and notification are the UI.
177. **Playlist and channel support.** One video per run keeps failure handling simple.
178. **A database or index of saved videos.** The inbox folder is the database.
179. **A config option for each filename rule.** One rule set is easier to reason about.
180. **Parallel fetches.** One URL per run; nothing to parallelize.
181. **A plugin or hook system.**
182. **Docker or packaging as a system install.** PRD says run from the project folder.
183. **Audio transcription fallback (Whisper).** Heavy dependency, PRD lists it as far future.
184. **Thumbnails or channel avatars.** PRD says no.
185. **Switching to `youtube-transcript-api`.** BUILD_PLAN chose yt-dlp because one call gives metadata and captions. Still the right call.

---

## Suggested order

1. Items 1, 2, 6, 7, 9 (crash and throttle fixes, ~30 min total).
2. Items 46, 47, 48, 51 (hotkey UX, ~15 min).
3. Items 26, 27, 29, 31, 44 (yt-dlp option cleanup, ~15 min, re-run tests after).
4. Items 63, 64, 78, 79 (note quality, ~30 min).
5. Item 14, then decide #55 vs #112 (make the retry list real or delete it).
6. Doc trims: 150-155.

Round 1 count: 185 items (includes ~20 "checked, no action" notes so you can see what was ruled out). Round 2 follows below.

---

# Round 2

New items only (186+). This round I ran things instead of only reading: real fetches into a scratch vault (captioned, no-caption, live, deleted), a dead-network simulation, and a fresh `git clone` following the README. **[V]** items below were observed. Round 1 text is unchanged except #14.

## Round 2: do these first (top 6)

1. Silence yt-dlp's own `ERROR:` stderr output (#187).
2. Do not save junk stubs for deleted or mistyped IDs (#188).
3. Take a lock so a double-tapped hotkey cannot save the same video twice (#221).
4. Truncate long clipboard text in errors, notifications, and the log (#222).
5. Strip `♪` and `[music]` noise, and add paragraph breaks (#191, #192).
6. Tell the README how to rebuild `.venv` after an Arch Python upgrade (#284).

## P. Observed in live runs (186-198)

186. **[V] End-to-end works.** Into a scratch vault: captioned video saved, same video again reported as duplicate, no-caption stub, live-stream stub, and deleted-video stub all written correctly. Runs took 0.7 to 2.1 s.
187. **[V][S] yt-dlp prints `ERROR: ...` to stderr** on top of your own line (seen on the deleted-video run, and 3 times in a row on a dead network). Pass `"logger"` with no-op `debug`/`warning`/`error` methods so only your message prints.
188. **[V][S] Deleted or mistyped ID writes a junk note.** `video-aaaaaaaaaaa.md` with `Title: aaaaaaaaaaa`, `Channel: unknown`, `Date: unknown`. "This video is unavailable" is not in the PRD stub list. Treat it as a failure: log, notify, write no note. (This also changes #16.)
189. **[V][S] Network-down notification is raw yt-dlp text** (`ERROR: [youtube] id: Unable to download API page: [Errno 111] ...`, 200+ chars). Send "Network down, queued for retry" and keep the detail in `run.log`.
190. **[V] Dead network gave up in 6.2 s** (3 tries, connection refused). Good. With real timeouts it is up to 30 s x 3 plus sleeps, about 96 s with no feedback (computed, not measured). Consider `timeout = 15`.
191. **[V][S] Music noise is real.** The Rick Astley transcript starts `[♪♪♪] ♪ We're no strangers to love ♪ ♪ You know...`. Strip `♪` and `[...]` tags (upgrades #64 and #68 from "maybe" to "do").
192. **[V] Transcript is one line.** 2,089 characters here; a 2-hour video is 100k+ in one line. Obsidian's editor is known to slow on very long lines (not measured by me). Paragraph breaks (#63) are higher priority than they looked.
193. **[V] Real json3 events** carry only `tStartMs`, `dDurationMs`, `segs` in this sample (61 events). That is enough for gap-based paragraphing with no new fields.
194. **[V][S] Trailing punctuation survives** in filenames: `10 Hours of Rain Sound ... Meditation, Yoga,.md`. Strip trailing `, ; - _` after the ASCII strip (`strip(" .,;-_")`).
195. **[V][S] yt-dlp `info` has `chapters`** (3 on a test video). When present, use chapter starts as paragraph breaks instead of guessing from pauses. [PRD] if you also want headings; breaks alone are fine.
196. **[V][S] Stub text is lowercased.** Output was `transcript fetch failed: this video is unavailable`. `stub_reason` lowercases the whole message for matching (:143) and then reuses it for display (:151). Keep a lowercase copy for matching only.
197. **[V] You cannot tell manual from auto by URL.** Both kinds of track URL contain `caps=asr`. If you want a `Captions: auto` line, have `pick_track` return which dict (`subtitles` or `automatic_captions`) it used.
198. **[V] `info["duration"]` exists** (213 for the test video). Free to add a `Duration:` line later [PRD].

## Q. Remove or simplify, new (199-220)

199. **[S] Delete `.lower()` after `u.hostname`** (:59). `hostname` is already lowercase.
200. **[S] Strip the URL once.** `get_url` strips (:49, :53) and `parse_url` strips again (:58).
201. **[S] Drop the redundant parentheses** in `if (old := find_existing(...)):` (:250).
202. **[S] Pass ints, not `cfg`,** into `fetch`, `fetch_track`, and `with_retries`. They only use `timeout` or `retries`. Test fakes become `lambda u, t: track`.
203. **[S] Default `argv` to `sys.argv[1:]`** so `get_url` checks `argv[0]` and tests stop passing `[None, url]` (`test_yt2obsidian.py:119`).
204. **[M] Fold the success tail into `done()`.** Lines 268-272 repeat print, log, notify that `done()` already does (:236-241). One path instead of two. Pairs with #48 (always notify).
205. **[S] Replace `BAD_CHARS` plus the ASCII encode/decode** (:25, :157) with one allowlist: after NFKD, `re.sub(r"[^A-Za-z0-9 '(),.&!+=@$%~_-]", "", s)`. One regex, no list of 25 forbidden characters to keep complete, and stray characters like `;` or backticks cannot slip through.
206. **[S] Resolve `HERE`** with `Path(__file__).resolve().parent` (:18). A symlink in `~/.local/bin` would otherwise look for `config.toml` next to the symlink.
207. **[S] Reject a relative `vault`** or resolve it against `HERE`. Hotkey runs start in `$HOME`, so a relative path means a different place than in your terminal.
208. **[S] Move `import tempfile / Path / mock`** to the top of the test file; three functions re-import them (:80-82, :103-105).
209. **[S] `with_retries` returns `None`** if `retries < 1` (falls out of the loop). Validate in `load_config` (#120) or add `raise` after the loop.
210. **[S] `queue_retry` creates the file lazily** but `RETRY.exists()` is checked first (:225). `RETRY.touch()`-free approach: `open("a+")`, read, append. One open instead of two.
211. **[S] `log_run`/`queue_retry` can raise** (disk full) and mask the real outcome. Wrap both in `try/except OSError: pass` or let #1's catch-all handle it.
212. **[S] `open_obsidian` `Popen`** is not in a `try` (:216). Missing `xdg-open` raises after the note is already saved and logged. Wrap like `notify`.
213. **[S] Duplicate path in `done()` returns 0** for "failed" parse cases? No: parse errors return 1. Fine. Closed.
214. **[S] Use `ydl.urlopen`** for the caption fetch (see #44). Extra reason: `urllib` sends `Python-urllib` as User-Agent, which YouTube may block later.
215. **[S] `fetch()` rebuilds the watch URL** (:82) while `info["webpage_url"]` is available. Not worth changing; keep the single `watch_url(vid)` helper from #39.
216. **[S] `Throttled` docstring** is three claims in one line. Shorten to "Stop the run and queue the URL."
217. **[S] The three constants `RESTRICTED`, `LIVE`, `NO_CAPS`** are fine. Leave them.
218. **[S] Module header comment** (:134-140) mixes findings and a to-do. After this round it can be replaced by the real values (see #33, #34).
219. **[S] Remove `quiet` once `logger` is set** (#187). The logger replaces it.
220. **[S] `raise` bare after the string checks** in `fetch` (:86) is fine. Closed.

## R. Hotkey, concurrency, environment (221-235)

221. **[S] Double-tap race** (from reading the code, not reproduced). Two overlapping runs both pass `find_existing` and write `Title.md` and `Title (2).md` for one video. Add `fcntl.flock` on a lock file in `HERE` at the top of `main`; the second run waits, then reports a duplicate. About 4 lines. Real risk because the first 1-2 s have no feedback.
222. **[V][S] Clipboard often holds non-URL text.** It held a long paragraph when I tested `wl-paste`. The error `not a YouTube URL: '<whole paste>'` then goes to the toast and the log. Cut to `s[:60]`.
223. **[S] `wl-paste --type text`** (or `-t text`) so an image on the clipboard does not stream bytes into Python.
224. **[S] Add a `--primary` fallback** for selected text? No. Closed.
225. **[unverified][S] Check how other Omarchy binds launch commands** (`uwsm app --`?) and match it, so the process gets the same environment as other apps.
226. **[V] `.venv/bin/python` is a symlink to `/usr/bin/python`** (3.14). On a rolling Arch upgrade to 3.15 the venv's `site-packages/python3.14` stops matching and the tool dies. Add the rebuild command to the README (#284).
227. **[V][S] PATH differs between terminal and bind.** `node` lives in `~/.local/share/mise/...` (shims). A Hyprland `exec` may not have that PATH. yt-dlp accepts `deno` and `node` as JS runtimes (`/usr/bin/deno` exists system-wide). If a video needs a JS runtime, it will work in the terminal and fail from the bind. Test once from the actual bind.
228. **[S] Set `js_runtimes`** explicitly in the yt-dlp options to the system `deno` path, so the bind does not depend on PATH. Only if #227 bites.
229. **[S] Cold-start Obsidian** may take several seconds; the note is already saved, so nothing to fix. Closed.
230. **[S] Exit code on duplicate** is 0. Fine. Closed.
231. **[S] No `--help`/argparse.** PRD says no polished help. Closed (see section W).
232. **[S] `notify-send` actions** (click to open) need the process to wait. Skip; Obsidian opens anyway.
233. **[S] Progress toast for slow runs.** One extra toast per run. Skip.
234. **[S] Run from any cwd.** Already true (paths use `HERE`), except relative `vault` (#207).
235. **[S] Quote paths in the README bind** if the project path has spaces.

## S. Note format and content (236-246)

236. **[PRD][S] `Captions: manual` or `auto` line.** Helps you know how much to trust the text (#197).
237. **[PRD][S] `Duration:` line** (#198). Taste.
238. **[S] Stub `Title:` shows the raw ID** when yt-dlp has no title (verified). Moot after #188; otherwise print `unknown`.
239. **[S] Split paragraphs on `>>`** (speaker change in manual captions) instead of deleting it. Pairs with #63.
240. **[S] Break on `tStartMs` gaps > 2 s,** or on chapter starts (#195). Whichever is present.
241. **[S] Cap paragraph length** (~600 chars) so a track with no pauses still gets breaks. Split at the next sentence end or space.
242. **[S] Auto captions have no punctuation or casing.** Nothing to do without a model; PRD says no AI. Closed.
243. **[S] Save a `Language:` line?** Not needed; English only.
244. **[S] Stub note links.** Stub is `[YouTube](url)`; the full-note link text is the title. Consistent enough. Closed.
245. **[S] Trailing newline** is present. Closed.
246. **[S] Do not add frontmatter, tags, or wikilinks.** PRD forbids; listed so no one adds `[[channel]]`.

## T. Filenames, new (247-252)

247. **[S] Allowlist regex** (#205) replaces the denylist.
248. **[S] Titles that already end in `(2)`** become `Part (2) (2).md` on a clash. Harmless.
249. **[S] Titles that reduce to punctuation only** fall back to `video-<id>`. Fine.
250. **[S] A stub and a later real note with the same title** get `(2)`. Fine.
251. **[S] Unicode NFKD can turn `ﬁ` into `fi`** and `²` into `2`. Good side effect of #78.
252. **[S] Keep `&`** in names; Obsidian allows it. The allowlist in #205 includes it.

## U. Tests, new (253-270)

253. **[S] Commit one real captured track as a fixture** (trim to ~10 events). A 61-event real json3 sample is saved at `/tmp/claude-1000/-home-sy-Documents-Code-auto-ai-yt-summaries/8c5871d9-924a-45be-8865-bfcf722435df/scratchpad/t.json` (session scratch; copy it before it is cleaned). Synthetic tracks miss real quirks like `♪`.
254. **[S] Commit one real `info` subset** (`availability`, `live_status`, `age_limit`, caption keys). BUILD_PLAN Phase 2 asked for real values; today `stub_reason` tests use hand-built dicts.
255. **[S] Test `queue_retry` does not append the same URL twice.**
256. **[S] Test that a non-network `DownloadError`** ("Video unavailable") passes `with_retries` after one call.
257. **[S] Test `fetch()`** maps 429, "not a bot", and "rate-limited" to `Throttled` by patching `yt_dlp.YoutubeDL`. `run_main` replaces `fetch` entirely, so `fetch` itself has no test.
258. **[S] Test `fetch_track` 429** by patching `urllib.request.urlopen` (or `ydl.urlopen` after #44).
259. **[S] Test `load_config`** defaults and `~` expansion with a temp `config.toml` (patch `HERE`).
260. **[S] Test `get_url`** for clipboard happy path, empty clipboard, and missing `wl-paste` (patch `subprocess.run`).
261. **[S] Test `open_obsidian`** builds the right URI for a vault path with spaces (patch `Popen`).
262. **[S] Test `notify`** swallows a missing binary (patch `run` to raise `FileNotFoundError`).
263. **[S] Test `render`** with a malformed `upload_date` like `"2024"` gives `Date: unknown`.
264. **[S] Test an empty-text track** (`events` all empty) gives the no-captions stub, not an empty note.
265. **[S] Test "too many name clashes"** once the cap is 99 (#8): create 99 files, expect `OSError`.
266. **[S] Test `find_existing`** with CRLF or BOM on line 1.
267. **[S] Test runner prints a summary** (`11 passed`) and exits non-zero on failure. Today it stops at the first assert with a traceback.
268. **[V] Fresh clone check:** `git clone`, `python -m venv`, `pip install -r requirements.txt`, copy config, run tests: 11 tests ok. README steps work as written.
269. **[S] Silence test output** (`Saved stub ...`, `Stopped: ...` lines). Patch `builtins.print` in `run_main` (also in #140).
270. **[S] Add one slow, opt-in live test** (`python test_yt2obsidian.py --live`) that fetches a known captioned video in ~2 s. Useful as a canary after `pip install -U yt-dlp`. Skip if #283's README line is enough.

## V. Docs and repo, new (271-284)

271. **[S] Rename the folder and repo** `auto-ai-yt-summaries` to `yt2obsidian`. The tool does no AI and no summaries, and everything else is already named `yt2obsidian`.
272. **[S] README: state the tested versions** (yt-dlp 2026.8.19, Python 3.14). A future breakage is then easy to attribute.
273. **[S] README: minimum Python is 3.11** (`tomllib`).
274. **[S] `git tag v1`** once the top fixes land. A cheap restore point before the next yt-dlp upgrade.
275. **[S] Treat `IMPROVEMENTS.md` as a working list.** Move finished items to a `Done` heading or delete the file when empty; otherwise it rots.
276. **[S] `config.example.toml`:** mark `timeout` and `retries` as optional.
277. **[S] PRD §7.5 contradicts itself:** "not truncated" and "capped". Rewrite as "capped at 255 bytes (or your chosen shorter limit, #77)".
278. **[S] PRD §5 says "clean enough to share later".** If you do share: README must say Wayland-only and Obsidian URI scheme required.
279. **[S] BUILD_PLAN Phase 5 "fresh clone-style run"** is now done (#268). Tick it or delete the file (#150).
280. **[S] README: add "what to do when it stops working"** in this order: update yt-dlp, rebuild `.venv`, check `run.log`.
281. **[S] README: link `run.log` fields** (time, URL, outcome, detail; tab-separated) so it can be grepped.
282. **[S] README: mention `retry.txt`** only if #55 gets built; otherwise remove the line along with the feature.
283. **[S] README canary line:** after upgrading yt-dlp run `.venv/bin/python yt2obsidian.py https://youtu.be/dQw4w9WgXcQ` and check the note appears. No code needed.
284. **[V][S] README: rebuild the venv after an Arch Python upgrade:** `rm -rf .venv && python -m venv .venv && .venv/bin/pip install -r requirements.txt` (#226).

## W. Things I would still not build, new (285-300)

285. `argparse` or `--help` text. One optional URL argument does not need it.
286. The `logging` module. A tab-separated `run.log` is greppable and 3 lines.
287. Type hints and mypy.
288. A `Config` dataclass or pydantic model.
289. `asyncio` or threads.
290. Caching yt-dlp `info` on disk.
291. `tenacity` or another retry library; `with_retries` is 12 lines.
292. A `--watch-clipboard` daemon. The PRD says no background service.
293. Non-English captions or translation (PRD).
294. A local model to add punctuation to auto captions (PRD: no AI).
295. An Obsidian plugin that calls this tool.
296. A web UI or share target for the phone (PRD: desktop only).
297. Splitting `yt2obsidian.py` into modules. 277 lines.
298. A Makefile or `justfile` for five commands.
299. CI. One user, one machine, tests run in a second.
300. Auto-updating yt-dlp on a schedule (PRD non-goal).

---

Round 2 count: 115 new items (186-300). Total 300 including ~35 "checked, no action" and "do not build" entries.
