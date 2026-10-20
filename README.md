# yt2obsidian

Paste a YouTube link, get a plain-text transcript note in your Obsidian vault. Free, no AI. See `PRD.md`.

Wayland only (uses `wl-paste`). Tested with yt-dlp 2026.8.19 and Python 3.14 on Arch (Omarchy); if it breaks later, those are the versions that worked.

## Prerequisites

- Python 3.11 or newer (`tomllib`)
- `wl-clipboard` (`wl-paste`), `libnotify` (`notify-send`), `xdg-utils` (`xdg-open`)
- Obsidian, with `obsidian://` links handled by it
- A JavaScript runtime that yt-dlp can find (`node` or `deno`); a hotkey may have a shorter `PATH` than your terminal

## Setup

```
python -m venv .venv && .venv/bin/pip install -r requirements.txt
cp config.example.toml config.toml        # set vault + inbox
.venv/bin/python test_yt2obsidian.py      # tests; add --live for one real YouTube fetch
ln -s "$PWD/yt" ~/.local/bin/yt           # optional: run it as `yt`
```

## Use

- `yt` in a terminal opens the prompt. Paste a link and press Enter (Enter alone pastes the clipboard). Several links, one per line or space-separated, are saved in turn. `?` lists the commands: `o` open the last note, `l` list recent, `r` retry `retry.txt`, `undo` delete the last note, `u` update yt-dlp, `s` settings, `q` quit.
- `yt <url>` saves one link. `yt --retry` saves the links in `retry.txt`. `--no-open` skips Obsidian and `--no-notify` skips toasts for that run.
- With no terminal (a hotkey) it reads the clipboard and shows the result as a toast. Hyprland: `bind = SUPER, Y, exec, ~/.local/bin/yt` (after the `ln -s` above; or `exec, "/path/to/project/yt"`, quoted if the path has spaces).
- Settings (`s`, or `yt --settings`): open in Obsidian, notifications (`auto` = toast only for hotkey runs, `always`, `never`), inbox folder, fetch timeout, attempts per fetch. `d` resets all but the inbox. Changes apply to the next paste and are written to `config.toml` with comments kept. Unknown keys in `config.toml` are reported, not used.
- Output is colored in a terminal (status word green/yellow/red, warnings yellow). Set `NO_COLOR=1` to turn it off.
- Exit codes: 0 ok (saved, stub, duplicate, skipped), 1 bad input or failure, 2 stopped (throttled or network down; the URL is queued in `retry.txt`).
- Two runs at once take turns, so a double-tapped hotkey reports the second as a duplicate.

## Notes it writes

- The filename is the video title with accents folded (`Café` becomes `Cafe`) and anything outside a short ASCII set removed, so titles in other scripts fall back to `<channel> video-<id>`. Layout is in `PRD.md` §7.4.
- A **stub** is a note for a video with no transcript (no captions, live or upcoming, private, members-only, age-restricted). It says why. A stub counts as saved, so pasting the same link again reports a duplicate; delete the stub to try again.
- A video already in the inbox (any subfolder) is never saved twice, and existing notes are never overwritten.

## Logs

`run.log` is tab-separated, one row per run: time, URL, outcome (`saved`, `stub`, `duplicate`, `skipped`, `failed`, `cancelled`, `undone`), detail (note path, or the error with its type and the yt-dlp version), title, seconds, source (`repl`, `argv`, `clipboard`, `retry`). Older rows have fewer columns. It is a watch history, so it is owner-only and gitignored. Count outcomes: `cut -f3 run.log | sort | uniq -c`. Throttled or network-failed URLs go to `retry.txt`.

## Troubleshooting

- **No notification:** `notify` may be `auto` (prompt runs do not toast) or `never`; check `s`. Also check a notification daemon is running.
- **Note saved but Obsidian did not open:** `open_obsidian` is off (`s`), or `xdg-open` does not know `obsidian://`.
- **"throttled by YouTube":** wait up to an hour, then `r` (or `yt --retry`).
- **Failures with "Unable to extract" or "nsig":** yt-dlp is stale, see below.

## When it stops working

1. Update yt-dlp: press `u` in the prompt, or `.venv/bin/pip install -U yt-dlp`.
2. After an Arch Python upgrade `.venv` breaks (`.venv/bin/python` points at `/usr/bin/python`): `rm -rf .venv && python -m venv .venv && .venv/bin/pip install -r requirements.txt`.
3. Read the last rows of `run.log`.

Canary after upgrading yt-dlp: `yt https://youtu.be/dQw4w9WgXcQ` should save a note (or `.venv/bin/python test_yt2obsidian.py --live`).
