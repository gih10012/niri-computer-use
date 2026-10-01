#!/usr/bin/env python3
"""Disposable GTK application with observable input results for niri E2E."""
import argparse
import json
from pathlib import Path
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib, Atk

parser = argparse.ArgumentParser()
parser.add_argument("--state", required=True)
args = parser.parse_args()
GLib.set_prgname("niri-cu-probe")
state = {"clicks": 0, "right_clicks": 0, "drag_events": 0, "scrolls": 0, "html": "", "keys": [], "points": []}
window = Gtk.Window(title="niri Computer Use acceptance probe")
window.set_default_size(700, 700)
window.connect("destroy", Gtk.main_quit)
box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
box.set_border_width(20)
window.add(box)
entry = Gtk.Entry()
entry.get_accessible().set_name("Probe text")
box.pack_start(entry, False, False, 0)
other = Gtk.Entry()
other.get_accessible().set_name("Other text")
box.pack_start(other, False, False, 0)
button = Gtk.Button(label="Probe counter")
button.connect("clicked", lambda *_: state.update(clicks=state["clicks"] + 1))
box.pack_start(button, False, False, 0)
check = Gtk.CheckButton(label="Probe checkbox")
box.pack_start(check, False, False, 0)
scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
scale.get_accessible().set_name("Probe slider")
box.pack_start(scale, False, False, 0)
canvas = Gtk.DrawingArea()
canvas.set_size_request(300, 150)
canvas.get_accessible().set_name("Probe canvas")
canvas.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.BUTTON_RELEASE_MASK | Gdk.EventMask.POINTER_MOTION_MASK | Gdk.EventMask.SCROLL_MASK | Gdk.EventMask.SMOOTH_SCROLL_MASK)
def draw(widget, cr):
    cr.set_source_rgb(0, 1, 0)
    cr.rectangle(30, 30, 30, 30)
    cr.fill()
    cr.set_source_rgb(0, 0, 1)
    cr.rectangle(150, 30, 30, 30)
    cr.fill()
canvas.connect("draw", draw)
def press(widget, event):
    state["points"].append([round(event.x, 2), round(event.y, 2), event.button])
    if event.button == 3: state["right_clicks"] += 1
    return False
canvas.connect("button-press-event", press)
canvas.connect("motion-notify-event", lambda w, e: state.update(drag_events=state["drag_events"] + int(bool(e.state & Gdk.ModifierType.BUTTON1_MASK))))
canvas.connect("scroll-event", lambda *_: state.update(scrolls=state["scrolls"] + 1))
box.pack_start(canvas, False, False, 0)
textview = Gtk.TextView()
textview.get_accessible().set_name("Probe document")
textview.get_buffer().set_text("\n".join(f"Line {i}" for i in range(200)))
scroller = Gtk.ScrolledWindow()
scroller.set_size_request(200, 180)
scroller.add(textview)
box.pack_start(scroller, True, True, 0)
def key(widget, event):
    state["keys"].append([Gdk.keyval_name(event.keyval), int(event.state)])
    if event.state & Gdk.ModifierType.CONTROL_MASK and Gdk.keyval_name(event.keyval).lower() == "v":
        def got_html(clip, data, _):
            raw = data.get_data()
            state["html"] = bytes(raw).decode("utf-8") if raw else ""
        Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).request_contents(Gdk.Atom.intern("text/html", False), got_html, None)
    return False
entry.connect("key-press-event", key)
other.connect("key-press-event", key)
def save():
    selection = entry.get_selection_bounds()
    buf = textview.get_buffer()
    device = Gdk.Display.get_default().get_default_seat().get_pointer()
    position = window.get_window().get_device_position(device)
    px, py = position[-3:-1]
    rect = canvas.get_allocation()
    state.update(pointer=[px,py], canvas=[rect.x,rect.y,rect.width,rect.height], text=entry.get_text(), other=other.get_text(), selection=list(selection), checked=check.get_active(), slider=scale.get_value(), document=buf.get_text(buf.get_start_iter(), buf.get_end_iter(), True))
    Path(args.state).write_text(json.dumps(state, ensure_ascii=False))
    return True
GLib.timeout_add(40, save)
window.show_all()
entry.grab_focus()
Gtk.main()
