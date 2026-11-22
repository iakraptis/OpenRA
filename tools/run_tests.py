"""Run a mod's automated test maps on this engine, headless and in parallel.

Usage, from a mod repository (Mod SDK layout, engine in ./engine):
  python engine/tools/run_tests.py                       # every *-test map, in parallel
  python engine/tools/run_tests.py --only a-test,b-test  # some maps
  python engine/tools/run_tests.py --jobs 4              # at most 4 games at once
  python engine/tools/run_tests.py --windowed --only a-test   # watch one test in a window
Options for other layouts: --mod-dir, --mod, --engine, --results.

Each test map runs as its own game with Game.Platform=Null (no window) and Launch.Uncapped=true (no waiting for the
game speed's timestep), with its logs and replay in its own folder under the results directory. The verdict comes from
the game's exit code:
   0 pass (Test.Pass)     1 fail (Test.Fail)     2 tick limit (Launch.MaxTicks)
   4 fatal Lua error      5 out of sync          other: crash (see the map's stderr)
Maps whose script doesn't call Test.Pass/Test.Fail yet are judged by their output as before ("TEST PASS",
"TEST FAIL", "FAIL:", "Fatal Lua Error"); the runner then stops that game itself. It never touches other processes.

Optional per-mod settings in <mod-dir>/tests.json:
  {"manual": ["map-not-to-run"], "max_ticks": {"bot-test": 45000}, "default_max_ticks": 20000,
   "timeout_seconds": {"bot-test": 900}, "default_timeout_seconds": 300, "content_maps": true}
"""
import argparse
import concurrent.futures
import json
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

PASS_LINE = re.compile(r'TEST PASS')
FAIL_LINE = re.compile(r'TEST FAIL|FAIL:|Fatal Lua Error')
EXIT_VERDICTS = {0: 'PASS', 1: 'FAIL', 2: 'FAIL (tick limit)', 4: 'FAIL (Lua error)', 5: 'FAIL (out of sync)'}
# Pinned so results don't depend on the player's settings (the null window takes its size from them).
SCREEN = ['Graphics.Mode=Windowed', 'Graphics.WindowedSize=1920,1080']


def read_mod_config(mod_dir: Path) -> dict:
    values = {}
    path = mod_dir / 'mod.config'
    if path.is_file():
        for line in path.read_text(encoding='utf-8', errors='replace').splitlines():
            m = re.match(r'^([A-Z_]+)="?(.*?)"?\s*$', line)
            if m:
                values[m.group(1)] = m.group(2)
    return values


def game_command(engine: Path) -> list:
    exe = engine / 'bin' / 'OpenRA.exe'
    if os.name == 'nt' and exe.is_file():
        return [str(exe)]
    return ['dotnet', str(engine / 'bin' / 'OpenRA.dll')]


def content_map_dirs(mod: str) -> list:
    # Maps an asset installer generates into the player's content folder: Content/<mod>/maps (e.g. OpenPW)
    # or Content/<mod>/<version>/maps (e.g. OpenSYW's v1).
    base = Path(os.environ.get('APPDATA', Path.home() / '.config' / 'openra')) / 'OpenRA' / 'Content' / mod
    if not base.is_dir():
        return []
    return sorted(p for p in [base / 'maps', *base.glob('*/maps')] if p.is_dir())


def find_maps(mod_dir: Path, mod: str, use_content: bool) -> list:
    folders = [mod_dir / 'mods' / mod / 'maps'] + (content_map_dirs(mod) if use_content else [])
    names = set()
    for folder in folders:
        if folder.is_dir():
            names |= {p.name for p in folder.iterdir() if p.name.endswith('-test')}
    return sorted(names)


