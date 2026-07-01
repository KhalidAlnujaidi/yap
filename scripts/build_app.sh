#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

echo "Building .app with py2app (alias mode for speed on first try)..."
rm -rf build dist
uv run python setup.py py2app -A   # -A = alias mode: fast, references the venv

echo "Installing to /Applications ..."
rm -rf "/Applications/Parakeet Dictation.app"
cp -R "dist/Parakeet Dictation.app" "/Applications/"

echo "Done. Launch from /Applications or Spotlight."
echo "NOTE: alias-mode bundle depends on this project's venv staying in place."
echo "For a fully standalone bundle, run: uv run python setup.py py2app"
