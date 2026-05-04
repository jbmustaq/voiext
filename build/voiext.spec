# -*- mode: python ; coding: utf-8 -*-
# Run from repository root: py -m PyInstaller build/voiext.spec
import os

block_cipher = None
_spec_dir = os.path.dirname(os.path.abspath(SPEC))
root = os.path.dirname(_spec_dir)

a = Analysis(
    [os.path.join(root, "voice_type.py")],
    pathex=[root],
    binaries=[],
    datas=[
        (os.path.join(root, "model"), os.path.join("models", "en_giga")),
        (os.path.join(root, "model-indian-backup"), os.path.join("models", "indian_en")),
    ],
    hiddenimports=["sounddevice", "vosk", "pynput", "pystray", "PIL._tkinter_finder"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="VoiceType",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="VoiceType",
)
