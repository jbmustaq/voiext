#!/usr/bin/env bash
# Run on Linux (same arch as target users). Produces dist/VoiceType/ and a tarball.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

python3 -m pip install --upgrade pip
python3 -m pip install "pyinstaller>=6.0" -r requirements.txt

python3 -m PyInstaller build/voiext.spec --noconfirm --clean

test -d dist/VoiceType

OUT="dist/VoiceType-Linux-x86_64-models.tar.gz"
# If you build on arm64, rename the artifact accordingly.
tar -czvf "$OUT" -C dist VoiceType
echo "Done: $OUT"
echo "Upload as a GitHub Release asset."
