#!/usr/bin/env python3
"""Runs real desktop actions against a disposable fixture, never user documents."""
import argparse
import base64
import io
import json
import os
from pathlib import Path
import select
import subprocess
import tempfile
import time
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]

class MCP:
    def __init__(self, binary, env=None):
        self.process = subprocess.Popen([str(binary), "mcp"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, bufsize=1, env=env)
        self.counter = 0
        self.request("initialize", {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "niri-e2e", "version": "0.1"}})
        self.process.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
        self.process.stdin.flush()

    def request(self, method, params):
        self.counter += 1
        self.process.stdin.write(json.dumps({"jsonrpc": "2.0", "id": self.counter, "method": method, "params": params}) + "\n")
        self.process.stdin.flush()
        deadline = time.monotonic() + 50
        while time.monotonic() < deadline:
            if not select.select([self.process.stdout], [], [], 1)[0]: continue
            line = self.process.stdout.readline()
            if not line: raise RuntimeError("MCP server exited")
            response = json.loads(line)
            if response.get("id") == self.counter:
                if "error" in response: raise RuntimeError(response["error"])
                return response["result"]
        raise TimeoutError(method)

    def call(self, name, **arguments):
        result = self.request("tools/call", {"name": name, "arguments": arguments})
        if result.get("isError"): raise RuntimeError(result)
        structured = result.get("structuredContent")
        if structured is None:
            for block in result.get("content", []):
                if block["type"] == "text":
                    try: structured = json.loads(block["text"])
                    except json.JSONDecodeError: continue
                    break
        if isinstance(structured, dict) and structured.get("ok") is False: raise RuntimeError(structured.get("message", structured))
        return structured, result

    def close(self):
        self.process.stdin.close()
        try: self.process.wait(timeout=5)
        except subprocess.TimeoutExpired: self.process.terminate(); self.process.wait(timeout=5)