def run_map(name: str, args, config: dict, results: Path) -> dict:
    out_dir = results / name
    out_dir.mkdir(parents=True, exist_ok=True)
    max_ticks = config.get('max_ticks', {}).get(name, config.get('default_max_ticks', 0))
    timeout = config.get('timeout_seconds', {}).get(name, config.get('default_timeout_seconds', 600))

    cmd = game_command(args.engine) + [
        f'Game.Mod={args.mod}', f'Engine.EngineDir={args.engine}',
        f'Engine.ModSearchPaths={args.mod_dir / "mods"},{args.engine / "mods"}',
        f'Engine.LogDir={out_dir / "logs"}', f'Engine.ReplayDir={out_dir}', f'Launch.Map={name}']
    if not args.windowed:
        cmd += ['Game.Platform=Null', 'Launch.Uncapped=true'] + SCREEN
    if max_ticks:
        cmd.append(f'Launch.MaxTicks={max_ticks}')

    started = time.time()
    stdout_path, stderr_path = out_dir / 'stdout.txt', out_dir / 'stderr.txt'
    with open(stdout_path, 'w', encoding='utf-8') as out, open(stderr_path, 'w', encoding='utf-8') as err:
        proc = subprocess.Popen(cmd, cwd=args.engine, stdout=subprocess.PIPE, stderr=err, text=True,
                                encoding='utf-8', errors='replace', bufsize=1)
        seen = {'pass': None, 'fail': None, 'last': ''}

        def pump():
            for line in proc.stdout:
                out.write(line)
                text = line.strip()
                if 'TEST' in text or 'Fatal Lua' in text or 'Out of sync' in text or 'tick limit' in text:
                    seen['last'] = text
                if seen['fail'] is None and FAIL_LINE.search(text):
                    seen['fail'] = text
                elif seen['pass'] is None and PASS_LINE.search(text):
                    seen['pass'] = text

        reader = threading.Thread(target=pump, daemon=True)
        reader.start()
        stopped_by_runner = None
        while proc.poll() is None:
            time.sleep(0.1)
            # Scripts that don't call Test.Pass/Fail yet: their result line ends the run.
            if seen['fail'] or seen['pass']:
                time.sleep(0.5)  # give Test.Pass/Fail a moment to exit by itself
                if proc.poll() is None:
                    stopped_by_runner = 'result line'
                    proc.kill()
                break
            if time.time() - started > timeout:
                stopped_by_runner = f'timeout after {timeout}s'
                proc.kill()
                break
        proc.wait()
        reader.join(timeout=5)

    code = proc.returncode
    if code is not None and code > 2**31:
        code -= 2**32
    if stopped_by_runner == 'result line':
        verdict = 'FAIL' if seen['fail'] else 'PASS'
        code_text = 'stopped'
    elif stopped_by_runner:
        verdict, code_text = 'FAIL (timeout)', 'stopped'
    else:
        verdict = EXIT_VERDICTS.get(code, 'CRASH')
        code_text = str(code)
        if verdict == 'PASS' and seen['fail']:
            verdict = 'FAIL'

    detail = seen['fail'] or (seen['last'] if verdict != 'PASS' else '')
    if verdict == 'CRASH' or (verdict.startswith('FAIL') and not detail):
        errors = [l for l in stderr_path.read_text(encoding='utf-8', errors='replace').splitlines() if 'Exception' in l]
        detail = errors[-1].strip() if errors else (stopped_by_runner or f'exit code {code}')
    if stopped_by_runner and stopped_by_runner != 'result line':
        detail = f'{stopped_by_runner}; last: {seen["last"]}'
    detail = re.sub(r'^Lua debug: ', '', detail)
    return {'map': name, 'verdict': verdict, 'exit': code_text, 'seconds': time.time() - started, 'detail': detail}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--mod-dir', type=Path, default=Path.cwd(), help='mod repository (default: current folder)')
    parser.add_argument('--mod', help='mod id (default: MOD_ID from mod.config)')
    parser.add_argument('--engine', type=Path, help='engine folder (default: <mod-dir>/engine)')
    parser.add_argument('--results', type=Path, help='results folder (default: <mod-dir>/test-results)')
    parser.add_argument('--only', help='comma-separated map names')
    parser.add_argument('--jobs', type=int, default=max(1, min(8, (os.cpu_count() or 2) // 2)),
                        help='games at once (default: half the cores, at most 8)')
    parser.add_argument('--windowed', action='store_true', help='run with a window at normal speed, one at a time')
    args = parser.parse_args()

    args.mod_dir = args.mod_dir.resolve()
    mod_config = read_mod_config(args.mod_dir)
    args.mod = args.mod or mod_config.get('MOD_ID')
    if not args.mod:
        sys.exit('No mod id: pass --mod or run from a folder with mod.config')
    args.engine = (args.engine or args.mod_dir / mod_config.get('ENGINE_DIRECTORY', 'engine')).resolve()
    if not (args.engine / 'bin').is_dir():
        sys.exit(f'Engine not built: {args.engine / "bin"} is missing')
    results = (args.results or args.mod_dir / 'test-results').resolve()
    results.mkdir(parents=True, exist_ok=True)

    config_path = args.mod_dir / 'tests.json'
    config = json.loads(config_path.read_text(encoding='utf-8')) if config_path.is_file() else {}
    maps = args.only.split(',') if args.only else [
        m for m in find_maps(args.mod_dir, args.mod, config.get('content_maps', True)) if m not in config.get('manual', [])]
    if not maps:
        sys.exit('No test maps found')
    jobs = 1 if args.windowed else max(1, args.jobs)
    print(f'{len(maps)} maps, {jobs} at a time, {"windowed" if args.windowed else "headless, uncapped"}; '
          f'results in {results}', flush=True)

    started = time.time()
    rows = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as pool:
        futures = {pool.submit(run_map, m, args, config, results): m for m in maps}
        for future in concurrent.futures.as_completed(futures):
            r = future.result()
            rows.append(r)
            print(f'{r["map"]:26} {r["verdict"]:18} {r["seconds"]:6.1f}s  {r["detail"][:110]}', flush=True)
    total = time.time() - started

    rows.sort(key=lambda r: r['map'])
    passed = sum(r['verdict'] == 'PASS' for r in rows)
    lines = ['# Test suite results', '',
             f'{passed}/{len(rows)} maps passed in {total:.0f}s ({jobs} at a time, '
             f'{"windowed" if args.windowed else "headless, uncapped"}); engine: {args.engine}', '',
             '| Map | Result | Exit | Time | Detail |', '|---|---|---|---:|---|']
    lines += [f'| {r["map"]} | {r["verdict"]} | {r["exit"]} | {r["seconds"]:.0f}s | {r["detail"].replace("|", "/")} |'
              for r in rows]
    (results / 'summary.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(f'\n{passed}/{len(rows)} passed in {total:.0f}s; see {results / "summary.md"}')
    sys.exit(0 if passed == len(rows) else 1)


if __name__ == '__main__':
    main()
