#!/usr/bin/env python3
"""Check current delivery artifacts; never infer success from missing evidence."""
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]
def read(path):return json.loads(path.read_text())
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    reports={name:read(ROOT/'artifacts'/f'{name}.json') for name in ['acceptance','qt','web-toolkits','launch','cold-start','host']}
    expected={'acceptance':63,'qt':30,'web-toolkits':60,'launch':9}
    for name,count in expected.items():
        report=reports[name]
        assert report['passed'] and len(report['cases'])==count,name
        assert all(case['passed'] for case in report['cases']),name
        assert report['rounds']==3,name
    assert len({c['name'].split('/',1)[1] for c in reports['acceptance']['cases']})>=20
    assert reports['cold-start']['passed'] and len(reports['cold-start']['rounds'])==3
    host=reports['host']
    assert host['passed'] and host['harmless_call_succeeded'] and not host['inference_started']
    legacy=read(ROOT/'plugins/niri-computer-use/.codex-plugin/plugin.json')
    portable=read(ROOT/'packaging/niri-computer-use.plugin.json')
    assert legacy['version']==portable['version']==host['plugin_version']
    assert legacy['interface']==portable['extensions']['com.openai']['interface']
    installed=json.loads(subprocess.check_output(['codex','plugin','list','--json']))
    plugin=next(p for p in installed['installed'] if p['pluginId']=='niri-computer-use@niri-local')
    assert plugin['enabled'] and plugin['version']==legacy['version']
    assert not (ROOT/'plugins/niri-computer-use/plugin.json').exists(), 'this CLI drops MCP discovery with a portable root manifest'
    hashes={}
    for name in ['computer-use-linux','niri-clipboard']:
        built=ROOT/'target/debug'/name
        runtime=Path.home()/'.local/share/niri-computer-use/bin'/name
        assert digest(built)==digest(runtime),f'installed binary is stale: {name}'
        hashes[name]=digest(runtime)
    for path in ['NIRI.md','LICENSE','scripts/install-niri.sh','scripts/uninstall-niri.sh']:
        assert (ROOT/path).is_file(),path
    summary={'passed':True,'plugin_version':legacy['version'],'gui_cases':153,'launch_cases':9,
             'cold_process_rounds':3,'host_tools':len(host['tools']),'binary_sha256':hashes,
             'mac_hardware_tested':False,'desktop_rebooted':False,'github_published':False}
    (ROOT/'artifacts/delivery.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2))

if __name__=='__main__':main()
