#!/usr/bin/env bash
# Build a native "Yap.app" bundle that launches the menu-bar app using this
# project's uv-managed virtualenv, then install it to /Applications.
#
# We build the bundle by hand rather than with py2app: py2app conflicts with the
# project's PEP 621 pyproject metadata, and a launcher bundle is simpler, fully
# transparent, and plays nicely with macOS TCC (mic/Accessibility) and login items.
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV_PY="$PROJECT_DIR/.venv/bin/python"
APP_NAME="Yap"
APP="$PROJECT_DIR/dist/$APP_NAME.app"

if [[ ! -x "$VENV_PY" ]]; then
  echo "error: venv python not found at $VENV_PY — run 'uv sync' first." >&2
  exit 1
fi

echo "Building $APP_NAME.app ..."
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"

# --- Info.plist ---
cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>            <string>$APP_NAME</string>
    <key>CFBundleDisplayName</key>     <string>$APP_NAME</string>
    <key>CFBundleExecutable</key>      <string>yap</string>
    <key>CFBundleIdentifier</key>      <string>com.yap.dictation</string>
    <key>CFBundlePackageType</key>     <string>APPL</string>
    <key>CFBundleShortVersionString</key> <string>0.1.0</string>
    <key>CFBundleVersion</key>         <string>0.1.0</string>
    <key>LSUIElement</key>             <true/>
    <key>LSMinimumSystemVersion</key>  <string>13.0</string>
    <key>NSMicrophoneUsageDescription</key>
        <string>Yap transcribes your speech on-device.</string>
    <key>NSAppleEventsUsageDescription</key>
        <string>Yap pastes transcribed text into the focused field.</string>
</dict>
</plist>
PLIST

# --- launcher executable ---
cat > "$APP/Contents/MacOS/yap" <<LAUNCH
#!/bin/bash
# Launch the Yap menu-bar app from the project's virtualenv.
export YAP_HOME="$PROJECT_DIR"
exec "$VENV_PY" -m yap
LAUNCH
chmod +x "$APP/Contents/MacOS/yap"

echo "Installing to /Applications ..."
rm -rf "/Applications/$APP_NAME.app"
cp -R "$APP" "/Applications/"
# Nudge LaunchServices to register the freshly installed bundle.
/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister \
  -f "/Applications/$APP_NAME.app" 2>/dev/null || true

echo
echo "Done. '$APP_NAME' is installed in /Applications."
echo "Launch it from Spotlight/Launchpad; look for the 🦜 in your menu bar."
echo "First run asks for Microphone and Accessibility permissions — grant both."
echo "NOTE: the bundle runs from this project's venv at $PROJECT_DIR/.venv"
echo "Keep the project in place; if you move it, re-run this script."
