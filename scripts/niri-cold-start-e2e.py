#!/usr/bin/env python3
"""Verify installed tools recover the live session from a scrubbed environment."""
import json
import os
from pathlib import Path
import subprocess
from niri_e2e_import import MCP

ROOT=Path(__file__).resolve().parents[1]

def main():
    binary=Path.home()/'.local/share/niri-computer-use/bin/computer-use-linux'
    env={'HOME':str(Path.home()),'PATH':os.defpath}
    report={'passed':False,'reboot_performed':False,'rounds':[]}
    for iteration in range(3):
        doctor=json.loads(subprocess.check_output([str(binary),'doctor'],env=env))
        readiness=doctor['readiness']
        assert not readiness['blockers'],readiness['blockers']
        for key in ['can_build_accessibility_tree','can_query_windows','can_focus_windows','can_send_development_input','can_capture_screenshots']:
            assert readiness[key],key
        mcp=MCP(binary,env=env)
        try:
            windows=mcp.call('list_windows')[0]['windows']
            assert windows,'live session was not discovered'
            assert mcp.call('list_desktop_apps')[0]['apps']
        finally:mcp.close()
        report['rounds'].append({'round':iteration+1,'passed':True,'capabilities':doctor['capabilities']})
        print('PASS scrubbed environment',iteration+1,flush=True)
    report['passed']=True
    (ROOT/'artifacts/cold-start.json').write_text(json.dumps(report,indent=2)+'\n')

if __name__=='__main__':main()