def eventually(read, predicate, timeout=5):
    deadline = time.monotonic() + timeout
    value = None
    while time.monotonic() < deadline:
        value = read()
        if predicate(value): return value
        time.sleep(.08)
    if isinstance(value, dict): value = {k:v for k,v in value.items() if k not in ("document", "keys")}
    raise AssertionError(f"observable state did not satisfy predicate: {str(value)[:800]}")

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, default=ROOT / "target/debug/computer-use-linux")
    parser.add_argument("--report", type=Path, default=ROOT / "artifacts/acceptance.json")
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--debug-images", action="store_true", help="Save full-desktop images on calibration failure; may include private windows")
    args = parser.parse_args()
    platform = json.loads(subprocess.check_output([str(args.binary), "doctor"]))["platform"]
    for key, field in {"WAYLAND_DISPLAY": "wayland_display", "XDG_RUNTIME_DIR": "xdg_runtime_dir", "DBUS_SESSION_BUS_ADDRESS": "dbus_session_bus_address", "XDG_CURRENT_DESKTOP": "xdg_current_desktop", "XDG_SESSION_TYPE": "xdg_session_type", "DISPLAY": "display"}.items():
        if platform.get(field): os.environ.setdefault(key, platform[field])
    sockets = list(Path(os.environ["XDG_RUNTIME_DIR"]).glob(f"niri.{os.environ['WAYLAND_DISPLAY']}.*.sock"))
    if len(sockets) == 1: os.environ.setdefault("NIRI_SOCKET", str(sockets[0]))
    report = {"rounds": args.rounds, "cases": [], "desktop": os.getenv("XDG_CURRENT_DESKTOP"), "mac_hardware_tested": False}
    with tempfile.TemporaryDirectory(prefix="niri-cu-e2e-") as temp:
        state_path = Path(temp) / "state.json"
        previous = subprocess.check_output([str(args.binary.with_name("niri-clipboard")), "snapshot"])
        probe = subprocess.Popen(["python", str(ROOT / "examples/niri-probe.py"), "--state", str(state_path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        mcp = MCP(args.binary)
        def state():
            try: return json.loads(state_path.read_text())
            except (FileNotFoundError, json.JSONDecodeError): return {}
        def record(name, fn):
            start = time.monotonic()
            try:
                fn()
                report["cases"].append({"name": name, "passed": True, "seconds": round(time.monotonic()-start, 3)})
                print("PASS", name, flush=True)
            except Exception as error:
                report["last_probe_state"] = {k:v for k,v in state().items() if k not in ("document", "keys")}
                if args.debug_images and "calibration" in name:
                    _, failed_capture = mcp.call("get_app_state", window_id=wid, desktop_screenshot=True)
                    debug_dir = Path(tempfile.mkdtemp(prefix="niri-cu-pointer-debug-"))
                    for block in image_result["content"]:
                        if block["type"] == "image":
                            (debug_dir / "before.png").write_bytes(base64.b64decode(block["data"]))
                    for block in failed_capture["content"]:
                        if block["type"] == "image":
                            (debug_dir / "after.png").write_bytes(base64.b64decode(block["data"]))
                    print("debug image", debug_dir / "after.png", flush=True)
                report["cases"].append({"name": name, "passed": False, "error": str(error)[:1500]})
                print("FAIL", name, str(error)[:200], flush=True)
                raise
        try:
            tools = mcp.request("tools/list", {})["tools"]
            required = {"launch_app", "paste", "select_text", "list_desktop_apps", "get_app_state", "click", "drag", "scroll", "press_key", "type_text"}
            assert required <= {t["name"] for t in tools}
            windows = eventually(lambda: mcp.call("list_windows")[0]["windows"], lambda ws: any(w.get("app_id") == "niri-cu-probe" for w in ws))
            wid = next(w["window_id"] for w in windows if w.get("app_id") == "niri-cu-probe")
            def app_state(image=False):
                return mcp.call("get_app_state", window_id=wid, desktop_screenshot=True, include_screenshot=image, max_nodes=300)[0]
            def node(name):
                nodes = app_state()["accessibility_tree"]
                return next(n for n in nodes if n.get("name") == name)
            def value(name, text):
                mcp.call("set_value", element_index=node(name)["index"], value=text)
            def key(chord): mcp.call("press_key", window_id=wid, key=chord)
            def focus_text():
                # AT-SPI grab-focus is not universally exposed; keyboard Tab
                # from the initially focused entry is covered separately.
                mcp.call("activate_window", window_id=wid)
                key("Ctrl+A")
            for round_index in range(args.rounds):
                prefix = f"r{round_index+1}/"
                record(prefix+"window-focus", lambda: mcp.call("activate_window", window_id=wid))
                record(prefix+"scoped-tree", lambda: (_ for _ in ()).throw(AssertionError("unscoped tree")) if not app_state()["tree_scoped"] else None)
                record(prefix+"editable-value", lambda: (value("Probe text", "seed"), eventually(state, lambda s: s.get("text") == "seed")))
                record(prefix+"unicode-value", lambda: (value("Probe text", "中文🙂abc"), eventually(state, lambda s: s.get("text") == "中文🙂abc")))
                record(prefix+"text-selection", lambda: (mcp.call("select_text", element_index=node("Probe text")["index"], start_offset=0, end_offset=3), eventually(state, lambda s: s.get("selection") == [0,3])))
                record(prefix+"unicode-typing", lambda: (key("Ctrl+A"), eventually(state, lambda s: s.get("selection") == [0,6]), mcp.call("type_text", window_id=wid, text="你好🙂 world"), eventually(state, lambda s: s.get("text") == "你好🙂 world")))
                record(prefix+"key-chord", lambda: (key("Ctrl+A"), eventually(state, lambda s: s.get("selection") == [0,len(s.get("text", ""))])))
                record(prefix+"plain-paste", lambda: (mcp.call("paste", window_id=wid, text="plain 中文"), eventually(state, lambda s: s.get("text") == "plain 中文")))
                record(prefix+"clipboard-restored", lambda: (_ for _ in ()).throw(AssertionError("clipboard changed")) if subprocess.check_output([str(args.binary.with_name("niri-clipboard")), "snapshot"]) != previous else None)
                record(prefix+"rich-paste", lambda: (key("Ctrl+A"), mcp.call("paste", window_id=wid, text="rich", html="<b>rich</b>"), eventually(state, lambda s: s.get("text") == "rich" and s.get("html") == "<b>rich</b>")))
                record(prefix+"secondary-entry", lambda: (key("Tab"), mcp.call("type_text", window_id=wid, text="second"), eventually(state, lambda s: s.get("other", "").endswith("second")), key("Shift+Tab")))
                clicks = state()["clicks"]
                record(prefix+"semantic-click", lambda: (mcp.call("perform_action", element_index=node("Probe counter")["index"]), eventually(state, lambda s: s.get("clicks") == clicks+1)))
                checked = state()["checked"]
                record(prefix+"checkbox", lambda: (mcp.call("perform_action", element_index=node("Probe checkbox")["index"]), eventually(state, lambda s: s.get("checked") != checked)))
                record(prefix+"numeric-value", lambda: (value("Probe slider", "42"), eventually(state, lambda s: s.get("slider") == 42)))
                image_state, image_result = mcp.call("get_app_state", window_id=wid, desktop_screenshot=True)
                record(prefix+"desktop-screenshot", lambda: (_ for _ in ()).throw(AssertionError(image_state.get("screenshot_error"))) if not any(c["type"]=="image" for c in image_result["content"]) else None)
                image_block = next(c for c in image_result["content"] if c["type"] == "image")
                image = Image.open(io.BytesIO(base64.b64decode(image_block["data"]))).convert("RGB")
                def colored_center(color):
                    pixels = image.load()
                    remaining = {(x,y) for y in range(image.height) for x in range(image.width) if all(abs(pixels[x,y][i]-color[i])<12 for i in range(3))}
                    components = []
                    while remaining:
                        stack = [remaining.pop()]
                        hits = []
                        while stack:
                            point = stack.pop(); hits.append(point)
                            px,py = point
                            for adjacent in [(px+1,py),(px-1,py),(px,py+1),(px,py-1)]:
                                if adjacent in remaining: remaining.remove(adjacent); stack.append(adjacent)
                        components.append(hits)
                    hits = max(components, key=len)
                    assert len(hits)>50, "calibration square not visible"
                    scale = image_state["screenshot"]["scale"]
                    return round(sum(x for x,y in hits)/len(hits)/scale), round(sum(y for x,y in hits)/len(hits)/scale)
                x,y = colored_center((0,255,0))
                bx,by = colored_center((0,0,255))
                print("calibration", x,y,bx,by, "space", image_state["screenshot"]["coordinate_width"], image_state["screenshot"]["coordinate_height"], flush=True)
                points = len(state()["points"])
                record(prefix+"absolute-click-calibration", lambda: (mcp.call("click", window_id=wid, x=x, y=y, relative=False), eventually(state, lambda s: len(s.get("points", []))>points and abs(s["points"][-1][0]-45)<5 and abs(s["points"][-1][1]-45)<5)))
                rights = state()["right_clicks"]
                record(prefix+"right-click", lambda: (mcp.call("click", window_id=wid, x=x, y=y, button="right"), eventually(state, lambda s:s.get("right_clicks")==rights+1)))
                motions = state()["drag_events"]
                record(prefix+"drag", lambda: (mcp.call("drag", window_id=wid, start_x=x, start_y=y, end_x=bx, end_y=by), eventually(state, lambda s:s.get("drag_events",0)>motions)))
                scrolls = state()["scrolls"]
                record(prefix+"scroll", lambda: (mcp.call("scroll", window_id=wid, x=x,y=y,direction="down", pages=1), eventually(state,lambda s:s.get("scrolls",0)>scrolls)))
                record(prefix+"verify-state-after-actions", lambda: (_ for _ in ()).throw(AssertionError("stale value")) if node("Probe text")["text"]["content"] != "rich" else None)
                record(prefix+"desktop-app-discovery", lambda: (_ for _ in ()).throw(AssertionError("empty desktop apps")) if not mcp.call("list_desktop_apps")[0]["apps"] else None)
            report["passed"] = True
        except Exception:
            report["passed"] = False
            raise
        finally:
            subprocess.run([str(args.binary.with_name("niri-clipboard")), "offer"], input=previous, check=True)
            mcp.close()
            probe.terminate()
            probe.wait(timeout=5)
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n")

if __name__ == "__main__": main()
