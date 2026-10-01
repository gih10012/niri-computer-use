#!/usr/bin/env bash
set -euo pipefail
codex plugin remove niri-computer-use@niri-local
codex plugin marketplace remove niri-local
echo 'Plugin removed. Runtime binaries are retained under the XDG data directory for recovery.'
echo 'Accessibility settings are shared with other tools; disable them manually only if no longer needed.'
