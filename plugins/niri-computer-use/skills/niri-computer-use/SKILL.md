---
name: niri-computer-use
description: Observe and operate local niri Wayland desktop applications through the niri_computer_use MCP tools, including screenshots, accessibility controls, window targeting, keyboard, pointer and clipboard input.
---

Use `niri_computer_use` for the user's requested GUI task. The backend shares
the user's active desktop, pointer and focus. Actions can switch workspaces.

## Observation and targeting

Call `doctor` if the desktop's readiness is unknown. If AT-SPI is disabled,
`setup_accessibility` enables it. Newly launched apps inherit the environment;
existing Chromium/Electron apps may need restarting with accessibility enabled.
Do not restart a user's application with unsaved work automatically.

Find running windows with `list_windows`; find installed apps with
`list_desktop_apps` and start them using `launch_app(desktop_id)`.
Prefer exact `window_id`, especially when an app has multiple windows.

Start with `get_app_state(window_id, desktop_screenshot: true)` on niri.
This scopes the accessibility tree to the app while explicitly capturing the
entire desktop. Other windows may appear in this image. It works when niri
omits window positions. `desktop_screenshot: false` requests a strict window
crop and may fail when bounds are unknown. Use `include_screenshot: false`
when the control tree provides enough information.

Element indices refer to the most recent state, so refresh after navigation,
dialog changes and actions that change the control hierarchy. Prefer semantic
actions and `set_value` when the app exposes usable AT-SPI interfaces.
Use `focus_element` to focus an observed editable control and verify its state.
Chromium may omit EditableText; Firefox may acknowledge a write without changing
the DOM. Verify the actual value. If semantic replacement fails, explicitly
focus the text field, send Ctrl+A, then type or paste and verify the result.

## Display power and brightness

Keep the user's Mod+B binding unchanged. Read-only screenshots work while
monitors are powered off, but niri wakes them on pointer/uinput events.
Before any GUI input, run the installed session helper using the shell:

```sh
python "$HOME/.local/share/niri-computer-use/bin/niri-desktop-session.py" begin
```

It records display power and brightness. If entry was powered off, it sets
the minimum nonzero backlight level without waking the monitor. Only when
GUI input is needed, run the same helper with `wake`; never wake first and
dim afterwards. Then use the MCP tools normally. On success, error, or user
cancellation, always run the helper with `end` before yielding. This powers
off first and restores the saved brightness, avoiding a bright flash.
If entry was already powered on, brightness and power are left unchanged.
Use `status` to verify the result. If begin fails (for example an external
monitor has no controllable backlight), stop before input and explain.
For unattended workflows pass the same `--owner-pid PID` to begin/wake/end,
using the long-lived agent process PID, not a short-lived shell: a watchdog
restores the state after that process exits. Ownerless interactive sessions
require explicit end; this is a skill workflow, not automatic MCP interception.

## Coordinates and input

For full-desktop images, divide preview x/y by returned `scale`, then pass
absolute coordinates (`relative: false`). The screenshot coordinate dimensions
can differ from niri logical output size; never multiply by output scale again.
If window bounds are unavailable, do not use window-relative coordinates or
targeted scroll without x/y. Supply an observed absolute point inside the
target window and include its window_id in click/scroll/keyboard calls.

`click(button: "right")` performs a secondary click. `drag` takes absolute
start/end coordinates and an optional exact window_id. Inspect a fresh image
first. Never invent missing window geometry. Pointer actions use niri's native
Wayland virtual-pointer protocol; shortcuts use a persistent uinput keyboard.

Use Linux shortcuts (`Ctrl`, rather than macOS `Cmd`). `press_key` accepts
names such as Ctrl+L, Ctrl+Shift+P, Enter and ArrowLeft. Literal `type_text`
supports Unicode through wtype. `select_text` takes Unicode character offsets
from a fresh AT-SPI Text element and verifies the selection; unsupported apps
need observed keyboard selection instead.
For a single-line field, Home followed by Shift+ArrowRight can select an observed
prefix. Do not assume code-point offsets equal grapheme/keyboard steps for
combining characters or emoji; verify the resulting selection.

`paste(text, html?, window_id)` offers plain text plus optional HTML and restores
the previous clipboard formats. Plain-text consumers choose the text offer.
Use `key: "Ctrl+Shift+V"` only when the destination requires it. For a slow
consumer increase `restore_delay_ms` (100–5000); verify actual contents after
the call. Clipboard errors are not evidence that text was inserted.

## Verification

After each meaningful operation, inspect fresh state, visible content or the
task's result file. Successful input delivery alone does not prove the task
succeeded. Stop when the requested result is observed or report the concrete
missing capability. niri background/locked-desktop control and the official
@Computer UI are outside this plugin's capability.
