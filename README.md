# yt2obsidian

Copy a YouTube link, run one command, get a plain-text transcript note in your Obsidian vault. Free, no AI. See `PRD.md`.

```
python -m venv .venv && .venv/bin/pip install -r requirements.txt
cp config.example.toml config.toml        # set vault + inbox
.venv/bin/python yt2obsidian.py           # reads the URL from the clipboard
.venv/bin/python yt2obsidian.py <url>     # or pass it
.venv/bin/python test_yt2obsidian.py      # tests
```

Hyprland keybind: `bind = SUPER, Y, exec, <path>/.venv/bin/python <path>/yt2obsidian.py`

- Logs every run to `run.log`; throttled/network-failed URLs go to `retry.txt`.
- If it suddenly stops working, update yt-dlp first: `.venv/bin/pip install -U yt-dlp`.
