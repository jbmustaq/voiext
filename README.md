# Voiext (VoiceType)

Offline voice-to-text for Windows and Linux using [Vosk](https://alphacephei.com/vosk/). Dictate with a small GUI, system tray, and hotkeys (`Ctrl+Shift+V` start/stop, `Ctrl+Shift+C` mode).

- **Project page (local):** open `website/index.html` in your browser.
- **Author on GitHub:** [github.com/jbmustaq](https://github.com/jbmustaq)

## Quick start (from source)

1. Install [Python 3](https://www.python.org/downloads/) (check “Add Python to PATH” on Windows).
2. In this folder, run:

   ```bash
   pip install -r requirements.txt
   python voice_type.py
   ```

3. On first run, the app can download the **English GigaSpeech** model (~500 MB) if it is missing. You can also switch **speech model** in the UI when both model folders are present (see build docs for bundling).

## Publish to GitHub (first time — follow in order)

You only do this once per computer for this repo. Use your **GitHub username** and password is **not** used for Git anymore; GitHub will ask for a **Personal Access Token** (like a password for Git only).

### Step 1 — Create a token (one-time)

1. While logged in at GitHub, open: **Settings → Developer settings → Personal access tokens → Tokens (classic)**  
   Direct link: [github.com/settings/tokens](https://github.com/settings/tokens)
2. **Generate new token (classic)**.
3. Give it a name (e.g. `voiext-laptop`), set an expiry you are comfortable with.
4. Enable scope **`repo`** (full control of private repositories).
5. Generate and **copy the token** — you will not see it again. Store it somewhere safe (password manager).

### Step 2 — Create an empty repository on GitHub

1. Open [github.com/new](https://github.com/new).
2. Repository name: **`voiext`** (must match the links on your website, or change the website links later).
3. Choose **Public**, leave “Add a README” **unchecked** (you already have files locally).
4. Click **Create repository**.

### Step 3 — Upload from your PC (Command Prompt or PowerShell)

Open **Command Prompt** or **PowerShell**, then run each block (change the path if your folder is elsewhere):

```bat
cd C:\Users\Mustaq\Desktop\voiext
git init
git branch -M main
git add .
git commit -m "Initial commit: VoiceType / Voiext"
```

Connect to **your** GitHub repo (replace if your username is different):

```bat
git remote add origin https://github.com/jbmustaq/voiext.git
git push -u origin main
```

When Git asks for credentials:

- **Username:** `jbmustaq`
- **Password:** paste your **token** (not your Google/GitHub account password)

If `git` is not recognized, install [Git for Windows](https://git-scm.com/download/win) and reopen the terminal.

### After the first push

- Refresh [github.com/jbmustaq/voiext](https://github.com/jbmustaq/voiext) — your files should appear.
- Large **model** folders are **not** in Git (see `.gitignore`); releases can ship zips built with `scripts\build_windows.ps1` instead.

## Build a Windows zip (optional)

From the project root, in PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_windows.ps1
```

Then attach `dist\VoiceType-Windows-models.zip` to a **GitHub Release** (repo → **Releases** → **Draft a new release**).

## License

Add a `LICENSE` file when you choose one (MIT is common for small open-source apps).
