#!/bin/zsh
# Double-click launcher (no DMG required)
set -e
cd "$HOME/social-media-liaison/mac-app"
if [[ ! -d node_modules ]]; then
  echo "Installing desktop app dependencies (first run)…"
  npm install
fi
# Ensure content library exists via python helper if available
if [[ -x "$HOME/social-media-liaison/.venv/bin/python" ]]; then
  "$HOME/social-media-liaison/.venv/bin/python" - <<'PY'
from pathlib import Path
import sys
sys.path.insert(0, str(Path.home() / "social-media-liaison"))
from src.content_library import ensure_library
print("Library:", ensure_library())
PY
fi
echo "Starting Doc Weather Liaison…"
npm start
