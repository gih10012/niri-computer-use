#!/usr/bin/env python3
"""Launch a disposable XDG application and verify reuse, targeting and rejection."""
import json
import argparse
import os
from pathlib import Path
import signal
import subprocess
import tempfile
from niri_e2e_import import MCP, eventually

ROOT = Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary',type=Path,default=Path.home()/'.local/share/niri-computer-use/bin/computer-use-linux')
    binary=parser.parse_args().binary
    platform=json.loads(subprocess.check_output([str(binary),'doctor']))['platform']
    for key,field in {'WAYLAND_DISPLAY':'wayland_display','XDG_RUNTIME_DIR':'xdg_runtime_dir','DBUS_SESSION_BUS_ADDRESS':'dbus_session_bus_address','XDG_CURRENT_DESKTOP':'xdg_current_desktop'}.items():
        if platform.get(field):os.environ.setdefault(key,platform[field])
    report={'passed':False,'rounds':3,'cases':[]}
    with tempfile.TemporaryDirectory(prefix='niri-cu-launch-') as directory:
        temp=Path(directory)
        apps=temp/'applications';apps.mkdir()
        state=temp/'state.json'
        (apps/'niri-cu-launch-test.desktop').write_text('[Desktop Entry]\nType=Application\nName=niri launch acceptance\nStartupWMClass=niri-cu-probe\nExec=python '+str(ROOT/'examples/niri-probe.py')+' --state '+str(state)+'\n')
        old=os.environ.get('XDG_DATA_HOME')
        os.environ['XDG_DATA_HOME']=str(temp)
        mcp=MCP(binary)
        if old is None:os.environ.pop('XDG_DATA_HOME')
        else:os.environ['XDG_DATA_HOME']=old
        def record(name,fn):
            fn();report['cases'].append({'name':name,'passed':True});print('PASS',name,flush=True)
        def owned_windows():
            return [w for w in mcp.call('list_windows')[0]['windows'] if w.get('app_id')=='niri-cu-probe' and w.get('pid') and str(state) in Path(f"/proc/{w['pid']}/cmdline").read_text(errors='replace')]
        def close_owned():
            for w in owned_windows():os.kill(w['pid'],signal.SIGTERM)
            eventually(owned_windows,lambda ws:not ws)
        try:
            for iteration in range(3):
                prefix=f'r{iteration+1}/'
                def unknown():
                    try:mcp.call('launch_app',desktop_id='niri-cu-nonexistent-test.desktop')
                    except RuntimeError as error:
                        assert 'unknown desktop_id' in str(error);return
                    raise AssertionError('unknown application was accepted')
                record(prefix+'unknown-app-rejected',unknown)
                window=mcp.call('launch_app',desktop_id='niri-cu-launch-test.desktop')[0]['window']
                wid=window['window_id']
                record(prefix+'launch-and-focus',lambda:eventually(owned_windows,lambda ws:len(ws)==1 and ws[0]['window_id']==wid and ws[0]['focused']))
                reused=mcp.call('launch_app',desktop_id='niri-cu-launch-test.desktop')[0]['window']
                record(prefix+'reuse-existing-window',lambda:(_ for _ in ()).throw(AssertionError('duplicate window')) if reused['window_id']!=wid or len(owned_windows())!=1 else None)
                close_owned()
            report['passed']=True
        finally:
            close_owned();mcp.close()
            (ROOT/'artifacts/launch.json').write_text(json.dumps(report,indent=2)+'\n')

if __name__=='__main__':main()
