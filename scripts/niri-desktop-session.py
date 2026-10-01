#!/usr/bin/env python3
"""Preserve DPMS-off entry state while CUA uses the minimum backlight level."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import time

STATE=Path(os.environ.get('XDG_STATE_HOME',str(Path.home()/'.local/state')))/'niri-computer-use'
CHECKPOINT=STATE/'desktop-session.json'

def power_state():
    connected=[p.parent for p in Path('/sys/class/drm').glob('card*-*/status') if p.read_text().strip()=='connected']
    if not connected:raise RuntimeError('cannot determine physical display power state')
    return {'off':all((p/'enabled').read_text().strip()!='enabled' for p in connected),
            'connectors':{p.name:(p/'enabled').read_text().strip() for p in connected}}

def backlights():
    return {p.name:int((p/'brightness').read_text()) for p in Path('/sys/class/backlight').iterdir()}

def set_brightness(name,value):
    subprocess.run(['brightnessctl','-q','-d',name,'--min-value=0','set',str(value)],check=True,timeout=5)
    if int((Path('/sys/class/backlight')/name/'brightness').read_text())!=value:
        raise RuntimeError('requested brightness did not apply')

def niri_power(off):
    env=dict(os.environ)
    if not env.get('NIRI_SOCKET'):
        runtime=Path(env.get('XDG_RUNTIME_DIR',f'/run/user/{os.getuid()}'))
        display=env.get('WAYLAND_DISPLAY','*')
        sockets=list(runtime.glob(f'niri.{display}.*.sock'))
        if len(sockets)!=1:raise RuntimeError('cannot uniquely resolve niri IPC socket')
        env['NIRI_SOCKET']=str(sockets[0])
    subprocess.run(['niri','msg','action','power-off-monitors' if off else 'power-on-monitors'],env=env,check=True,timeout=5)
    deadline=time.monotonic()+2
    while power_state()['off']!=off:
        if time.monotonic()>deadline:raise RuntimeError('display power transition did not apply')
        time.sleep(.05)

def restore(snapshot):
    if snapshot['dimmed']:
        # Blank first so restoration cannot expose a bright frame.
        niri_power(True)
        for name,value in snapshot['brightness'].items():set_brightness(name,value)
    return {'power':power_state(),'brightness':backlights()}

def owner_alive(snapshot):
    owner=snapshot.get('owner_pid',0)
    if not owner:return True
    try:return Path(f'/proc/{owner}/stat').read_text().split()[21]==snapshot['owner_start']
    except FileNotFoundError:return False

def write_checkpoint(snapshot):
    temporary=STATE/'desktop-session.json.tmp'
    with temporary.open('w') as file:
        os.chmod(temporary,0o600);json.dump(snapshot,file)
    temporary.replace(CHECKPOINT)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['begin','wake','end','status','watch'])
    parser.add_argument('--owner-pid',type=int,default=0)
    args=parser.parse_args()
    STATE.mkdir(parents=True,mode=0o700,exist_ok=True)
    if args.action=='watch':
        while CHECKPOINT.exists():
            try:snapshot=json.loads(CHECKPOINT.read_text())
            except FileNotFoundError:return
            if snapshot.get('owner_pid')!=args.owner_pid:return
            if not owner_alive(snapshot):
                with (STATE/'desktop-session.lock').open('a') as lock:
                    fcntl.flock(lock,fcntl.LOCK_EX)
                    if CHECKPOINT.exists():
                        current=json.loads(CHECKPOINT.read_text())
                        if current==snapshot:restore(current);CHECKPOINT.unlink()
                return
            time.sleep(1)
        return
    with (STATE/'desktop-session.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        snapshot=json.loads(CHECKPOINT.read_text()) if CHECKPOINT.exists() else None
        if snapshot and not owner_alive(snapshot):
            restore(snapshot);CHECKPOINT.unlink();snapshot=None
        if args.action=='begin':
            if snapshot:
                if snapshot.get('owner_pid')!=args.owner_pid:raise RuntimeError('another CUA session owns the brightness checkpoint')
            else:
                power=power_state();off=power['off'];brightness=backlights()
                if off and any(not ('eDP-' in name or 'LVDS-' in name) for name in power['connectors']):
                    raise RuntimeError('external monitor minimum brightness is not controllable; refusing automatic wake')
                if off and not brightness:raise RuntimeError('display is off but no controllable backlight exists; cannot guarantee minimum brightness')
                owner_start=Path(f'/proc/{args.owner_pid}/stat').read_text().split()[21] if args.owner_pid else None
                snapshot={'entered_off':off,'dimmed':off,'brightness':brightness,'owner_pid':args.owner_pid,'owner_start':owner_start}
                write_checkpoint(snapshot)
                try:
                    if off:
                        for name in brightness:set_brightness(name,1)
                except Exception:
                    restore(snapshot);CHECKPOINT.unlink();raise
                if args.owner_pid:
                    subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'watch','--owner-pid',str(args.owner_pid)],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
        elif args.action=='wake':
            if not snapshot:raise RuntimeError('begin a protected session before waking the display')
            if snapshot.get('owner_pid')!=args.owner_pid:raise RuntimeError('another session owns the checkpoint')
            if snapshot['dimmed']:
                for name in snapshot['brightness']:set_brightness(name,1)
            niri_power(False)
        elif args.action=='end' and snapshot:
            if snapshot.get('owner_pid') not in (0,args.owner_pid):raise RuntimeError('brightness checkpoint belongs to another CUA session')
            restored=restore(snapshot);CHECKPOINT.unlink()
            print(json.dumps({'ok':True,'restored':restored,'entered_off':snapshot['entered_off']}));return
        print(json.dumps({'ok':True,'session':snapshot,'power':power_state(),'brightness':backlights()}))

if __name__=='__main__':main()
