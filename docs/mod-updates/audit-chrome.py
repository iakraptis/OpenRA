"""Chrome check for a mod on bleed: widgets and panels the mod's chrome needs but no loaded chrome file defines.

Usage, from anywhere:  python audit-chrome.py <mod repository> <mod id>
                 e.g.  python audit-chrome.py ../../../primwars pw

Reads the mod's ChromeLayout (mod.yaml, or the file it includes), then reports:
- for each Logic used in a loaded chrome file, the widget ids its C# requires (Get, not GetOrNull) that are not
  defined in any loaded chrome file;
- panel ids named in the chrome (for example the settings window's Panels list) that are not defined.
Rough: ids are matched anywhere in the loaded chrome, and logics are found by file or class name. It catches missing
panels such as GAMEPLAY_PANEL; it doesn't prove a screen works.
"""
import re
import sys
from pathlib import Path

repo = Path(sys.argv[1]).resolve()
mod_id = sys.argv[2]
engine = repo / 'engine'
mod_dir = repo / 'mods' / mod_id


def chrome_layout():
    for name in ['mod.yaml'] + [m for m in re.findall(r'^Include: *(.+)$', (mod_dir / 'mod.yaml').read_text(encoding='utf-8-sig'), re.M)]:
        text = (mod_dir / name.strip()).read_text(encoding='utf-8-sig')
        m = re.search(r'^ChromeLayout:\n((?:\t.*\n?)+)', text, re.M)
        if m:
            return [line.strip() for line in m.group(1).split('\n') if line.strip() and not line.strip().startswith('#')]
    sys.exit('No ChromeLayout found')


def resolve(entry):
    mod, path = entry.split('|')
    if (engine / 'mods' / mod).is_dir():
        return engine / 'mods' / mod / path
    return repo / 'mods' / mod / path


files = [resolve(e) for e in chrome_layout()]
defined, logics, panel_refs = set(), set(), set()
for f in files:
    text = f.read_text(encoding='utf-8-sig')
    defined |= set(re.findall(r'@([A-Z0-9_]+):', text))
    for group in re.findall(r'Logic: *([A-Za-z0-9_, ]+)', text):
        logics |= {n.strip() for n in group.split(',') if n.strip()}
    panel_refs |= set(re.findall(r'^\t+([A-Z][A-Z0-9_]*_PANEL):', text, re.M))
    panel_refs |= set(re.findall(r':\s*([A-Z][A-Z0-9_]*_PANEL)\s*$', text, re.M))

code_dirs = [engine / 'OpenRA.Mods.Common'] + [p for p in repo.glob('OpenRA.Mods.*') if p.is_dir()]
sources = {p: p.read_text(encoding='utf-8-sig', errors='replace')
           for d in code_dirs for p in d.rglob('*.cs') if 'obj' not in p.parts}

problems = 0
for name in sorted(logics):
    body = None
    for code in sources.values():
        m = re.search(r'class ' + re.escape(name) + r'\b.*?(?=\n\t(?:public|sealed|abstract|static)? ?class |\Z)', code, re.S)
        if m:
            body = m.group(0)
            break
    if body is None:
        print(f'{name}: source not found (not checked)')
        continue
    required = set(re.findall(r'\.Get(?:<\w+>)?\("([A-Z0-9_]+)"\)', body))
    required |= set(re.findall(r'(?:OpenWindow|LoadWidget)\([^")]*"([A-Z0-9_]+)"', body))
    missing = sorted(i for i in required if i not in defined)
    if missing:
        problems += 1
        print(f'{name}: needs {", ".join(missing)}')

missing_panels = sorted(r for r in panel_refs if r not in defined)
if missing_panels:
    problems += 1
    print('panels named in the chrome but not defined:', ', '.join(missing_panels))
print(f'{len(files)} chrome files, {len(logics)} logics; {"no problems" if not problems else str(problems) + " to look at"}')
