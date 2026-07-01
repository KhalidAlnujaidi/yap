#!/usr/bin/env bash
# Yap — one-line installer for Apple Silicon Macs.
#
#   curl -fsSL https://raw.githubusercontent.com/__GH_USER__/yap/main/install.sh | bash
#
# Installs prerequisites (Homebrew ffmpeg + uv if missing), clones Yap, builds
# the model environment, and installs "Yap.app" into /Applications.
set -euo pipefail

REPO="https://github.com/__GH_USER__/yap.git"
YAP_DIR="${YAP_DIR:-$HOME/.local/share/yap}"

say() { printf "\033[1;32m🦜 %s\033[0m\n" "$*"; }
die() { printf "\033[1;31merror: %s\033[0m\n" "$*" >&2; exit 1; }

# --- 1. Platform checks ------------------------------------------------------
[[ "$(uname -s)" == "Darwin" ]] || die "Yap is macOS-only right now."
[[ "$(uname -m)" == "arm64" ]] || die "Yap requires Apple Silicon (M-series). Intel isn't supported yet — PRs welcome!"

# --- 2. Homebrew + ffmpeg ----------------------------------------------------
if ! command -v brew >/dev/null 2>&1; then
  die "Homebrew not found. Install it from https://brew.sh then re-run this script."
fi
if ! command -v ffmpeg >/dev/null 2>&1; then
  say "Installing ffmpeg via Homebrew ..."
  brew install ffmpeg
fi

# --- 3. uv (Python package manager) -----------------------------------------
if ! command -v uv >/dev/null 2>&1; then
  say "Installing uv ..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi
command -v uv >/dev/null 2>&1 || die "uv install failed; open a new terminal and re-run."

# --- 4. Fetch Yap ------------------------------------------------------------
if [[ -d "$YAP_DIR/.git" ]]; then
  say "Updating existing Yap in $YAP_DIR ..."
  git -C "$YAP_DIR" pull --ff-only
else
  say "Cloning Yap into $YAP_DIR ..."
  mkdir -p "$(dirname "$YAP_DIR")"
  git clone --depth 1 "$REPO" "$YAP_DIR"
fi

# --- 5. Build the environment (downloads the speech model on first run) ------
say "Setting up the Python environment (this pulls the ~1–2.5 GB speech model once) ..."
cd "$YAP_DIR"
uv sync

# --- 6. Build & install the app ---------------------------------------------
say "Building Yap.app and installing to /Applications ..."
bash "$YAP_DIR/scripts/build_app.sh"

say "Done! Launch 'Yap' from Spotlight and look for 🦜 in your menu bar."
say "First launch will ask for Microphone + Accessibility — grant both, then just talk."
