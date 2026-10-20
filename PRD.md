PRD: Video-to-Obsidian Transcript Pipeline
1. Overview

This tool turns a YouTube video into a plain-text transcript note inside a personal Obsidian vault. The user copies a YouTube link, runs the tool, and gets a markdown note in an inbox folder that syncs through Obsidian Sync to every device where Obsidian runs. The tool is free to use. It uses no paid APIs and no AI summarization in v1.

The original idea was a pipeline that pulls the transcript, writes timestamped key points, and links to related notes. After discussion, v1 was scoped down to the core job: reliable transcript capture written into Obsidian with a predictable file name and layout. Timestamps, key points, and related-note linking are deferred.

2. Problem Statement

The user watches YouTube videos worth keeping and wants them preserved as searchable, readable notes in their existing knowledge base. Copying transcripts by hand is slow. Existing ways of getting them into Obsidian either need paid services or produce notes with inconsistent names and formats. The user wants a single repeatable action: copy a link, run one command, and find the note in the vault.

3. Goals
Turn a single YouTube URL into a markdown note containing the full transcript, in one step.
Keep the cost at zero: no paid APIs, no paid services, no subscription AI.
Produce notes whose filenames match the video title, so they are easy to find and open in Obsidian.
Make the output work with Obsidian Sync, so the note appears on the laptop and phone without extra steps.
Be easy to build and maintain as a personal hobby project.
4. Non-Goals
No AI summaries, key-point extraction, or any language model use.
No overwriting of existing notes, ever.
No YouTube Shorts handling. Shorts are skipped.
No playlist or channel processing. Single videos only (several links may be pasted at once; each is saved on its own).
No sponsor or ad segment removal.
Also out of scope: timestamps, related-note links and tags, thumbnails, an index page, a mobile trigger, auto-update (manual only), and a background service.

5. Users

The only user is the author, who is the sole owner of the vault. The tool is a personal script, not a product. It does not need to be installable by others, although it should be clean enough to share later if wanted. The user runs Arch Linux with the Omarchy setup, which uses Hyprland and Wayland. They use Obsidian daily and pay for Obsidian Sync, so the vault is available on a phone, a laptop, and any other device with Obsidian installed.

6. User Workflow
The user watches a YouTube video they want to keep and copies the link.
The user runs `yt` in a terminal and pastes the link at the prompt (Enter alone pastes the clipboard). The command can also take the URL as an argument, and a Hyprland hotkey can run it with no terminal, in which case it reads the clipboard.
The tool validates the URL, fetches metadata, fetches the transcript, and writes a note.
The tool prints the path and title of the new note. Hotkey runs show a desktop notification instead of relying on the terminal.
The tool opens the new note in Obsidian through an Obsidian URI (can be turned off in settings).
Obsidian Sync carries the file to the other devices.

If the video cannot produce a transcript, the tool still writes a stub note so the user knows the video was processed and why it has no transcript.

7. Functional Requirements
7.1 Input
Accept a YouTube URL from the clipboard by default.
Accept a URL as a single command-line argument as an alternative.
Accept these URL forms: standard watch links (youtube.com/watch?v=...), short links (youtu.be/...), and links with extra query parameters such as timestamps or tracking tags. The tool should accept as many YouTube URL forms as practical.
Reject YouTube Shorts URLs by skipping them with a clear message. Shorts are not processed.
Several links in one paste (one per line or space-separated) are each processed in turn.
7.2 Transcript Retrieval
Retrieve transcripts from YouTube captions only. No audio transcription in v1.
Accept English captions only. Any English variant counts, including en, en-US, and en-GB.
Accept both auto-generated and manually created captions.
If multiple English tracks exist, prefer manual over auto-generated, since that is the most accurate result.
Output the full transcript. No truncation.
Output the transcript as plain text. No timestamps. No line-per-caption formatting. Captions should be joined into readable text. Light cleanup such as fixing repeated spacing is acceptable, but the user is fine with raw output.
Do not apply sponsor removal, grammar correction, or summarization.
7.3 Metadata
Retrieve the video title, channel name, and publish or relevant date from whatever the transcript library exposes. No separate paid or keyed API.
Date format in the note is YYYY-MM-DD.
Channel and date each appear on their own line below the URL.
7.4 Note Content and Layout

The note body is in this order:

The YouTube URL as a markdown link. The link text is the video title or a short label, and the target is the full YouTube URL.
A line with the channel name.
A line with the upload date.
A `Duration:` line (h:mm:ss or m:ss), left out when YouTube gives none (live, upcoming).
A `Saved:` line with the date the note was written.
The full transcript as plain text.

The note has no YAML frontmatter block. It has no H1 heading. The video title is only in the filename.

For a stub note (no transcript available), the note includes:

The YouTube URL as a markdown link.
The original title.
The channel name and date.
A line stating the reason there is no transcript, such as “no captions available,” “live stream or premiere, not finished,” or “video is private, members-only, or age-restricted.”

No thumbnail or attachment is saved.

