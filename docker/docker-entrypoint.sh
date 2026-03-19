#!/bin/sh
set -eu

DISPLAY_VALUE="${DISPLAY:-:99}"
SCREEN_WIDTH="1920"
SCREEN_HEIGHT="1080"
SCREEN_DEPTH="24"

export DISPLAY="$DISPLAY_VALUE"
rm -f "/tmp/.X${DISPLAY_VALUE#:}-lock"

Xvfb "$DISPLAY" -screen 0 "${SCREEN_WIDTH}x${SCREEN_HEIGHT}x${SCREEN_DEPTH}" -ac +extension RANDR >/tmp/xvfb.log 2>&1 &
sleep 2

exec "$@"
