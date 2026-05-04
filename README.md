# Voiext (VoiceType)

Offline voice-to-text app for Windows and Linux. Dictate text, control your desktop, and navigate your computer — all with your voice.

- **Author on GitHub:** [github.com/jbmustaq](https://github.com/jbmustaq)

---

## Features

### Voice Dictation

Speak naturally and your words are typed into the active application. Only final confirmed text is typed — no wrong-then-right duplication or slow backspacing.

- **Auto-correct** — misspelled words are fixed automatically using a spell checker
- **Number conversion** — say "twenty five" and get `25`, say "one two three" and get `123`, say "third" and get `3rd`
- **Garbage filtering** — filler sounds like "uh", "hmm", "um" are ignored

### Two Modes

| Mode | What happens when you speak |
|------|-----------------------------|
| **Command** | Voice controls your desktop — opens apps, presses shortcuts, manages media |
| **Dictation** | Voice types text into the active application |

Switch modes by saying **"type"** or **"command mode"**, or use the GUI / `Ctrl+Shift+C`.

### Sentence Autocomplete

When you pause while dictating, VoiceType predicts the rest of your sentence:

1. **N-gram (instant)** — learns your common phrases from dictation history. If you've typed "thank you very much" several times, it will suggest it after you say "thank you"
2. **DistilGPT-2 (smart)** — a small offline language model that generates full sentence completions for phrases you haven't said before

Predictions appear as `suggest: "..."` in the GUI. Say **"yes"**, **"okay"**, or **"approve"** to accept, or just keep talking to discard.

Toggle this feature on/off with the **"Sentence autocomplete"** checkbox.

### Desktop Commands (Command Mode)

**Open applications:**

| Say this | Opens |
|----------|-------|
| "open browser" | Default web browser |
| "open chrome" | Google Chrome |
| "open notepad" | Notepad |
| "open calculator" | Calculator |
| "open file explorer" / "open explorer" | File Explorer |
| "open settings" | Windows Settings |
| "open command prompt" / "open terminal" | Command Prompt |
| "open task manager" | Task Manager |
| "open paint" | MS Paint |
| "open snipping tool" | Snipping Tool |
| "open word" | Microsoft Word |
| "open excel" | Microsoft Excel |
| "open powerpoint" | Microsoft PowerPoint |
| "open V S code" / "open visual studio code" | VS Code |

**Open any installed app** — say "open" followed by the app name (e.g. "open spotify", "open discord", "open vlc"). VoiceType will search your PATH, Windows App Paths registry, and registered app names to find and launch it.

**Open folders:**

| Say this | Opens |
|----------|-------|
| "open downloads" | Downloads folder |
| "open documents" | Documents folder |
| "open desktop" | Desktop folder |
| "open pictures" | Pictures folder |
| "open videos" | Videos folder |
| "open music" | Music folder |
| "open C drive" | C:\ |
| "open D drive" | D:\ (if present) |

**Navigate to URLs:**

| Say this | What happens |
|----------|--------------|
| "go to google dot com" | Opens https://google.com |
| "go to youtube" | Opens https://youtube.com (if in URL shortcuts) |
| "open servermania" | Opens https://servermania.com (custom shortcut) |

You can add your own URL shortcuts by editing the `URL_SHORTCUTS` dictionary in `voice_type.py`.

**Media and volume:**

| Say this | Action |
|----------|--------|
| "volume up" | Increase volume |
| "volume down" | Decrease volume |
| "mute" | Toggle mute |
| "play pause" | Play / Pause media |
| "next track" | Next track |
| "previous track" | Previous track |

### Keyboard Shortcuts by Voice

| Say this | Keys pressed |
|----------|--------------|
| "copy" | Ctrl+C |
| "paste" | Ctrl+V |
| "cut" | Ctrl+X |
| "undo" | Ctrl+Z |
| "redo" | Ctrl+Y |
| "select all" | Ctrl+A |
| "find" | Ctrl+F |
| "find next" | F3 |
| "go to line" | Ctrl+G |
| "bold" | Ctrl+B |
| "italic" | Ctrl+I |
| "underline" | Ctrl+U |
| "save" | Ctrl+S |
| "new file" | Ctrl+N |
| "new line" / "enter" | Enter |
| "tab" | Tab |
| "backspace" | Backspace |
| "delete" | Delete |
| "home" | Home |
| "end" | End |
| "switch" | Alt+Tab |
| "page up" | Page Up |
| "page down" | Page Down |
| "up" / "down" / "left" / "right" | Arrow keys |
| "close tab" | Ctrl+W |
| "close" | Alt+F4 |

### Mouse Control

Requires `pyautogui` (included in requirements.txt).

| Say this | Action |
|----------|--------|
| "click" / "left click" | Left click |
| "right click" | Right click |
| "double click" | Double click |
| "middle click" | Middle click |
| "scroll up" | Scroll up |
| "scroll down" | Scroll down |

### Screen Reading

Requires `pytesseract` and the [Tesseract OCR engine](https://github.com/UB-Mannheim/tesseract/wiki). Optional — VoiceType works fine without it.

| Say this | Action |
|----------|--------|
| "click on [text]" | Finds text on screen, moves mouse, clicks it |
| "move to [text]" | Finds text on screen, moves mouse to it |
| "analyze screen" / "scan screen" | Reads all visible text on screen and shows it in the log |

### Voice Control Phrases

These work regardless of which mode you're in:

| Say this | Action |
|----------|--------|
| "stop" / "stop listening" | Stop listening |
| "go to sleep" / "sleep" / "pause" | Enter sleep mode (stops processing speech) |
| "wake up" / "resume" / "start listening" | Wake up from sleep |
| "type" / "start typing" / "dictate" | Switch to Dictation mode |
| "command mode" / "stop typing" | Switch to Command mode |

### System Tray and Hotkeys

- **System tray icon** — color changes based on state (red=idle, green=dictating, blue=command, yellow=sleeping)
- **Minimize to tray** — window auto-minimizes when idle; right-click tray icon to show/quit
- **`Ctrl+Shift+V`** — start / stop listening
- **`Ctrl+Shift+C`** — switch between Command and Dictation mode
- **Auto-sleep** — stops listening after 60 seconds of silence

### GUI Settings

- **Speech model selector** — switch between English GigaSpeech and Indian English models
- **Mic gain slider** — boost microphone input (1x to 5x)
- **Start on boot** — adds a startup shortcut (Windows only)
- **Auto-start on open** — starts listening automatically when the app opens
- **Sentence autocomplete** — toggle N-gram + DistilGPT-2 predictions

---

## Quick Start

### Prerequisites

- [Python 3.9+](https://www.python.org/downloads/) (check "Add Python to PATH" on Windows)
- A working microphone

### Install and Run

```bash
pip install -r requirements.txt
python voice_type.py
```

On first run, the app will download the **English GigaSpeech** speech model (~500 MB) if it is missing. The autocomplete model (DistilGPT-2, ~350 MB) downloads lazily on first use.

### Optional: Tesseract OCR (for screen reading)

1. Download the installer from [UB-Mannheim Tesseract](https://github.com/UB-Mannheim/tesseract/wiki)
2. Install it, then verify: `tesseract --version`

### Usage Examples

**Example 1: Dictate an email**

```
[Press Ctrl+Shift+V to start]
"hey john"          → types: hey john
"thank you very much"  → types: thank you very much
"command mode"      → switches to command mode
"send"             → presses Ctrl+S (if configured)
[Press Ctrl+Shift+V to stop]
```

**Example 2: Navigate your computer**

```
[Press Ctrl+Shift+V to start]
"open chrome"       → launches Google Chrome
"go to servermania dot com"  → opens servermania.com
"close tab"         → closes current browser tab (Ctrl+W)
"open downloads"    → opens Downloads folder
```

**Example 3: Use autocomplete**

```
[Dictate for a while to build N-gram history]
"thank you"         → pause 1.5s
                    → suggestion appears: "very much"
"okay"              → types: very much
```

**Example 4: Mouse and screen reading**

```
"click on save"     → finds "Save" button on screen, clicks it
"analyze screen"    → reads all text on screen into the log
"scroll down"       → scrolls down
```

---

## Customization

### Add URL Shortcuts

Edit the `URL_SHORTCUTS` dictionary in `voice_type.py`:

```python
URL_SHORTCUTS = {
    "servermania": "https://servermania.com",
    "google": "https://google.com",
    "youtube": "https://youtube.com",
    # Add your own:
    "my site": "https://example.com",
    "github": "https://github.com",
}
```

Vosk may mishear words — add variations (e.g. "server mania", "serve a mania") so the URL still opens.

### Add Desktop Commands

Edit the `DESKTOP_COMMANDS` and `APP_LAUNCHERS` dictionaries in `voice_type.py` to add new apps or commands.

### Adjust Autocomplete Behavior

Edit these constants in `voice_type.py`:

| Constant | Default | What it controls |
|----------|---------|-------------------|
| `PREDICTION_SILENCE_SECONDS` | 1.5 | Seconds of silence before a prediction is triggered |
| `NGRAM_MIN_FREQ` | 3 | How many times a phrase must appear before N-gram suggests it |
| `NGRAM_ORDER` | 3 | Trigram model (3-word sequences) |
| `PREDICTION_MAX_TOKENS` | 20 | Max length of GPT-2 completions |

---

## Configuration

Settings are saved to `voicetype_config.json` (next to the script or executable):

```json
{
  "model_preset": "en_giga",
  "mic_gain": 1.0,
  "auto_start": false,
  "autocomplete_enabled": true
}
```

---

## Build a Windows Zip (Optional)

From the project root, in PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_windows.ps1
```

Then attach `dist\VoiceType-Windows-models.zip` to a GitHub Release.

---

## License

Add a `LICENSE` file when you choose one (MIT is common for small open-source apps).