7.5 Filename
The filename is the video title with characters Obsidian and common filesystems reject removed. Examples of characters to strip include the forward slash, backslash, colon, asterisk, question mark, double quote, angle brackets, and pipe.
Accents are folded to plain letters (Café becomes Cafe), curly quotes and dashes become ASCII, and anything outside a short ASCII allowlist is removed. Trailing punctuation is stripped. A title with no usable characters becomes “<channel> video-<id>”.
Spaces are kept.
Filenames are capped to stay under the common 255-byte filesystem limit (room is left for ".md" and a " (99)" suffix). The cap is the only length restriction.
The filename ends in .md.
If a file with the same name already exists and belongs to a different video, append a number, for example “Title (2).md.”
7.6 Duplicate Handling
Before writing, check whether a note for the same video already exists in the target folder or any subfolder of it. Determine this by the video ID recorded in the note’s URL (a `watch?v=` or `youtu.be/` link in the first 1 KB).
If a duplicate exists, skip writing and report that the video was already saved. Do not overwrite.
Existing notes are never overwritten under any circumstances.
7.7 Output Location
The inbox folder is a single fixed folder inside the user’s Obsidian vault. It is set in a configuration file. Any subfolder of the vault is valid, for example “Inbox” or a deeper path.
The tool creates the inbox folder automatically if it does not yet exist.
Only one vault is supported in v1.
Writes use a temporary file followed by a rename, so an interrupted run does not leave a half-written note.
7.8 Configuration
Configuration lives in a small file, such as JSON or TOML. Format is left to the implementer.
Configuration includes at minimum the vault path and the inbox folder path relative to the vault.
Configuration also includes the transcript fetch timeout and the retry count, although these have sensible defaults.
No environment variables are required.
7.9 Feedback and Notifications
After a successful save, the tool prints the full path of the new note to the terminal.
After a successful save, the tool sends a desktop notification.
The tool opens the new note in Obsidian through an Obsidian URI after saving.
On failure, the tool prints a clear error message to the terminal and sends a desktop notification where it can.
The tool keeps a log file that records each run, including the URL, the outcome, and any error.
7.10 Error Handling and Retries
Network requests are retried 2 to 3 times on failure.
Transcript fetching has a time limit so a stuck request does not hang the run.
If YouTube throttles a request or blocks it, the run stops immediately.
When a run stops, failed or unprocessed videos are recorded in a retry list file so they can be processed later, and the user is notified which ones failed.
Both the retry list file and the desktop notification are used to report failures.
Restricted videos (private, members-only, age-restricted) receive a stub note, not an error.
Live streams and upcoming premieres receive a stub note stating that the transcript is not yet available.
8. Non-Functional Requirements
Cost: the tool must run without any paid service or API key.
Platform: Arch Linux on Omarchy with Hyprland and Wayland. The tool does not need to run on macOS or Windows in v1.
Language: Python is the chosen implementation language. The user left the choice to the implementer, and Python has mature transcript libraries.
Dependencies: Python dependencies are isolated in a virtualenv.
Installation: the tool is run from its project folder. It is not installed into the system path in v1.
Reliability: failed runs must not corrupt the vault. Writes are atomic. Overwrites never happen.
Maintainability: this is a hobby project. Code should be readable and reasonably commented, but does not need polished CLI help text or extensive documentation.
Privacy: the tool sends only the YouTube URL and transcript requests to YouTube. No other data leaves the machine.
9. Technical Approach
Python script with a small command-line interface.
Clipboard reading uses wl-paste on Wayland.
Desktop notifications use notify-send.
Metadata and caption retrieval use the yt-dlp Python library (one call returns both). No AI model is involved.
Obsidian integration works by writing markdown files into the vault folder. Opening the note uses an Obsidian URI.
The vault folder is a normal folder on the local disk. Obsidian Sync handles propagation to other devices.
Optional: a Hyprland keybinding that runs the tool with the clipboard as input.
10. Testing

Testing is basic, matching the hobby scope. The PRD requires testing against these cases:

A standard public video with English captions. Expected: a complete note with the URL, channel, date, and full transcript.
A video with no captions. Expected: a stub note with the reason stated.
A private or members-only video. Expected: a stub note with the reason stated.
A live stream or upcoming premiere. Expected: a stub note stating the transcript is not yet available.
A video with a non-English title. Expected: a filename with non-English characters removed.
A video with emoji in the title. Expected: a filename with emoji removed.
A duplicate link. Expected: no new file, a message that the video was already saved.
A YouTube Shorts link. Expected: skipped with a message.
A simulated throttle or network timeout. Expected: the run stops, the retry list file records the failed video, and a notification is sent.

Success for v1 means most captioned videos produce a correct note on the first try.

11. Success and Risks
Success: most videos with English captions produce a note with the correct filename and full transcript within a few seconds, and the user keeps using the tool instead of hand-copying transcripts.
Risks: YouTube changes caption access or throttles heavy use (the tool stops and queues the URL; the fix is usually updating yt-dlp), and long titles hit the filename limit (capped). The tool only creates new files, so Obsidian Sync conflicts are unlikely and not handled.
Depends on yt-dlp being maintained, Obsidian Sync for propagation, and the machine being on during a run.

12. Future Versions (unscheduled)
Timestamped key points and short summaries, links to related notes, audio transcription for videos without captions, a mobile trigger, and an index page of saved transcripts.
