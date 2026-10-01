# niri Computer Use

Local Codex plugin based on MIT-licensed [computer-use-linux v0.7.7](https://github.com/agent-sh/computer-use-linux/tree/v0.7.7).
Upstream commit: `418892f10e6840c45d92e4911f499f2e33994c94`.

Install with `bash scripts/install-niri.sh`. Requires Rust, Codex, niri,
`grim`, `wtype`, `gio`, Python 3, `brightnessctl`, AT-SPI and access to
`/dev/uinput`. The script builds pinned dependencies, installs both binaries
under `${XDG_DATA_HOME:-~/.local/share}/niri-computer-use/bin`, registers the
`niri-local` marketplace and enables accessibility. It does not publish to GitHub.
Start a new Codex conversation to load the plugin. Invoke `$niri-computer-use`
or request a niri GUI task. No OpenAI API key is required by the local server.

## Added MCP interfaces

| Interface | Behavior |
| --- | --- |
| `list_desktop_apps()` | XDG desktop IDs, names, app IDs and launch paths |
| `launch_app(desktop_id, app_id?, wait_timeout_ms?)` | Focus one existing window, or launch with gio and verify focus; refuse ambiguous matches |
| `select_text(element_index?, element_identifier?, role?, name?, start_offset, end_offset)` | AT-SPI Text range selection; offsets count Unicode characters |
| `focus_element(element_index?, element_identifier?, role?, name?)` | AT-SPI Component focus with Focused-state verification |
| `paste(text, html?, window_id/app_id/pid/title, key?, restore_delay_ms?)` | Offer text/HTML, send paste shortcut, restore original MIME data |
| `get_app_state(..., desktop_screenshot: true)` | App-scoped tree plus explicitly full-desktop image |
| `press_key(key, window_id?)` | Persistent uinput keyboard on niri; wtype chords on other compatible Wayland desktops |

`paste` requires an explicit target. Clipboard snapshot is limited to 64 MIME
formats and 16 MiB total; unreadable/oversized contents abort before overwrite.
Paste restores after 500 ms by default, configurable from 100–5000 ms. Verify
the destination's contents; a delivered shortcut is not an insertion guarantee.

## Mac capability mapping

| Mac operation | niri equivalent |
| --- | --- |
| List/launch apps | `list_apps`, `list_desktop_apps`, `launch_app` |
| App screenshot + accessibility state | `get_app_state` with explicit desktop screenshot |
| Click/secondary click | `click`, `button: right` |
| Drag/scroll | `drag`, `scroll` |
| Keys/Unicode input | `press_key`, `type_text` |
| Invoke AX action/set value | `perform_action`, `set_value` via AT-SPI |
| Select text | `select_text` or verified keyboard selection |
| Plain/rich paste | `paste` with text and optional HTML |
| Background/locked desktop, official UI | Not included in agreed functional target |

Control shares the active desktop. Exact window crops may be unavailable when
niri omits window bounds; full-screen coordinates are explicit, never guessed.
Multi-output/mixed-scale configurations need their own calibration.

On niri, screenshots use `grim`: the GNOME Screenshot compatibility interface
can return a mismatched canvas under fractional scaling. The local 1.5-scale
pointer calibration checks actual click positions against the screenshot.
Chromium/Electron may not implement writable accessibility text; Firefox may
acknowledge a semantic write without changing the document. Use explicitly
focused keyboard replacement/selection and verify the destination. Acceptance
reports distinguish native semantic interfaces from functional fallback paths.

Run `python scripts/niri-e2e.py --help` for the observable desktop acceptance
suite. Unit tests: `cargo test --locked`.
Cross-toolkit suite: `python scripts/niri-toolkit-e2e.py --binary target/debug/computer-use-linux`.
No Mac hardware has been tested; the mapping describes interface capability,
not measured cross-platform parity.

The current installed plugin is version 0.1.3. This workstation was tested with
the debug build; the normal installer defaults to an optimized release build.
Portable export: `python scripts/export-niri-plugin.py`. The ZIP describes a
local plugin and requires the separately installed runtime; it is not a bundled
cross-platform executable and has not been uploaded or publicly submitted.

## Local acceptance

The installation uses the compatibility manifest for Codex CLI 0.159.2. This
version discovers skills but drops MCP configuration when a portable root
`plugin.json` overrides the compatibility manifest. The portable export source
is kept separately in `packaging/niri-computer-use.plugin.json`; do not copy it
into the installed source directory on this CLI version.

Acceptance records under `artifacts/` cover GTK (21 cases × 3), Qt (10 × 3),
Electron (10 × 3), Firefox (10 × 3), application launch/reuse (3 × 3), and
new Codex app-server discovery plus a read-only `list_windows` call.
All 153 GUI cases passed, plus 9 launch/reuse checks. The Rust suite passed
379 tests; strict all-target Clippy, formatting, and skill validation passed.
Browser semantic-interface availability is recorded separately from successful
keyboard fallback. Run `python scripts/niri-launch-e2e.py` and
`python scripts/niri-host-e2e.py` to repeat the additional checks.

No separately managed input daemon or login hook is required: Codex starts the
MCP server on demand. A transient clipboard helper keeps restored clipboard
formats available until another application replaces the selection.
Session variables are recovered from the current graphical session. AT-SPI is
persistently enabled through desktop settings. On this host `/dev/uinput` has
the active user's ACL through the installed Steam `uaccess` udev rule; the
standard uinput rule also sets the input group and mode 0660. On another host,
give the active user appropriate uinput access and rerun `doctor`; do not grant
world-writable input-device access. Configuration persistence is inspected;
the user's live desktop has not been rebooted as part of testing.

Three cold-process tests run `doctor`, window listing and application discovery
with only HOME and PATH set. See `artifacts/cold-start.json` and run
`python scripts/niri-cold-start-e2e.py` to repeat them.

Uninstall with `bash scripts/uninstall-niri.sh`. Runtime binaries are retained
for recovery. The source repository and upstream license remain intact.
## Display-off Computer Use

Mod+B retains the original `power-off-monitors` binding. Screenshots work
while powered off; niri pointer and uinput events wake the panel. Plugin
0.1.4 adds a skill-guided `niri-desktop-session.py begin/wake/end` workflow.
Begin saves power/brightness and dims an off built-in panel before input;
wake is used only when input needs it. End blanks before restoring brightness.
Originally-on sessions are not dimmed. Explicit end is mandatory; optional
owner-PID watchdog restores after agent exit. This is not automatic interception
of arbitrary MCP clients. External monitors without controllable brightness
are refused rather than woken at an unknown level.

Verified on this laptop: requested minimum 1/100 (firmware actual floor 7),
then restored 100/100 and DRM connector disabled. A screenshot captured while
off was sent through the WeChat GUI to File Transfer Assistant; private
screenshots are not included in this repository.
