# yt2obsidian

Copy a YouTube link, run one command, get a plain-text transcript note in your Obsidian vault. Free, no AI. See `PRD.md`.

```
python -m venv .venv && .venv/bin/pip install -r requirements.txt
cp config.example.toml config.toml        # set vault + inbox
.venv/bin/python yt2obsidian.py           # in a terminal: the prompt; from a hotkey: reads the clipboard
.venv/bin/python yt2obsidian.py <url>     # or pass it
.venv/bin/python test_yt2obsidian.py      # tests
```

Interactive prompt: `./yt` (paste links one at a time; paste several links, one per line, to save them all; `?` lists commands: `o` open last note, `l` list recent, `r` retry `retry.txt`, `undo` delete the last note, `u` update yt-dlp, `s` settings, `q` quit). `./yt <url>` saves one link. Settings (`s`, or `yt2obsidian.py --settings` on its own): number toggles open-in-Obsidian and notifications, `d` resets them to the defaults (on), Enter/`q`/`b` goes back. Changes apply to the next paste and are written to `config.toml` (comments kept). Unknown keys in `config.toml` are reported, not used. Put it on your PATH: `ln -s "$PWD/yt" ~/.local/bin/yt`.

Hyprland keybind: `bind = SUPER, Y, exec, <path>/.venv/bin/python <path>/yt2obsidian.py`

- Logs every run to `run.log`; throttled/network-failed URLs go to `retry.txt`.
- If it suddenly stops working, update yt-dlp first: `.venv/bin/pip install -U yt-dlp`.
