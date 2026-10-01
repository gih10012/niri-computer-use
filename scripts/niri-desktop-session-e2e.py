#!/usr/bin/env python3
"""Explicit local hardware test; run only when display transitions are authorized."""
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
HELPER=ROOT/'scripts/niri-desktop-session.py'
def call(action,*args):
    return json.loads(subprocess.check_output([sys.executable,str(HELPER),action,*args]))

initial=call('status')
assert initial['power']['off'] and initial['session'] is None
rounds=[]
try:
    for _ in range(3):
        begin=call('begin');assert begin['power']['off']
        assert all(v==1 for v in begin['brightness'].values())
        wake=call('wake');assert not wake['power']['off']
        end=call('end');assert end['restored']['power']['off']
        assert end['restored']['brightness']==initial['brightness']
        rounds.append({'begin':begin,'wake':wake,'end':end})
    owner=subprocess.Popen(['sleep','10'])
    try:
        call('begin','--owner-pid',str(owner.pid))
        call('wake','--owner-pid',str(owner.pid))
    finally:
        owner.terminate();owner.wait()
    time.sleep(2)
    # Inspect checkpoint before status, which also offers stale-owner recovery.
    checkpoint=Path.home()/'.local/state/niri-computer-use/desktop-session.json'
    assert not checkpoint.exists(),'watchdog did not restore independently'
    final=call('status')
    assert final['power']['off'] and final['brightness']==initial['brightness']
    report={'passed':True,'rounds':rounds,'watchdog_passed':True,'final':final,
            'private_images_included':False}
    (ROOT/'artifacts/display-session.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'passed':True,'rounds':3,'watchdog_passed':True,'final':final}))
finally:
    call('end')
