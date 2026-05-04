# Build Windows folder distribution (PyInstaller onedir) with both speech models bundled.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host "Installing PyInstaller if needed..."
python -m pip install --upgrade pip | Out-Null
python -m pip install "pyinstaller>=6.0" -r requirements.txt -q

Write-Host "Building VoiceType (this may take several minutes)..."
python -m PyInstaller build/voiext.spec --noconfirm --clean

$dist = Join-Path $Root "dist\VoiceType"
if (-not (Test-Path $dist)) {
    Write-Error "Expected output not found: $dist"
}

$zipName = "VoiceType-Windows-models.zip"
$zipPath = Join-Path $Root "dist\$zipName"
if (Test-Path $zipPath) { Remove-Item $zipPath -Force }
Compress-Archive -Path $dist -DestinationPath $zipPath -Force
Write-Host "Done: $zipPath"
Write-Host "Upload this zip as a GitHub Release asset (do not commit large binaries to git unless using Git LFS)."
