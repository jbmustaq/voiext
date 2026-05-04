"""
VoiceType - Offline Voice-to-Text App

Ctrl+Shift+V = Start/Stop | Ctrl+Shift+C = Switch Mode

Partials show live in GUI, only final confirmed text gets typed.
Desktop commands: open browser, go to URL, open folders, launch apps.
"""

import ctypes
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk
import webbrowser
import zipfile
import urllib.request

import pystray
import sounddevice as sd
from PIL import Image, ImageDraw
from pynput import keyboard
from spellchecker import SpellChecker
from vosk import Model, KaldiRecognizer
import numpy as np
from PIL import ImageGrab

try:
    import pyautogui
    HAS_PYAUTOGUI = True
except Exception:
    HAS_PYAUTOGUI = False

try:
    import pytesseract
    from pytesseract import Output
    pytesseract.get_tesseract_version()
    HAS_TESSERACT = True
except Exception:
    HAS_TESSERACT = False

APP_NAME = "VoiceType"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
IS_WINDOWS = sys.platform == "win32"

# PyInstaller: bundled resources live under sys._MEIPASS
def _resource_root():
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return sys._MEIPASS
    return SCRIPT_DIR


def _writable_root():
    """Directory for config.json (next to exe when frozen, else script dir)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return SCRIPT_DIR


CONFIG_PATH = os.path.join(_writable_root(), "voicetype_config.json")
MODEL_URL = "https://alphacephei.com/vosk/models/vosk-model-en-us-0.42-gigaspeech.zip"
SAMPLE_RATE = 16000
BLOCKSIZE = 1600
AUTO_SLEEP_SECONDS = 60

# --- Autocomplete ---
GPT2_MODEL_DIR = os.path.join(_writable_root(), "voicetype_models", "gpt2")
PREDICTION_SILENCE_SECONDS = 1.5
PREDICTION_MAX_TOKENS = 20
NGRAM_ORDER = 3
NGRAM_MIN_FREQ = 3
APPROVAL_PHRASES = ["yes", "okay", "approve", "accept", "that's right", "that is right", "go ahead", "confirm"]

# Preset id -> human label, nested folder name inside zip for Giga (None = bundled only)
MODEL_PRESETS = {
    "en_giga": {
        "label": "English (US) — GigaSpeech",
        "zip_folder": "vosk-model-en-us-0.42-gigaspeech",
        "download_url": MODEL_URL,
    },
    "indian_en": {
        "label": "Indian English (bundled)",
        "zip_folder": None,
        "download_url": None,
    },
}


def model_path_for_preset(preset_id):
    """Filesystem path for a preset (dev layout vs PyInstaller bundle)."""
    root = _resource_root()
    if getattr(sys, "frozen", False):
        sub = {"en_giga": ("models", "en_giga"), "indian_en": ("models", "indian_en")}.get(preset_id)
        if not sub:
            return os.path.join(root, "models", "en_giga")
        return os.path.join(root, *sub)
    if preset_id == "indian_en":
        return os.path.join(SCRIPT_DIR, "model-indian-backup")
    return os.path.join(SCRIPT_DIR, "model")


def load_model_choice():
    try:
        if os.path.isfile(CONFIG_PATH):
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            mid = data.get("model_preset", "en_giga")
            if mid in MODEL_PRESETS:
                return mid
    except Exception:
        pass
    return "en_giga"


def save_model_choice(preset_id):
    try:
        data = {}
        if os.path.isfile(CONFIG_PATH):
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
        data["model_preset"] = preset_id
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


def load_auto_start():
    try:
        if os.path.isfile(CONFIG_PATH):
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            return bool(data.get("auto_start", False))
    except Exception:
        pass
    return False


def save_auto_start(enabled):
    try:
        data = {}
        if os.path.isfile(CONFIG_PATH):
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
        data["auto_start"] = bool(enabled)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


def load_mic_gain():
    try:
        if os.path.isfile(CONFIG_PATH):
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            return max(1.0, min(5.0, float(data.get("mic_gain", 1.0))))
    except Exception:
        pass
    return 1.0


def save_mic_gain(gain):
    try:
        data = {}
        if os.path.isfile(CONFIG_PATH):
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
        data["mic_gain"] = float(gain)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


def load_autocomplete_enabled():
    try:
        if os.path.isfile(CONFIG_PATH):
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            return bool(data.get("autocomplete_enabled", True))
    except Exception:
        pass
    return True


def save_autocomplete_enabled(enabled):
    try:
        data = {}
        if os.path.isfile(CONFIG_PATH):
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
        data["autocomplete_enabled"] = bool(enabled)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


selected_model_preset = load_model_choice()
mic_gain = load_mic_gain()
autocomplete_enabled = load_autocomplete_enabled()


def model_is_valid_at(path):
    readme = os.path.join(path, "README")
    conf = os.path.join(path, "conf")
    return os.path.exists(readme) and os.path.exists(conf)


def resolve_model_dir_for(preset_id):
    p = model_path_for_preset(preset_id)
    if model_is_valid_at(p):
        return p
    if getattr(sys, "frozen", False) and preset_id == "en_giga":
        cache = os.path.join(_writable_root(), "voicetype_models", "en_giga")
        if model_is_valid_at(cache):
            return cache
    return p


MODEL_DIR = resolve_model_dir_for(selected_model_preset)


def open_uri_or_path(target):
    """Cross-platform open for files, folders, and URLs."""
    if IS_WINDOWS:
        os.startfile(target)
        return
    if sys.platform == "darwin":
        subprocess.run(["open", target], check=False)
        return
    subprocess.run(["xdg-open", target], check=False)

STATE_IDLE = "idle"
STATE_DICTATION = "dictation"
STATE_COMMAND = "command"
STATE_SLEEPING = "sleeping"

# --- Keyboard shortcut commands ---
KEY_COMMANDS = {
    "copy": [keyboard.Key.ctrl, "c"],
    "paste": [keyboard.Key.ctrl, "v"],
    "cut": [keyboard.Key.ctrl, "x"],
    "undo": [keyboard.Key.ctrl, "z"],
    "redo": [keyboard.Key.ctrl, "y"],
    "select all": [keyboard.Key.ctrl, "a"],
    "find": [keyboard.Key.ctrl, "f"],
    "find next": [keyboard.Key.f3],
    "go to line": [keyboard.Key.ctrl, "g"],
    "bold": [keyboard.Key.ctrl, "b"],
    "italic": [keyboard.Key.ctrl, "i"],
    "underline": [keyboard.Key.ctrl, "u"],
    "save": [keyboard.Key.ctrl, "s"],
    "new file": [keyboard.Key.ctrl, "n"],
    "new line": [keyboard.Key.enter],
    "enter": [keyboard.Key.enter],
    "tab": [keyboard.Key.tab],
    "backspace": [keyboard.Key.backspace],
    "delete": [keyboard.Key.delete],
    "home": [keyboard.Key.home],
    "end": [keyboard.Key.end],
    "switch": [keyboard.Key.alt, keyboard.Key.tab],
    "page up": [keyboard.Key.page_up],
    "page down": [keyboard.Key.page_down],
    "paige up": [keyboard.Key.page_up],       # ASR alias
    "paige down": [keyboard.Key.page_down],   # ASR alias
    "up": [keyboard.Key.up],
    "down": [keyboard.Key.down],
    "left": [keyboard.Key.left],
    "right": [keyboard.Key.right],
    "close tab": [keyboard.Key.ctrl, "w"],
    "close": [keyboard.Key.alt, keyboard.KeyCode.from_vk(0x73)],
}

# --- Desktop commands (open apps, folders, URLs) ---
DESKTOP_COMMANDS = {
    # Apps
    "open browser": "browser",
    "open chrome": "chrome",
    "open notepad": "notepad",
    "open calculator": "calc",
    "open file explorer": "explorer",
    "open explorer": "explorer",
    "open settings": "settings",
    "open command prompt": "cmd",
    "open terminal": "cmd",
    "open task manager": "taskmgr",
    "open paint": "mspaint",
    "open snipping tool": "snippingtool",
    "open word": "winword",
    "open excel": "excel",
    "open powerpoint": "powerpnt",
    "open v s code": "code",
    "open visual studio code": "code",
    # Folders
    "open downloads": "downloads",
    "open documents": "documents",
    "open desktop": "desktop",
    "open pictures": "pictures",
    "open videos": "videos",
    "open music": "music",
    "open c drive": "cdrive",
    "open d drive": "ddrive",
    # Media
    "volume up": "volup",
    "volume down": "voldown",
    "mute": "mute",
    "play pause": "playpause",
    "next track": "nexttrack",
    "previous track": "prevtrack",
    # URL patterns
    "go to": "url",
}

# Custom URL shortcuts - add variations that Vosk might mishear
URL_SHORTCUTS = {
    "servermania": "https://servermania.com",
    "server mania": "https://servermania.com",
    "serve a mania": "https://servermania.com",
    "server mania": "https://servermania.com",
    "gautama darker mania": "https://servermania.com",  # Common mishearing
    "gautama mania": "https://servermania.com",
    "darker mania": "https://servermania.com",
    "ever mania": "https://servermania.com",
    "ver mania": "https://servermania.com",
    "google": "https://google.com",
    "youtube": "https://youtube.com",
}

def _launch_chrome():
    if IS_WINDOWS:
        os.startfile("chrome")
        return
    for exe in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
        path = shutil.which(exe)
        if path:
            subprocess.Popen([path])
            return
    webbrowser.open("https://www.google.com")


def try_open_app(name):
    """Try to open an app by name on Windows — checks PATH, common install dirs, and App Paths registry."""
    name = name.strip()
    if not name:
        return False
    # 1. If on PATH (e.g. "code", "spotify" if added to PATH)
    if shutil.which(name):
        subprocess.Popen([name])
        return True
    # 2. Try os.startfile (works for registered App Paths like "spotify", "discord", etc.)
    if IS_WINDOWS:
        try:
            os.startfile(name)
            return True
        except OSError:
            pass
        # 3. Check App Paths registry (covers apps not on PATH but registered in Windows)
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                 rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{name}.exe",
                                 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY)
            path, _ = winreg.QueryValueEx(key, "")
            winreg.CloseKey(key)
            if path and os.path.isfile(path):
                os.startfile(path)
                return True
        except OSError:
            pass
    return False


# Map desktop command IDs to actions
APP_LAUNCHERS = {
    "browser": lambda: webbrowser.open("https://www.google.com"),
    "chrome": _launch_chrome,
    "notepad": lambda: open_uri_or_path("notepad") if IS_WINDOWS else subprocess.Popen(["gedit"]) if shutil.which("gedit") else None,
    "calc": lambda: open_uri_or_path("calc") if IS_WINDOWS else subprocess.Popen(["gnome-calculator"]) if shutil.which("gnome-calculator") else None,
    "explorer": lambda: os.startfile("explorer") if IS_WINDOWS else open_uri_or_path(os.path.expanduser("~")),
    "settings": lambda: os.startfile("ms-settings:") if IS_WINDOWS else subprocess.Popen(["gnome-control-center"]) if shutil.which("gnome-control-center") else None,
    "cmd": lambda: open_uri_or_path("cmd") if IS_WINDOWS else subprocess.Popen(["x-terminal-emulator"]) if shutil.which("x-terminal-emulator") else subprocess.Popen(["gnome-terminal"]) if shutil.which("gnome-terminal") else None,
    "taskmgr": lambda: os.startfile("taskmgr") if IS_WINDOWS else None,
    "mspaint": lambda: os.startfile("mspaint") if IS_WINDOWS else None,
    "snippingtool": lambda: os.startfile("snippingtool") if IS_WINDOWS else None,
    "winword": lambda: _open_office_app("WINWORD.EXE", "winword", "wordpad"),
    "excel": lambda: _open_office_app("EXCEL.EXE", "excel"),
    "powerpnt": lambda: _open_office_app("POWERPNT.EXE", "powerpnt"),
    "code": lambda: subprocess.Popen(["code"]) if shutil.which("code") else open_uri_or_path("code") if IS_WINDOWS else None,
}

FOLDER_LAUNCHERS = {
    "downloads": lambda: open_uri_or_path(os.path.join(os.path.expanduser("~"), "Downloads")),
    "documents": lambda: open_uri_or_path(os.path.join(os.path.expanduser("~"), "Documents")),
    "desktop": lambda: open_uri_or_path(os.path.join(os.path.expanduser("~"), "Desktop")),
    "pictures": lambda: open_uri_or_path(os.path.join(os.path.expanduser("~"), "Pictures")),
    "videos": lambda: open_uri_or_path(os.path.join(os.path.expanduser("~"), "Videos")),
    "music": lambda: open_uri_or_path(os.path.join(os.path.expanduser("~"), "Music")),
    "cdrive": lambda: open_uri_or_path("C:\\") if IS_WINDOWS else None,
    "ddrive": lambda: open_uri_or_path("D:\\") if IS_WINDOWS and os.path.exists("D:\\") else None,
}

# Volume/media keys via SendMessage
VK_VOLUME_UP = 0xAF
VK_VOLUME_DOWN = 0xAE
VK_VOLUME_MUTE = 0xAD
VK_MEDIA_PLAY_PAUSE = 0xB3
VK_MEDIA_NEXT = 0xB0
VK_MEDIA_PREV = 0xB1

def send_vk(vk):
    """Send a virtual key press via Windows API using SendInput."""
    if not IS_WINDOWS:
        return
    ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
    ctypes.windll.user32.keybd_event(vk, 0, 2, 0)

MEDIA_LAUNCHERS = {
    "volup": lambda: send_vk(VK_VOLUME_UP),
    "voldown": lambda: send_vk(VK_VOLUME_DOWN),
    "mute": lambda: send_vk(VK_VOLUME_MUTE),
    "playpause": lambda: send_vk(VK_MEDIA_PLAY_PAUSE),
    "nexttrack": lambda: send_vk(VK_MEDIA_NEXT),
    "prevtrack": lambda: send_vk(VK_MEDIA_PREV),
}

MOUSE_COMMANDS = {
    "click": "click",
    "left click": "click",
    "right click": "right_click",
    "double click": "double_click",
    "middle click": "middle_click",
    "scroll up": "scroll_up",
    "scroll down": "scroll_down",
    "analyze screen": "analyze_screen",
    "scan screen": "analyze_screen",
}

def execute_mouse_action(action, target_text=None):
    if not HAS_PYAUTOGUI:
        send_to_gui("log", "Mouse control requires pyautogui: pip install pyautogui")
        return
    try:
        if action == "click":
            pyautogui.click()
        elif action == "right_click":
            pyautogui.rightClick()
        elif action == "double_click":
            pyautogui.doubleClick()
        elif action == "middle_click":
            pyautogui.middleClick()
        elif action == "scroll_up":
            pyautogui.scroll(3)
        elif action == "scroll_down":
            pyautogui.scroll(-3)
        elif action in ("click_text", "move_to_text"):
            if not HAS_TESSERACT:
                send_to_gui("log", "Screen-reading click requires pytesseract and Tesseract OCR engine.")
                return
            threading.Thread(target=_click_on_text, args=(target_text, action == "click_text"), daemon=True).start()
            return
        elif action == "analyze_screen":
            if not HAS_TESSERACT:
                send_to_gui("log", "Screen analysis requires pytesseract and Tesseract OCR engine.")
                return
            threading.Thread(target=_analyze_screen_thread, daemon=True).start()
            return
        if action not in ("click_text", "move_to_text", "analyze_screen"):
            send_to_gui("log", f"Mouse: {action.replace('_', ' ')}")
    except Exception as e:
        send_to_gui("log", f"Mouse error: {e}")

def _click_on_text(target_text, should_click=True):
    try:
        send_to_gui("log", f"Scanning screen for '{target_text}'...")
        screenshot = ImageGrab.grab()
        data = pytesseract.image_to_data(screenshot, output_type=Output.DICT)
        n_boxes = len(data["text"])
        matches = []
        for i in range(n_boxes):
            text = data["text"][i].strip()
            conf = int(data["conf"][i])
            if conf > 30 and target_text.lower() in text.lower():
                x = data["left"][i] + data["width"][i] // 2
                y = data["top"][i] + data["height"][i] // 2
                matches.append((conf, x, y, text))
        if not matches:
            send_to_gui("log", f"'{target_text}' not found on screen.")
            return
        matches.sort(reverse=True)
        _, x, y, found_text = matches[0]
        pyautogui.moveTo(x, y, duration=0.2)
        if should_click:
            pyautogui.click()
        send_to_gui("log", f"{'Clicked' if should_click else 'Moved to'} '{found_text}' at ({x}, {y})")
    except Exception as e:
        send_to_gui("log", f"Screen click error: {e}")

def _analyze_screen_thread():
    try:
        send_to_gui("log", "Analyzing screen...")
        screenshot = ImageGrab.grab()
        data = pytesseract.image_to_data(screenshot, output_type=Output.DICT)
        elements = []
        for i in range(len(data["text"])):
            text = data["text"][i].strip()
            conf = int(data["conf"][i])
            if conf > 30 and text:
                elements.append(text)
        if elements:
            unique = []
            seen = set()
            for e in elements:
                if e.lower() not in seen:
                    seen.add(e.lower())
                    unique.append(e)
            send_to_gui("log", f"Screen text ({len(unique)} items): {', '.join(unique[:30])}")
            if len(unique) > 30:
                send_to_gui("log", f"... and {len(unique) - 30} more.")
        else:
            send_to_gui("log", "No readable text found on screen.")
    except Exception as e:
        send_to_gui("log", f"Screen analysis error: {e}")


def _open_office_app(exe_name, primary_cmd, fallback_cmd=None):
    """Open an Office app by searching common installation paths."""
    office_paths = [
        r"C:\Program Files\Microsoft Office\root\Office16",
        r"C:\Program Files (x86)\Microsoft Office\root\Office16",
        r"C:\Program Files\Microsoft Office 15\Office15",
        r"C:\Program Files (x86)\Microsoft Office 15\Office15",
        r"C:\Program Files\Microsoft Office\Office16",
        r"C:\Program Files (x86)\Microsoft Office\Office16",
    ]
    for path in office_paths:
        exe_path = os.path.join(path, exe_name)
        if os.path.exists(exe_path):
            open_uri_or_path(exe_path)
            return True
    # Fallback to generic command
    if fallback_cmd:
        try:
            open_uri_or_path(fallback_cmd)
            return True
        except Exception:
            pass
    return False

STOP_PHRASES = ["stop", "stop listening", "stop dictation", "stop typing"]
SLEEP_PHRASES = ["go to sleep", "sleep", "pause", "take a break"]
WAKE_PHRASES = ["wake up", "resume", "start listening", "start typing", "i'm back", "hey type", "wake", "hey", "activate", "listen"]
TYPE_PHRASES = ["type", "start typing", "start type", "begin typing", "type mode", "dictate", "start dictation", "dictation", "start dictating"]
COMMAND_PHRASES = ["command mode", "back to command", "command", "stop typing"]

GARBAGE_WORDS = {
    "huh", "hmm", "hm", "uh", "um", "ah", "oh",
    "at you edge", "ha", "ah ha", "hey", "huh huh",
    "mm", "mhm", "mm-hmm", "huh ha", "uh huh",
}

spell = SpellChecker()

state = STATE_IDLE
stop_app = False
model = None
rec = None
stream = None
prev_state = STATE_COMMAND
keyboard_ctrl = keyboard.Controller()
lock = threading.Lock()
model_lock = threading.Lock()
pending_action = None
last_speech_time = time.time()

# --- Autocomplete state ---
gpt2_model = None
gpt2_tokenizer = None
gpt2_loading = False
active_prediction = None
prediction_pending = False
recent_text = ""
ngram_data = {}

gui_queue = queue.Queue()

STATE_COLORS = {
    STATE_IDLE: "#cc0000",
    STATE_DICTATION: "#00aa00",
    STATE_COMMAND: "#0066ff",
    STATE_SLEEPING: "#cc9900",
}
STATE_LABELS = {
    STATE_IDLE: "IDLE",
    STATE_DICTATION: "DICTATION",
    STATE_COMMAND: "COMMAND",
    STATE_SLEEPING: "SLEEPING",
}


def is_garbage(text):
    lower = text.lower().strip()
    if not lower:
        return True
    if lower in GARBAGE_WORDS:
        return True
    words = lower.split()
    if len(words) == 1 and len(words[0]) <= 2:
        return True
    return False


def auto_correct(text):
    words = text.split()
    corrected = []
    changed = False
    for word in words:
        prefix = suffix = ""
        clean = word
        while clean and not clean[0].isalpha():
            prefix += clean[0]; clean = clean[1:]
        while clean and not clean[-1].isalpha():
            suffix = clean[-1] + suffix; clean = clean[:-1]
        if not clean:
            corrected.append(word); continue
        if clean.lower() in spell:
            corrected.append(word)
        else:
            suggestion = spell.correction(clean)
            if suggestion and suggestion != clean.lower():
                if clean.isupper(): suggestion = suggestion.upper()
                elif clean[0].isupper(): suggestion = suggestion.capitalize()
                corrected.append(prefix + suggestion + suffix)
                changed = True
            else:
                corrected.append(word)
    result = " ".join(corrected)
    if changed:
        send_to_gui("log", f"Corrected: '{text}' -> '{result}'")
    return result


# --- Number word to digit conversion ---
NUMBER_WORDS = {
    "zero": 0, "oh": 0, "one": 1, "two": 2, "three": 3, "four": 4,
    "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
    "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
    "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
    "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30,
    "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
    "eighty": 80, "ninety": 90,
}
MULTIPLIERS = {
    "hundred": 100,
    "thousand": 1000,
    "million": 1000000,
    "billion": 1000000000,
}
ORDINALS = {
    "first": "1st", "second": "2nd", "third": "3rd",
    "fourth": "4th", "fifth": "5th", "sixth": "6th",
    "seventh": "7th", "eighth": "8th", "ninth": "9th",
    "tenth": "10th", "eleventh": "11th", "twelfth": "12th",
    "thirteenth": "13th", "fourteenth": "14th", "fifteenth": "15th",
    "sixteenth": "16th", "seventeenth": "17th", "eighteenth": "18th",
    "nineteenth": "19th", "twentieth": "20th",
    "thirtieth": "30th", "fortieth": "40th", "fiftieth": "50th",
    "sixtieth": "60th", "seventieth": "70th", "eightieth": "80th",
    "ninetieth": "90th", "hundredth": "100th",
}


def words_to_numbers(text):
    """Convert spoken number words to digits: 'one two three' -> '123', 'twenty five' -> '25'."""
    words = text.split()
    result = []
    i = 0
    changed = False

    while i < len(words):
        word = words[i].lower().strip(".,;:!?")
        # Check ordinals first
        if word in ORDINALS:
            # Replace the original word preserving nothing (ordinals are standalone)
            result.append(ORDINALS[word])
            changed = True
            i += 1
            continue

        # Try to collect a number phrase
        num, consumed = parse_number_phrase(words, i)
        if num is not None and consumed > 0:
            result.append(str(num))
            changed = True
            i += consumed
        else:
            result.append(words[i])
            i += 1

    if changed:
        converted = " ".join(result)
        send_to_gui("log", f"Numbers: '{text}' -> '{converted}'")
        return converted
    return text


def parse_number_phrase(words, start):
    """Parse a sequence of number words starting at `start` and return (value, words_consumed)."""
    total = 0
    current = 0
    i = start
    consumed = 0
    has_number = False

    while i < len(words):
        word = words[i].lower().strip(".,;:!?")

        # Skip "and" within number phrases (e.g. "three hundred and fifty")
        if word == "and" and has_number:
            consumed += 1
            i += 1
            continue

        if word in NUMBER_WORDS:
            val = NUMBER_WORDS[word]
            has_number = True
            if val < 10 and current == 0:
                # Could be part of a multi-digit number like "one two three" = 123
                if i + 1 < len(words) and words[i + 1].lower().strip(".,;:!?") in NUMBER_WORDS:
                    next_val = NUMBER_WORDS[words[i + 1].lower().strip(".,;:!?")]
                    if next_val < 10:
                        # Digit sequence: "one two three" → 123
                        digits = []
                        j = i
                        while j < len(words) and words[j].lower().strip(".,;:!?") in NUMBER_WORDS:
                            d = NUMBER_WORDS[words[j].lower().strip(".,;:!?")]
                            if d >= 10 and d < 100:
                                break
                            digits.append(str(d))
                            j += 1
                        if len(digits) > 1:
                            return int("".join(digits)), j - start
                current += val
            elif val >= 10 and val < 100:
                current += val
            else:
                current += val
            consumed += 1
            i += 1

        elif word in MULTIPLIERS:
            mult = MULTIPLIERS[word]
            has_number = True
            if current == 0:
                current = 1
            total += current * mult
            current = 0
            consumed += 1
            i += 1
        else:
            break

    total += current
    if consumed > 0 and total > 0:
        return total, consumed
    return None, 0


def send_to_gui(event, data=""):
    gui_queue.put((event, data))


# --- Text output: only final confirmed text gets typed ---
# Partials are shown live in the GUI for real-time feedback,
# but no text is sent to the editor until Vosk confirms a result.
# This eliminates wrong-then-right duplication and slow backspacing.


def finalize_text(raw_text):
    """Type the final confirmed text. Spell-corrects, converts numbers, adds trailing space."""
    global recent_text, ngram_data
    try:
        corrected = auto_correct(raw_text)
        corrected = words_to_numbers(corrected)
        keyboard_ctrl.type(corrected)
        keyboard_ctrl.type(" ")
        send_to_gui("heard", corrected)
        # Update autocomplete context
        recent_text = (recent_text + " " + corrected).strip()
        if len(recent_text) > 500:
            recent_text = recent_text[-500:]
        _rebuild_ngrams()
    except Exception as e:
        send_to_gui("log", f"Type error: {e}")


def _rebuild_ngrams():
    """Rebuild the N-gram model from recent_text."""
    global ngram_data
    words = recent_text.lower().split()
    ngram_data = {}
    for i in range(len(words) - NGRAM_ORDER + 1):
        key = tuple(words[i:i + NGRAM_ORDER - 1])
        next_word = words[i + NGRAM_ORDER - 1]
        ngram_data[key] = ngram_data.get(key, {})
        ngram_data[key][next_word] = ngram_data[key].get(next_word, 0) + 1


def ngram_predict(text, max_words=3):
    """Predict the next words using N-gram model. Returns a string or None."""
    if not ngram_data:
        return None
    words = text.lower().split()
    if len(words) < NGRAM_ORDER - 1:
        return None
    result = []
    context_words = list(words)
    for _ in range(max_words):
        key = tuple(context_words[-(NGRAM_ORDER - 1):])
        candidates = ngram_data.get(key)
        if not candidates:
            break
        best_word = max(candidates, key=candidates.get)
        if candidates[best_word] < NGRAM_MIN_FREQ:
            break
        result.append(best_word)
        context_words.append(best_word)
    return " ".join(result) if result else None

def model_is_valid():
    """Check if a Vosk model exists and looks valid."""
    return model_is_valid_at(MODEL_DIR)


def download_model():
    """Download Vosk model for current preset (English Giga only if missing)."""
    if model_is_valid():
        return
    preset = MODEL_PRESETS.get(selected_model_preset, MODEL_PRESETS["en_giga"])
    url = preset.get("download_url")
    nested = preset.get("zip_folder")
    if not url or not nested:
        send_to_gui("log", "Bundled model missing or invalid. Check model folder.")
        return
    send_to_gui("log", "Downloading speech model (~500MB)...")
    global MODEL_DIR
    work = _writable_root()
    partial_zip = os.path.join(work, "model_download.zip")
    dest = MODEL_DIR
    if getattr(sys, "frozen", False) and selected_model_preset == "en_giga":
        dest = os.path.join(_writable_root(), "voicetype_models", "en_giga")
    try:
        if os.path.exists(partial_zip):
            os.remove(partial_zip)

        def report_progress(block_num, block_size, total_size):
            downloaded = block_num * block_size
            percent = min(100, (downloaded / total_size) * 100) if total_size > 0 else 0
            if block_num % 100 == 0:
                send_to_gui("log", f"Progress: {percent:.0f}%")

        urllib.request.urlretrieve(url, partial_zip, reporthook=report_progress)

        with zipfile.ZipFile(partial_zip, "r") as zip_ref:
            zip_ref.extractall(work)
        os.remove(partial_zip)

        extracted_dir = os.path.join(work, nested)
        if os.path.exists(extracted_dir):
            if os.path.exists(dest):
                shutil.rmtree(dest)
            parent = os.path.dirname(dest)
            if parent:
                os.makedirs(parent, exist_ok=True)
            shutil.move(extracted_dir, dest)
            MODEL_DIR = dest

        send_to_gui("log", "Model downloaded successfully!")
    except Exception as e:
        send_to_gui("log", f"Download failed: {e}")
        send_to_gui("log", "Manual download: https://alphacephei.com/vosk/models")
        if os.path.exists(partial_zip):
            try:
                os.remove(partial_zip)
            except Exception:
                pass


# --- Autocomplete: DistilGPT-2 model management ---

def gpt2_model_is_valid():
    """Check if DistilGPT-2 model files exist."""
    config_file = os.path.join(GPT2_MODEL_DIR, "config.json")
    model_file = os.path.join(GPT2_MODEL_DIR, "model.safetensors")
    tokenizer_file = os.path.join(GPT2_MODEL_DIR, "tokenizer.json")
    return os.path.exists(config_file) and (os.path.exists(model_file) or os.path.exists(os.path.join(GPT2_MODEL_DIR, "pytorch_model.bin"))) and os.path.exists(tokenizer_file)


def download_gpt2_model():
    """Download DistilGPT-2 using Hugging Face transformers."""
    global gpt2_loading
    if gpt2_model_is_valid():
        return
    gpt2_loading = True
    send_to_gui("log", "Downloading autocomplete model (~350MB)...")
    try:
        from transformers import GPT2LMHeadModel, GPT2Tokenizer
        tokenizer = GPT2Tokenizer.from_pretrained("distilgpt2")
        model = GPT2LMHeadModel.from_pretrained("distilgpt2")
        os.makedirs(GPT2_MODEL_DIR, exist_ok=True)
        model.save_pretrained(GPT2_MODEL_DIR)
        tokenizer.save_pretrained(GPT2_MODEL_DIR)
        send_to_gui("log", "Autocomplete model downloaded.")
    except Exception as e:
        send_to_gui("log", f"GPT-2 download failed: {e}")
        send_to_gui("log", "Autocomplete will be unavailable until model is downloaded.")
    finally:
        gpt2_loading = False


def load_gpt2_model():
    """Load DistilGPT-2 model and tokenizer into memory."""
    global gpt2_model, gpt2_tokenizer, gpt2_loading
    if gpt2_model is not None:
        return True
    if gpt2_loading:
        return False
    gpt2_loading = True
    try:
        if not gpt2_model_is_valid():
            download_gpt2_model()
        if not gpt2_model_is_valid():
            send_to_gui("log", "GPT-2 model files not found.")
            return False
        from transformers import GPT2LMHeadModel, GPT2Tokenizer
        send_to_gui("log", "Loading autocomplete model...")
        gpt2_tokenizer = GPT2Tokenizer.from_pretrained(GPT2_MODEL_DIR)
        gpt2_model = GPT2LMHeadModel.from_pretrained(GPT2_MODEL_DIR)
        gpt2_model.eval()
        send_to_gui("log", "Autocomplete ready.")
        return True
    except Exception as e:
        send_to_gui("log", f"GPT-2 load error: {e}")
        gpt2_model = None
        gpt2_tokenizer = None
        return False
    finally:
        gpt2_loading = False


def generate_prediction(context_text):
    """Generate a sentence completion using DistilGPT-2. Returns prediction string or None."""
    global gpt2_model, gpt2_tokenizer
    if gpt2_model is None or gpt2_tokenizer is None:
        return None
    try:
        import torch
        context = context_text.strip()
        if not context:
            return None
        if len(context) > 400:
            context = context[-400:]
        input_ids = gpt2_tokenizer.encode(context, return_tensors="pt")
        if input_ids.shape[1] > 128:
            input_ids = input_ids[:, -128:]
        with torch.no_grad():
            output = gpt2_model.generate(
                input_ids,
                max_new_tokens=PREDICTION_MAX_TOKENS,
                do_sample=True,
                top_k=50,
                top_p=0.9,
                temperature=0.7,
                pad_token_id=gpt2_tokenizer.eos_token_id,
            )
        new_tokens = output[0][input_ids.shape[1]:]
        prediction = gpt2_tokenizer.decode(new_tokens, skip_special_tokens=True).strip()
        for punct in ['.', '!', '?']:
            idx = prediction.find(punct)
            if idx != -1 and idx < len(prediction) - 1:
                prediction = prediction[:idx + 1]
                break
        if len(prediction) < 3:
            return None
        return prediction
    except Exception as e:
        send_to_gui("log", f"Prediction error: {e}")
        return None


def request_prediction():
    """Background thread: try N-gram first, then GPT-2 if needed."""
    global prediction_pending, active_prediction
    if prediction_pending:
        return
    prediction_pending = True
    try:
        # Fast lane: N-gram
        ngram_result = ngram_predict(recent_text)
        if ngram_result:
            active_prediction = ngram_result
            send_to_gui("prediction", ngram_result)
            return
        # Smart lane: GPT-2
        if gpt2_model is None:
            if not load_gpt2_model():
                return
        prediction = generate_prediction(recent_text)
        if prediction:
            active_prediction = prediction
            send_to_gui("prediction", prediction)
        else:
            active_prediction = None
            send_to_gui("prediction", "")
    finally:
        prediction_pending = False
    try:
        for k in keys:
            keyboard_ctrl.press(k)
        for k in reversed(keys):
            keyboard_ctrl.release(k)
    except Exception as e:
        send_to_gui("log", f"Shortcut error: {e}")


def execute_desktop_command(cmd_id, full_text=""):
    """Execute a desktop command (open app, folder, URL, media)."""
    try:
        # URL command — extract URL from text
        if cmd_id == "url":
            url = extract_url(full_text)
            if url:
                webbrowser.open(url)
                send_to_gui("log", f"Opened: {url}")
            else:
                # "go to" without URL → Ctrl+G
                execute_shortcut([keyboard.Key.ctrl, "g"])
            return

        # App launchers
        if cmd_id in APP_LAUNCHERS:
            APP_LAUNCHERS[cmd_id]()
            send_to_gui("log", f"Opened: {cmd_id}")
            return

        # Folder launchers
        if cmd_id in FOLDER_LAUNCHERS:
            fn = FOLDER_LAUNCHERS[cmd_id]
            fn()
            send_to_gui("log", f"Opened: {cmd_id}")
            return

        # Media/volume
        if cmd_id in MEDIA_LAUNCHERS:
            MEDIA_LAUNCHERS[cmd_id]()
            send_to_gui("log", f"Executed: {cmd_id}")
            return

    except Exception as e:
        send_to_gui("log", f"Desktop cmd error: {e}")


def extract_url(text):
    """Extract a URL from recognized text like 'go to google dot com'."""
    lower = text.lower()
    # Remove the command prefix ("go to", "open")
    for prefix in ["go to ", "open "]:
        if lower.startswith(prefix):
            lower = lower[len(prefix):]
            break
    if not lower:
        return None

    # Check custom shortcuts first (handles misheard phrases)
    # Match on key words: if text contains distinctive parts of the shortcut key
    for shortcut, url in URL_SHORTCUTS.items():
        shortcut_words = shortcut.split()
        # If shortcut is multi-word, check if most words match
        if len(shortcut_words) > 1:
            matches = sum(1 for w in shortcut_words if w in lower)
            if matches >= len(shortcut_words) - 1:  # Allow 1 misheard word
                return url
        elif shortcut in lower:
            return url

    # Replace spoken URL patterns
    url_text = lower
    url_text = url_text.replace(" dot ", ".").replace(" dot", ".")  # "google dot com"
    url_text = url_text.replace(" slash ", "/")  # "google dot com slash search"
    url_text = url_text.replace(" colon ", ":")  # "http colon slash slash"
    url_text = url_text.replace(" dash ", "-")  # "my-site dot com"
    url_text = url_text.replace(" ", "")  # Remove remaining spaces for clean URLs

    # Add https:// if no protocol
    if "." in url_text and not url_text.startswith("http"):
        url_text = "https://" + url_text

    # Basic validation
    if "." in url_text and len(url_text) > 5:
        return url_text
    return None


def matches_phrase(text, phrases):
    lower = text.lower()
    for phrase in phrases:
        if phrase in lower:
            return phrase
    return None


def matches_phrase_prefix(text, phrases):
    """Match a phrase only at the start of text (word-boundary safe). Longer phrases checked first."""
    lower = text.lower().strip()
    for phrase in sorted(phrases, key=len, reverse=True):
        if lower == phrase or lower.startswith(phrase + " "):
            return phrase
    return None


def handle_final(text):
    """Handle final (confirmed) result."""
    global pending_action
    text = text.strip()
    if not text:
        send_to_gui("partial", "")
        return

    lower = text.lower()

    # --- ALWAYS check control phrases FIRST (before garbage filter) ---
    # This ensures "wake up", "stop", "sleep" etc. work even if
    # Vosk outputs them as short/odd results
    if state == STATE_SLEEPING:
        wake = matches_phrase(lower, WAKE_PHRASES)
        if wake:
            send_to_gui("command", f"WAKE: {wake}")
            pending_action = "wake"
        return

    stop_match = matches_phrase(lower, STOP_PHRASES)
    if stop_match:
        send_to_gui("command", f"STOP: {stop_match}")
        pending_action = "stop"
        return

    sleep = matches_phrase(lower, SLEEP_PHRASES)
    if sleep:
        send_to_gui("command", f"SLEEP: {sleep}")
        pending_action = "sleep"
        return

    # --- "type" trigger → switch from command to dictation mode ---
    if state == STATE_COMMAND:
        type_match = matches_phrase_prefix(lower, TYPE_PHRASES)
        if type_match:
            rest = lower[len(type_match):].strip()
            send_to_gui("command", f"DICTATE: {type_match}")
            pending_action = "type"
            if rest:
                finalize_text(rest)
            return

    # --- "command mode" trigger → switch from dictation to command mode ---
    if state == STATE_DICTATION:
        cmd_match = matches_phrase_prefix(lower, COMMAND_PHRASES)
        if cmd_match:
            send_to_gui("command", f"COMMAND: {cmd_match}")
            pending_action = "command"
            return

    # --- Now filter garbage ---
    if is_garbage(text):
        send_to_gui("partial", "")
        return

    send_to_gui("partial", "")

    # --- Always try to match commands (works in BOTH modes) ---
    # Exact match: entire phrase IS a command → always execute
    # Partial match in command mode → execute
    # Partial match in dictation mode → type it (probably just part of a sentence)

    # Desktop commands — exact or partial depending on mode
    for cmd, cmd_id in DESKTOP_COMMANDS.items():
        if cmd == lower or (state == STATE_COMMAND and cmd in lower):
            execute_desktop_command(cmd_id, text)
            send_to_gui("command", cmd)
            return
        # Special handling for "go to" with URL — match as prefix
        if cmd == "go to" and lower.startswith("go to "):
            execute_desktop_command(cmd_id, text)
            send_to_gui("command", cmd)
            return
        # Special handling for "open browser" — if text starts with "open " and looks like a URL, open it
        if cmd == "open browser" and lower.startswith("open ") and extract_url(text):
            execute_desktop_command("url", text)
            send_to_gui("command", cmd)
            return

    # --- Fallback: "open <app>" for any app not in the hardcoded list ---
    if lower.startswith("open "):
        app_name = lower[5:].strip()
        if app_name and state == STATE_COMMAND:
            if try_open_app(app_name):
                send_to_gui("log", f"Opened: {app_name}")
                send_to_gui("command", f"open {app_name}")
                return
            send_to_gui("log", f"App not found: '{app_name}'")
            return

    # --- Mouse commands ---
    if lower in MOUSE_COMMANDS:
        execute_mouse_action(MOUSE_COMMANDS[lower])
        send_to_gui("command", lower)
        return

    # Click / move to text on screen (command mode only)
    if state == STATE_COMMAND:
        for prefix in ["click on ", "click ", "move to ", "move mouse to "]:
            if lower.startswith(prefix):
                target = lower[len(prefix):].strip()
                if target:
                    action = "click_text" if "click" in prefix else "move_to_text"
                    execute_mouse_action(action, target)
                    send_to_gui("command", f"{prefix}{target}")
                    return

    # Key shortcut commands — exact match
    if lower in KEY_COMMANDS:
        execute_shortcut(KEY_COMMANDS[lower])
        send_to_gui("command", lower)
        return

    # Key shortcut commands — partial match only in command mode
    if state == STATE_COMMAND:
        for cmd, keys in KEY_COMMANDS.items():
            if cmd in lower:
                execute_shortcut(keys)
                send_to_gui("command", cmd)
                return
        send_to_gui("log", f"No command: '{text}'")
        return

    # --- Dictation mode (no command matched) — type the text ---
    # Autocomplete approval: if prediction is active and user says yes/okay, accept it
    if state == STATE_DICTATION and active_prediction is not None:
        if matches_phrase(lower, APPROVAL_PHRASES):
            accepted = active_prediction
            active_prediction = None
            send_to_gui("prediction", "")
            finalize_text(accepted)
            send_to_gui("log", "Prediction accepted.")
            return
        # User said something else — discard prediction
        active_prediction = None
        send_to_gui("prediction", "")

    finalize_text(text)


def handle_partial(text):
    text = text.strip()
    if not text or state == STATE_SLEEPING:
        send_to_gui("partial", "")
        return
    if is_garbage(text):
        send_to_gui("partial", "")
        return
    # Partials only show in GUI — no typing until final result
    send_to_gui("partial", text)


def audio_callback(indata, frames, time_info, status):
    global last_speech_time, active_prediction
    with lock:
        recognizer = rec
    if recognizer is None:
        return
    if mic_gain != 1.0:
        boosted = (indata.astype(np.float32) * mic_gain).astype(np.int16)
        data = boosted.tobytes()
    else:
        data = indata.tobytes()
    if recognizer.AcceptWaveform(data):
        result = json.loads(recognizer.Result())
        text = result.get("text", "")
        if text:
            last_speech_time = time.time()
            if active_prediction is not None:
                active_prediction = None
                send_to_gui("prediction", "")
            handle_final(text)
    else:
        partial = json.loads(recognizer.PartialResult())
        text = partial.get("partial", "")
        if text:
            last_speech_time = time.time()
            if active_prediction is not None:
                active_prediction = None
                send_to_gui("prediction", "")
            handle_partial(text)


# --- State change functions (GUI thread only!) ---

def _start_streaming():
    """Start recognizer + audio stream (assumes model is already loaded)."""
    global state, rec, stream, prev_state, last_speech_time
    try:
        with lock:
            rec = KaldiRecognizer(model, SAMPLE_RATE)
            rec.SetWords(True)

        if stream is None:
            stream = sd.InputStream(
                samplerate=SAMPLE_RATE, channels=1, dtype="int16",
                blocksize=BLOCKSIZE, callback=audio_callback,
            )
            stream.start()

        if state in (STATE_IDLE, STATE_SLEEPING):
            state = prev_state if prev_state in (STATE_DICTATION, STATE_COMMAND) else STATE_COMMAND
        elif state not in (STATE_DICTATION, STATE_COMMAND):
            state = STATE_COMMAND

        last_speech_time = time.time()
        send_to_gui("log", f"Listening [{STATE_LABELS[state]}]")
        send_to_gui("state", state)
    except Exception as e:
        send_to_gui("log", f"Error: {e}")
        state = STATE_IDLE
        rec = None
        send_to_gui("state", state)


def _load_model_and_start():
    """Background thread: download if needed, load model, then start streaming."""
    global model
    download_model()
    if not model_is_valid():
        send_to_gui("log", "No valid model — pick another or add model files.")
        return
    try:
        with model_lock:
            if model is None:
                model = Model(MODEL_DIR)
                send_to_gui("log", "Model loaded.")
        _start_streaming()
    except Exception as e:
        send_to_gui("log", f"Model load failed: {e}")


def do_start_listening():
    global state
    try:
        if model is None:
            send_to_gui("log", "Loading model...")
            threading.Thread(target=_load_model_and_start, daemon=True).start()
            return
        _start_streaming()
    except Exception as e:
        send_to_gui("log", f"Error: {e}")
        state = STATE_IDLE
        send_to_gui("state", state)


def do_stop_listening():
    global state, rec, stream, prev_state, active_prediction, recent_text
    if state in (STATE_DICTATION, STATE_COMMAND):
        prev_state = state
    state = STATE_IDLE
    active_prediction = None
    recent_text = ""
    send_to_gui("prediction", "")
    if stream is not None:
        try:
            stream.stop(); stream.close()
        except Exception:
            pass
        stream = None
    with lock:
        rec = None
    send_to_gui("log", "Stopped.")
    send_to_gui("state", state)


def do_enter_dictation():
    """Switch from command mode to dictation mode."""
    global state, rec, last_speech_time
    if state == STATE_COMMAND:
        state = STATE_DICTATION
        last_speech_time = time.time()
        with lock:
            if model is not None:
                rec = KaldiRecognizer(model, SAMPLE_RATE)
                rec.SetWords(True)
        send_to_gui("log", "Dictation mode — speak now (say 'command mode' to switch back)")
        send_to_gui("state", state)


def do_enter_command():
    """Switch from dictation mode to command mode."""
    global state, rec, active_prediction
    if state == STATE_DICTATION:
        state = STATE_COMMAND
        active_prediction = None
        send_to_gui("prediction", "")
        with lock:
            if model is not None:
                rec = KaldiRecognizer(model, SAMPLE_RATE)
                rec.SetWords(True)
        send_to_gui("log", "Command mode — say 'type' to dictate")
        send_to_gui("state", state)


def do_go_to_sleep():
    global state, prev_state, active_prediction
    if state in (STATE_DICTATION, STATE_COMMAND):
        prev_state = state
    state = STATE_SLEEPING
    active_prediction = None
    send_to_gui("prediction", "")
    send_to_gui("log", "Sleeping... (say 'wake up')")
    send_to_gui("state", state)


def do_wake_up():
    global state, rec, last_speech_time
    state = prev_state if prev_state in (STATE_DICTATION, STATE_COMMAND) else STATE_COMMAND
    last_speech_time = time.time()
    with lock:
        if model is not None:
            rec = KaldiRecognizer(model, SAMPLE_RATE)
            rec.SetWords(True)
    send_to_gui("log", f"Awake! [{STATE_LABELS[state]}]")
    send_to_gui("state", state)


# =====================================================================
#  GUI — compact, bottom-right
# =====================================================================

class VoiceTypeGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title(APP_NAME)
        self.root.configure(bg="#1e1e1e")
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.protocol("WM_TAKE_FOCUS", self.show_window)
        self.window_visible = True

        # Position bottom-right
        self.root.update_idletasks()
        w, h = 360, 400
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = sw - w - 20
        y = sh - h - 60
        self.root.geometry(f"{w}x{h}+{x}+{y}")

        # --- Status banner ---
        self.banner = tk.Frame(self.root, height=48, bg="#cc0000")
        self.banner.pack(fill="x", padx=6, pady=(6, 0))
        self.banner.pack_propagate(False)
        self.status_label = tk.Label(
            self.banner, text="IDLE", font=("Segoe UI", 18, "bold"),
            fg="white", bg="#cc0000"
        )
        self.status_label.pack(expand=True)

        # --- Command flash ---
        self.cmd_label = tk.Label(
            self.root, text="", font=("Segoe UI", 12, "bold"),
            fg="#00ccff", bg="#1e1e1e"
        )
        self.cmd_label.pack(fill="x", padx=8, pady=2)

        # --- Live partial preview ---
        self.partial_label = tk.Label(
            self.root, text="", font=("Segoe UI", 10, "italic"),
            fg="#999999", bg="#1e1e1e", anchor="w", wraplength=340
        )
        self.partial_label.pack(fill="x", padx=10, pady=0)

        # --- Autocomplete prediction ---
        self.prediction_label = tk.Label(
            self.root, text="", font=("Segoe UI", 10, "italic"),
            fg="#6688bb", bg="#1e1e1e", anchor="w", wraplength=340
        )
        self.prediction_label.pack(fill="x", padx=10, pady=(0, 2))

        # --- Log ---
        log_frame = tk.Frame(self.root, bg="#1e1e1e")
        log_frame.pack(fill="both", expand=True, padx=6, pady=2)
        self.log = tk.Text(
            log_frame, font=("Consolas", 9), bg="#2d2d2d", fg="#aaaaaa",
            wrap="word", state="disabled", relief="flat", padx=6, pady=4, height=6
        )
        self.log.pack(fill="both", expand=True)

        # --- Speech model ---
        model_frame = tk.Frame(self.root, bg="#1e1e1e")
        model_frame.pack(fill="x", padx=8, pady=(0, 2))
        tk.Label(
            model_frame, text="Speech model:", font=("Segoe UI", 8),
            fg="#888888", bg="#1e1e1e",
        ).pack(side="left")
        self.model_id_by_label = {v["label"]: k for k, v in MODEL_PRESETS.items()}
        self.model_labels = [MODEL_PRESETS[k]["label"] for k in ("en_giga", "indian_en") if k in MODEL_PRESETS]
        self.model_var = tk.StringVar(value=MODEL_PRESETS[selected_model_preset]["label"])
        self.model_combo = ttk.Combobox(
            model_frame, textvariable=self.model_var, values=self.model_labels,
            state="readonly", width=32, font=("Segoe UI", 8),
        )
        self.model_combo.pack(side="left", padx=(6, 0))
        self.model_combo.bind("<<ComboboxSelected>>", self.on_model_preset_selected)

        # --- Buttons ---
        btn_frame = tk.Frame(self.root, bg="#1e1e1e")
        btn_frame.pack(fill="x", padx=6, pady=(2, 4))
        btn_kw = dict(font=("Segoe UI", 9, "bold"), relief="flat",
                      fg="white", cursor="hand2", bd=0, padx=8, pady=4)

        self.btn_start = tk.Button(btn_frame, text="Start", bg="#00aa00",
                                   activebackground="#008800", command=self.on_start, **btn_kw)
        self.btn_start.pack(side="left", expand=True, fill="x", padx=1)

        self.btn_sleep = tk.Button(btn_frame, text="Sleep", bg="#cc9900",
                                   activebackground="#aa7700", command=self.on_sleep, **btn_kw)
        self.btn_sleep.pack(side="left", expand=True, fill="x", padx=1)

        self.btn_mode = tk.Button(btn_frame, text="Mode", bg="#0066ff",
                                  activebackground="#0044cc", command=self.on_mode, **btn_kw)
        self.btn_mode.pack(side="left", expand=True, fill="x", padx=1)

        self.btn_stop = tk.Button(btn_frame, text="Stop", bg="#cc0000",
                                  activebackground="#aa0000", command=self.on_stop, **btn_kw)
        self.btn_stop.pack(side="left", expand=True, fill="x", padx=1)

        # --- Startup checkbox (Windows only) ---
        self.startup_var = tk.IntVar()
        self.startup_cb = tk.Checkbutton(
            self.root, text="Start on boot", variable=self.startup_var,
            command=self.toggle_startup, font=("Segoe UI", 8),
            fg="#888888", bg="#1e1e1e", selectcolor="#1e1e1e",
            activebackground="#1e1e1e", activeforeground="#aaaaaa"
        )
        if IS_WINDOWS:
            self.startup_cb.pack(anchor="w", padx=8)
            self.startup_var.set(1 if self.startup_shortcut_exists() else 0)

        # --- Auto-start on open ---
        self.autostart_var = tk.IntVar()
        self.autostart_cb = tk.Checkbutton(
            self.root, text="Auto-start on open", variable=self.autostart_var,
            command=self.toggle_auto_start, font=("Segoe UI", 8),
            fg="#888888", bg="#1e1e1e", selectcolor="#1e1e1e",
            activebackground="#1e1e1e", activeforeground="#aaaaaa"
        )
        self.autostart_cb.pack(anchor="w", padx=8)
        self.autostart_var.set(1 if load_auto_start() else 0)

        # --- Mic gain ---
        gain_frame = tk.Frame(self.root, bg="#1e1e1e")
        gain_frame.pack(fill="x", padx=8, pady=(0, 2))
        tk.Label(
            gain_frame, text="Mic gain:", font=("Segoe UI", 8),
            fg="#888888", bg="#1e1e1e",
        ).pack(side="left")
        self.gain_var = tk.DoubleVar(value=mic_gain)
        self.gain_scale = tk.Scale(
            gain_frame, from_=1.0, to=5.0, resolution=0.5, orient="horizontal",
            variable=self.gain_var, command=self.on_gain_changed,
            bg="#1e1e1e", fg="#888888", highlightthickness=0,
            length=120, showvalue=1, font=("Segoe UI", 8),
        )
        self.gain_scale.pack(side="left", padx=(6, 0))

        # --- Hotkey hint ---
        tk.Label(self.root, text="Ctrl+Shift+V = Start/Stop  |  C = Mode",
                 font=("Segoe UI", 7), fg="#555555", bg="#1e1e1e").pack(pady=(0, 2))

        self.cmd_flash_after = None
        self.minimize_after_id = None

        # --- System tray icon ---
        self.tray_icon = None
        self.setup_tray()

        self.poll_queue()

        # Auto-start listening if configured
        if load_auto_start():
            self.root.after(800, self.on_start)

    def on_model_preset_selected(self, event=None):
        label = self.model_var.get()
        preset_id = self.model_id_by_label.get(label)
        if not preset_id:
            return
        global selected_model_preset
        if preset_id == selected_model_preset:
            return
        self.root.after(0, lambda p=preset_id: self._switch_model_preset(p))

    def _switch_model_preset(self, preset_id):
        global selected_model_preset, MODEL_DIR, model
        do_stop_listening()
        selected_model_preset = preset_id
        save_model_choice(preset_id)
        MODEL_DIR = resolve_model_dir_for(preset_id)
        model = None
        send_to_gui("log", f"Switching model to {MODEL_PRESETS[preset_id]['label']}…")
        threading.Thread(target=self._load_model_thread, daemon=True).start()

    def _load_model_thread(self):
        global model
        download_model()
        if not model_is_valid():
            send_to_gui("log", "Model files not found for this preset.")
            return
        try:
            model = Model(MODEL_DIR)
            send_to_gui("log", f"Ready — {MODEL_PRESETS[selected_model_preset]['label']}")
        except Exception as e:
            send_to_gui("log", f"Model load error: {e}")

    # --- Tray icon ---
    def create_tray_image(self, color):
        size = 64
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.ellipse([8, 8, 56, 56], fill=color)
        return img

    def setup_tray(self):
        icon = pystray.Icon(
            APP_NAME,
            icon=self.create_tray_image((200, 0, 0)),
            title="VoiceType: Idle",
            menu=pystray.Menu(
                pystray.MenuItem("Show", self.show_window),
                pystray.MenuItem("Start Listening", self.tray_start),
                pystray.MenuItem("Stop Listening", self.tray_stop),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Quit", self.tray_quit),
            ),
        )
        self.tray_icon = icon
        threading.Thread(target=icon.run, daemon=True).start()

    def update_tray(self, new_state):
        if self.tray_icon is None:
            return
        try:
            colors = {
                STATE_IDLE: (200, 0, 0),
                STATE_DICTATION: (0, 200, 0),
                STATE_COMMAND: (0, 100, 255),
                STATE_SLEEPING: (255, 200, 0),
            }
            titles = {
                STATE_IDLE: "VoiceType: Idle",
                STATE_DICTATION: "VoiceType: Dictating",
                STATE_COMMAND: "VoiceType: Command",
                STATE_SLEEPING: "VoiceType: Sleeping",
            }
            self.tray_icon.icon = self.create_tray_image(colors.get(new_state, (200, 0, 0)))
            self.tray_icon.title = titles.get(new_state, APP_NAME)
        except Exception:
            pass

    def tray_start(self, icon, item):
        send_to_gui("tray_start", "")

    def tray_stop(self, icon, item):
        send_to_gui("tray_stop", "")

    def tray_quit(self, icon, item):
        global stop_app
        stop_app = True
        do_stop_listening()
        icon.stop()
        self.root.after(100, self.root.destroy)

    # --- Window minimize / show ---
    def minimize_to_tray(self):
        """Hide the window, keep tray icon."""
        self.root.withdraw()
        self.window_visible = False
        send_to_gui("log", "Window minimized to system tray (right-click tray icon to show)")

    def show_window(self):
        """Restore the window from tray."""
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()
        self.window_visible = True
        # Cancel pending minimize
        if self.minimize_after_id:
            self.root.after_cancel(self.minimize_after_id)
            self.minimize_after_id = None

    def schedule_minimize(self, delay_ms=3000):
        """Auto-minimize to tray after delay when idle."""
        if self.minimize_after_id:
            self.root.after_cancel(self.minimize_after_id)
        self.minimize_after_id = self.root.after(delay_ms, self.minimize_to_tray)

    def poll_queue(self):
        global pending_action, last_speech_time
        if pending_action == "stop":
            pending_action = None
            do_stop_listening()
        elif pending_action == "sleep":
            pending_action = None
            do_go_to_sleep()
        elif pending_action == "type":
            pending_action = None
            do_enter_dictation()
        elif pending_action == "command":
            pending_action = None
            do_enter_command()
        elif pending_action == "wake":
            pending_action = None
            do_wake_up()

        # Auto-sleep after no voice detected for a while
        if state in (STATE_DICTATION, STATE_COMMAND):
            if time.time() - last_speech_time > AUTO_SLEEP_SECONDS:
                send_to_gui("log", f"Auto-sleep after {AUTO_SLEEP_SECONDS}s of silence")
                do_go_to_sleep()

        # --- Autocomplete: trigger prediction after silence in DICTATION mode ---
        if (state == STATE_DICTATION and autocomplete_enabled
                and active_prediction is None and not prediction_pending
                and not gpt2_loading and recent_text
                and time.time() - last_speech_time > PREDICTION_SILENCE_SECONDS):
            # Fast lane: try N-gram first (instant)
            ngram_result = ngram_predict(recent_text)
            if ngram_result:
                active_prediction = ngram_result
                send_to_gui("prediction", ngram_result)
            else:
                # Smart lane: GPT-2 in background thread
                threading.Thread(target=request_prediction, daemon=True).start()

        try:
            while True:
                event, data = gui_queue.get_nowait()
                if event == "state":
                    self.update_state(data)
                elif event == "heard":
                    self.add_log(f'Typed: "{data}"')
                elif event == "partial":
                    self.partial_label.config(
                        text=f'  hearing: "{data}"' if data else ""
                    )
                elif event == "command":
                    self.flash_command(data)
                elif event == "log":
                    self.add_log(data)
                elif event == "mode_toggle":
                    self.on_mode()
                elif event == "tray_start":
                    self.show_window()
                    if state == STATE_SLEEPING:
                        do_wake_up()
                    elif state == STATE_IDLE:
                        do_start_listening()
                elif event == "tray_stop":
                    if state != STATE_IDLE:
                        do_stop_listening()
        except queue.Empty:
            pass

        if not stop_app:
            self.root.after(50, self.poll_queue)

    def update_state(self, new_state):
        global state
        color = STATE_COLORS.get(new_state, "#cc0000")
        label = STATE_LABELS.get(new_state, "IDLE")
        self.banner.configure(bg=color)
        self.status_label.configure(text=label, bg=color)
        self.partial_label.config(text="")
        self.update_tray(new_state)

        if new_state == STATE_IDLE:
            self.btn_start.config(state="normal", text="Start")
            self.btn_sleep.config(state="disabled")
            self.btn_stop.config(state="disabled")
            # Auto-minimize when idle
            self.schedule_minimize(3000)
        elif new_state == STATE_SLEEPING:
            self.btn_start.config(state="normal", text="Wake")
            self.btn_sleep.config(state="disabled")
            self.btn_stop.config(state="normal")
            self.schedule_minimize(3000)
        else:
            # Active — show window, cancel minimize
            self.btn_start.config(state="disabled", text="Start")
            self.btn_sleep.config(state="normal")
            self.btn_stop.config(state="normal")
            if not self.window_visible:
                self.show_window()

    def flash_command(self, text):
        self.cmd_label.config(text=text)
        if self.cmd_flash_after:
            self.root.after_cancel(self.cmd_flash_after)
        self.cmd_flash_after = self.root.after(2000, lambda: self.cmd_label.config(text=""))

    def add_log(self, text):
        self.log.config(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.config(state="disabled")

    # --- Startup on boot ---
    def get_startup_folder(self):
        return os.path.join(os.environ.get("APPDATA", ""),
                            "Microsoft", "Windows", "Start Menu",
                            "Programs", "Startup")

    def startup_shortcut_exists(self):
        path = os.path.join(self.get_startup_folder(), APP_NAME + ".vbs")
        return os.path.exists(path)

    def toggle_startup(self):
        startup_folder = self.get_startup_folder()
        vbs_path = os.path.join(startup_folder, APP_NAME + ".vbs")
        if self.startup_var.get():
            if getattr(sys, "frozen", False):
                exe = sys.executable.replace('"', '""')
                vbs_content = (
                    "Set ws = CreateObject(\"WScript.Shell\")\n"
                    f'ws.Run Chr(34) & "{exe}" & Chr(34), 0, False\n'
                )
            else:
                script_path = os.path.join(SCRIPT_DIR, "voice_type.py")
                vbs_content = (
                    f'Set ws = CreateObject("WScript.Shell")\n'
                    f'ws.Run "pythonw ""{script_path}""", 0, False\n'
                )
            with open(vbs_path, "w") as f:
                f.write(vbs_content)
            send_to_gui("log", "Added to startup.")
        else:
            if os.path.exists(vbs_path):
                os.remove(vbs_path)
                send_to_gui("log", "Removed from startup.")

    def toggle_auto_start(self):
        save_auto_start(self.autostart_var.get())

    def on_gain_changed(self, val):
        global mic_gain
        mic_gain = float(val)
        save_mic_gain(mic_gain)

    def on_start(self):
        if state == STATE_SLEEPING:
            do_wake_up()
        elif state == STATE_IDLE:
            do_start_listening()

    def on_sleep(self):
        if state in (STATE_DICTATION, STATE_COMMAND):
            do_go_to_sleep()

    def on_mode(self):
        global state, prev_state
        if state == STATE_DICTATION:
            state = STATE_COMMAND; prev_state = STATE_COMMAND
        elif state == STATE_COMMAND:
            state = STATE_DICTATION; prev_state = STATE_DICTATION
        elif state == STATE_SLEEPING:
            prev_state = STATE_COMMAND if prev_state == STATE_DICTATION else STATE_DICTATION
        elif state == STATE_IDLE:
            prev_state = STATE_COMMAND if prev_state == STATE_DICTATION else STATE_DICTATION
        else:
            state = STATE_DICTATION
        send_to_gui("log", f"Mode: {STATE_LABELS.get(state, state)}")
        send_to_gui("state", state)

    def on_stop(self):
        if state != STATE_IDLE:
            do_stop_listening()

    def on_close(self):
        global stop_app
        stop_app = True
        do_stop_listening()
        if self.tray_icon:
            self.tray_icon.stop()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


def main():
    if IS_WINDOWS:
        try:
            ctypes.windll.kernel32.SetConsoleTitleW(APP_NAME)
        except Exception:
            pass

    # Model is loaded lazily on first Start to avoid long startup delays.

    hotkey_toggle = keyboard.HotKey(
        {keyboard.Key.ctrl, keyboard.Key.shift, keyboard.KeyCode.from_char("v")},
        lambda: (do_stop_listening() if state != STATE_IDLE else do_start_listening()),
    )
    hotkey_mode = keyboard.HotKey(
        {keyboard.Key.ctrl, keyboard.Key.shift, keyboard.KeyCode.from_char("c")},
        lambda: send_to_gui("mode_toggle", ""),
    )

    def on_press(key):
        hotkey_toggle.press(key); hotkey_mode.press(key)

    def on_release(key):
        hotkey_toggle.release(key); hotkey_mode.release(key)

    listener = keyboard.Listener(on_press=on_press, on_release=on_release)
    listener.start()

    app = VoiceTypeGUI()
    app.run()

    stop_app = True
    do_stop_listening()
    listener.stop()


if __name__ == "__main__":
    main()