#!/bin/zsh

cd -- "$(dirname -- "$0")" || exit 1

LOG_FILE="$PWD/run_downloader_mac.log"
{
  print "[$(date '+%Y-%m-%d %H:%M:%S')] Starting OpenDART launcher"

  if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python3)"
  elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python)"
  else
    print "Python was not found."
    print "Install Python 3.10 or newer, then run this file again."
    print "Download: https://www.python.org/downloads/macos/"
    print
    print "Press Enter to close."
    read -r _
    exit 1
  fi

  print "Using $PYTHON_BIN"
  "$PYTHON_BIN" opendart_gui.py
  EXIT_CODE=$?
  print "Exit code: $EXIT_CODE"

  if [ "$EXIT_CODE" -ne 0 ]; then
    print
    print "The app exited with an error. See:"
    print "$LOG_FILE"
    print
    print "Press Enter to close."
    read -r _
  fi

  exit "$EXIT_CODE"
} 2>&1 | tee "$LOG_FILE"
