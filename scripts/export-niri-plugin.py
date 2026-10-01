#!/usr/bin/env python3
"""Export a portable package separately from the installed legacy-CLI source."""
import json
from pathlib import Path
import zipfile

ROOT=Path(__file__).resolve().parents[1]
source=ROOT/'plugins/niri-computer-use'
manifest=ROOT/'packaging/niri-computer-use.plugin.json'
portable=json.loads(manifest.read_text())
legacy=json.loads((source/'.codex-plugin/plugin.json').read_text())
assert portable['name']==legacy['name'] and portable['version']==legacy['version']
assert portable['extensions']['com.openai']['interface']==legacy['interface']
assert len(legacy['interface']['shortDescription'])<=30
output=ROOT/'artifacts'/f"niri-computer-use-{legacy['version']}.zip"
with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as archive:
    archive.write(manifest,'niri-computer-use/plugin.json')
    archive.write(ROOT/'LICENSE','niri-computer-use/LICENSE')
    for path in sorted(source.rglob('*')):
        if path.is_symlink():raise ValueError(f'symlink not allowed: {path}')
        if path.is_file():archive.write(path,'niri-computer-use/'+str(path.relative_to(source)))
with zipfile.ZipFile(output) as archive:
    assert archive.testzip() is None
    assert 'niri-computer-use/mcp.json' in archive.namelist()
    assert 'niri-computer-use/skills/niri-computer-use/SKILL.md' in archive.namelist()
print(output)
