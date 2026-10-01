#!/usr/bin/env python3
"""Verify installed-plugin discovery and a read-only call in Codex, without inference."""
import json
import argparse
from pathlib import Path
import queue
import subprocess
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report',type=Path,default=ROOT/'artifacts/host.json')
    args=parser.parse_args()
    report = {'passed': False, 'inference_started': False}
    with tempfile.TemporaryFile() as log:
        process = subprocess.Popen(['codex', 'app-server', '--stdio'], stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=log, text=True, bufsize=1)
        messages = queue.Queue()
        def receive():
            for line in process.stdout:
                messages.put(json.loads(line))
            messages.put(None)
        threading.Thread(target=receive, daemon=True).start()
        counter = 0
        def request(method, params):
            nonlocal counter
            counter += 1
            process.stdin.write(json.dumps({'id':counter,'method':method,'params':params})+'\n')
            process.stdin.flush()
            while True:
                response = messages.get(timeout=90)
                if response is None: raise RuntimeError('Codex app-server exited')
                if response.get('id') == counter:
                    if 'error' in response: raise RuntimeError(response['error'])
                    return response['result']
        try:
            request('initialize', {'clientInfo':{'name':'niri-host-e2e','version':'0.1'},
                                   'capabilities':{'experimentalApi':True}})
            process.stdin.write(json.dumps({'method':'initialized'})+'\n');process.stdin.flush()
            plugin=request('plugin/read',{'pluginName':'niri-computer-use','marketplacePath':str(ROOT/'.agents/plugins/marketplace.json')})
            print('niri plugin MCP servers:', plugin['plugin']['mcpServers'],flush=True)
            assert plugin['plugin']['mcpServers'], 'installed plugin has no discovered MCP server'
            report['plugin_version']=plugin['plugin']['summary']['localVersion']
            thread = request('thread/start', {'cwd':str(ROOT),'ephemeral':True})
            thread_id = thread['thread']['id']
            deadline = time.monotonic()+60
            while True:
                status = request('mcpServerStatus/list', {'threadId':thread_id,'detail':'toolsAndAuthOnly','limit':100})
                servers = [s for s in status['data'] if 'niri' in s['name']]
                if servers or time.monotonic() >= deadline: break
                time.sleep(1)
            if len(servers) != 1: raise AssertionError({'server_names':[s['name'] for s in status['data']]})
            server = servers[0]
            tools = server['tools']
            names = list(tools) if isinstance(tools,dict) else [t['name'] for t in tools]
            required = {'list_windows','get_app_state','launch_app','select_text','paste','focus_element'}
            if not required.issubset(set(names)): raise AssertionError({'tools':names})
            result = request('mcpServer/tool/call', {'threadId':thread_id,'server':server['name'],
                                                   'tool':'list_windows','arguments':{}})
            if result.get('isError'): raise AssertionError(result)
            report.update(passed=True, server=server['name'], tools=sorted(names),
                          harmless_call='list_windows', harmless_call_succeeded=True)
            print(json.dumps(report,indent=2))
        finally:
            process.stdin.close()
            try: process.wait(timeout=10)
            except subprocess.TimeoutExpired: process.terminate();process.wait(timeout=10)
            if not report['passed']:
                log.seek(0)
                for line in log.read().decode(errors='replace').splitlines():
                    if 'niri' in line.lower(): print(line,flush=True)
            args.report.write_text(json.dumps(report,indent=2)+'\n')

if __name__ == '__main__': main()
