#!/usr/bin/env python3
"""Cross-toolkit acceptance using isolated Qt, Electron and Firefox fixtures."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import threading
import time
from niri_e2e_import import MCP, eventually

ROOT = Path(__file__).resolve().parents[1]

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path, required=True)
    parser.add_argument('--rounds', type=int, default=3)
    parser.add_argument('--report', type=Path, default=ROOT/'artifacts/toolkits.json')
    parser.add_argument('--toolkits', nargs='+', choices=['qt','electron','firefox'], default=['qt','electron','firefox'])
    args = parser.parse_args()
    platform = json.loads(subprocess.check_output([str(args.binary),'doctor']))['platform']
    for key,field in {'WAYLAND_DISPLAY':'wayland_display','XDG_RUNTIME_DIR':'xdg_runtime_dir','DBUS_SESSION_BUS_ADDRESS':'dbus_session_bus_address','XDG_CURRENT_DESKTOP':'xdg_current_desktop','XDG_SESSION_TYPE':'xdg_session_type','DISPLAY':'display'}.items():
        if platform.get(field): os.environ.setdefault(key,platform[field])
    os.environ['QT_ACCESSIBILITY_ALWAYS_ON']='1'
    os.environ['MOZ_ENABLE_WAYLAND']='1'
    report={'rounds':args.rounds,'cases':[],'capabilities':[],'passed':False,'mac_hardware_tested':False}
    with tempfile.TemporaryDirectory(prefix='niri-cu-toolkits-') as directory:
        temp=Path(directory)
        qt_binary=temp/'qt-probe'
        if 'qt' in args.toolkits:
            flags=subprocess.check_output(['pkg-config','--cflags','--libs','Qt6Widgets'],text=True).split()
            subprocess.run(['g++','-std=c++17','-fPIC',str(ROOT/'examples/niri-qt-probe.cpp'),'-o',str(qt_binary),*flags],check=True)
        shared={}
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                body=(ROOT/'examples/niri-web-probe.html').read_bytes()
                self.send_response(200); self.send_header('Content-Type','text/html; charset=utf-8'); self.end_headers();self.wfile.write(body)
            def do_POST(self):
                length=int(self.headers.get('Content-Length','0'))
                if length>65536: self.send_error(413);return
                shared.clear();shared.update(json.loads(self.rfile.read(length)))
                self.send_response(204);self.end_headers()
            def log_message(self,*_): pass
        http=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        threading.Thread(target=http.serve_forever,daemon=True).start()
        mcp=MCP(args.binary)
        previous=subprocess.check_output([str(args.binary.with_name('niri-clipboard')),'snapshot'])
        def record(name,operation):
            start=time.monotonic()
            try: operation();report['cases'].append({'name':name,'passed':True,'seconds':round(time.monotonic()-start,3)});print('PASS',name,flush=True)
            except Exception as error:
                report['cases'].append({'name':name,'passed':False,'error':str(error)[:1500]});print('FAIL',name,str(error)[:200],flush=True);raise
        try:
            for toolkit in args.toolkits:
                for iteration in range(args.rounds):
                    shared.clear()
                    state_path=temp/f'{toolkit}-{iteration}.json'
                    url=f'http://127.0.0.1:{http.server_port}/?toolkit={toolkit}&round={iteration}'
                    if toolkit=='qt':
                        command=[str(qt_binary),str(state_path)]
                        title='niri Computer Use Qt probe'
                        def read():
                            try:return json.loads(state_path.read_text())
                            except (FileNotFoundError,json.JSONDecodeError):return {}
                    elif toolkit=='electron':
                        command=['electron','--ozone-platform=wayland','--force-renderer-accessibility',str(ROOT/'examples/niri-electron-probe.js'),url]
                        title='niri Computer Use web probe'
                        def read():return dict(shared)
                    else:
                        profile=temp/f'firefox-{iteration}'
                        profile.mkdir()
                        command=['firefox','--no-remote','--profile',str(profile),'--new-window',url]
                        title='niri Computer Use web probe'
                        def read():return dict(shared)
                    log_path=temp/f'{toolkit}-{iteration}.log'
                    log=log_path.open('wb')
                    process=subprocess.Popen(command,stdout=log,stderr=log,start_new_session=True)
                    try:
                        windows=eventually(lambda:mcp.call('list_windows')[0]['windows'],lambda ws:any(title in (w.get('title') or '') for w in ws),timeout=30)
                        wid=next(w['window_id'] for w in windows if title in (w.get('title') or ''))
                        def state():return mcp.call('get_app_state',window_id=wid,include_screenshot=False,max_nodes=1000)[0]
                        def node(name):return next(n for n in state()['accessibility_tree'] if n.get('name')==name)
                        def key(chord):mcp.call('press_key',window_id=wid,key=chord)
                        prefix=f'{toolkit}/r{iteration+1}/'
                        record(prefix+'focus',lambda:mcp.call('activate_window',window_id=wid))
                        record(prefix+'scoped-accessibility',lambda:eventually(state,lambda s:s.get('tree_scoped') and any(n.get('name')=='Probe text' for n in s['accessibility_tree'])))
                        def replace_text():
                            mcp.call('focus_element',element_index=node('Probe text')['index'])
                            error=None
                            try:
                                mcp.call('set_value',element_index=node('Probe text')['index'],value='Hello 中文')
                                eventually(read,lambda s:s.get('text')=='Hello 中文',timeout=2)
                            except (RuntimeError,AssertionError) as failure:
                                error=str(failure)
                            report['capabilities'].append({'toolkit':toolkit,'round':iteration+1,'interface':'set_value','verified':error is None,'error':error})
                            if error is not None:
                                key('Ctrl+A');mcp.call('type_text',window_id=wid,text='Hello 中文')
                                eventually(read,lambda s:s.get('text')=='Hello 中文')
                        record(prefix+'unicode-replacement',replace_text)
                        def select_text():
                            error=None
                            try:
                                mcp.call('select_text',element_index=node('Probe text')['index'],start_offset=0,end_offset=5)
                                eventually(read,lambda s:s.get('selected')=='Hello',timeout=2)
                            except (RuntimeError,AssertionError) as failure:
                                error=str(failure)
                            report['capabilities'].append({'toolkit':toolkit,'round':iteration+1,'interface':'select_text','verified':error is None,'error':error})
                            if error is not None:
                                mcp.call('focus_element',element_index=node('Probe text')['index'])
                                key('Home')
                                for _ in range(5):key('Shift+ArrowRight')
                                eventually(read,lambda s:s.get('selected')=='Hello')
                        record(prefix+'text-selection',select_text)
                        record(prefix+'unicode-typing',lambda:(key('Ctrl+A'),mcp.call('type_text',window_id=wid,text='你好 world'),eventually(read,lambda s:s.get('text')=='你好 world')))
                        record(prefix+'plain-paste',lambda:(key('Ctrl+A'),mcp.call('paste',window_id=wid,text='paste 中文'),eventually(read,lambda s:s.get('text')=='paste 中文')))
                        record(prefix+'semantic-click',lambda:(mcp.call('perform_action',element_index=node('Probe counter')['index']),eventually(read,lambda s:s.get('clicks')==1)))
                        record(prefix+'checkbox',lambda:(mcp.call('perform_action',element_index=node('Probe checkbox')['index']),eventually(read,lambda s:s.get('checked') is True)))
                        # Some semantic actions focus their widgets. Explicitly
                        # focus the rich editor through native Component focus.
                        record(prefix+'rich-paste',lambda:(mcp.call('focus_element',element_index=node('Probe rich')['index']),mcp.call('paste',window_id=wid,text='rich',html='<b>rich</b>'),eventually(read,lambda s:s.get('rich')=='rich' and s.get('bold'))))
                        screenshot,result=mcp.call('get_app_state',window_id=wid,desktop_screenshot=True)
                        record(prefix+'screenshot',lambda:(_ for _ in ()).throw(AssertionError(screenshot.get('screenshot_error'))) if not any(c['type']=='image' for c in result['content']) else None)
                    except Exception:
                        log.flush()
                        print(log_path.read_text(errors='replace')[-4000:],flush=True)
                        raise
                    finally:
                        if process.poll() is None:
                            os.killpg(process.pid,signal.SIGTERM)
                            try:process.wait(timeout=5)
                            except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=5)
                        log.close()
            report['passed']=True
        finally:
            subprocess.run([str(args.binary.with_name('niri-clipboard')),'offer'],input=previous,check=True)
            mcp.close();http.shutdown();http.server_close()
            args.report.parent.mkdir(parents=True,exist_ok=True)
            args.report.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')

if __name__=='__main__':main()
