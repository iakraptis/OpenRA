# Headless test runs: switching a mod over

From the engine session, 2026-11-22. For the agents working on OpenSYW, OpenPW and OpenWBC. Background and
measurements: `../../plan.md` (Phases 1–3).

## What the engine now offers

On the fork's branch `headless-rl` (= `netframe` + the headless work; give the mod the commit hash the user
publishes):

- `Game.Platform=Null`: the game with no window, GPU or audio. Tests behave as windowed (same verdicts on every
  OpenPW and OpenSYW map, replays in sync).
- `Launch.Uncapped=true`: no waiting for the game speed's timestep. OpenPW `bot-test` 654 s → 68 s; OpenSYW
  `bot-test` 131 s → 6.6 s.
- A Lua `Test` global: `Test.Pass(line?)`, `Test.Fail(line?)`, `Test.Headless`. Headless, the game then exits with a
  code (`0` pass, `1` fail, `2` `Launch.MaxTicks` reached, `4` fatal Lua error, `5` out of sync, `-1` crash).
  Windowed, nothing changes: the game keeps running.
- `Engine.LogDir` / `Engine.ReplayDir`: each run's logs and replay in its own folder.
- **`engine/tools/run_tests.py`**: runs every `*-test` map (the mod's and the installer's), headless, several at
  once. OpenPW's 13 maps take 87 s, OpenSYW's 9 take 8 s. `--windowed --only <map>` to watch one.
- Headless runs never write the player's `settings.yaml`.

## Steps

Follow the repo's own rules (branch, no push, the user merges, report what wasn't checked).

1. **Engine.** Set `ENGINE_VERSION` in `mod.config` to the commit hash the user gives you (on `iakraptis/OpenRA`), then
   `./make.cmd all`. It includes `jmods` (movement fix) and `netframe` (NetFrameInterval per game speed, default 3 as
   before) underneath. **OpenWBC** is still on `release-20250330`: do the bleed update (`OpenWBC.md`) first.
2. **testlib.lua.** After the line that prints the result, report it to the engine. In every test map's
   `testlib.lua` (and the installer's templates, e.g. OpenPW's `AssetInstaller/MapTemplates/*/testlib.lua`):
   ```lua
   if #failures == 0 then
       print(testName .. " TEST PASS (" .. checks .. " checks)")
       if Test then Test.Pass() end
   else
       print(testName .. " TEST FAIL: " .. ...)
       if Test then Test.Fail() end
   end
   ```
   `if Test then` keeps the scripts working on older engines. Without this step the runner still works (it reads the
   PASS/FAIL line and stops the game), but a test that never prints a result only ends at its timeout.
3. **Runner.** Replace the body of `run_tests.py` with a call to the shared runner, keeping your build and
   `--check-yaml` steps, e.g.:
   ```python
   subprocess.run([sys.executable, 'engine/tools/run_tests.py', *sys.argv[1:]], check=False)
   ```
   Or call `python engine/tools/run_tests.py` directly. Per-map settings go in `tests.json` at the repository root:
   ```json
   {"manual": [], "max_ticks": {"bot-test": 45000}, "timeout_seconds": {"bot-test": 900}}
   ```
   (`default_max_ticks`, `default_timeout_seconds` = 600, `content_maps` = true are the other keys.) Bot battles
   (`battle-*` maps) aren't run by it yet; that is Phase 4.
4. **Compare.** Run the suite headless and once windowed (the old way, or `--windowed` per map) and confirm the
   same verdicts. Report the times.
5. **Visual checks stay windowed.** Rendering, effects, sound and screenshots aren't exercised headless; reports
   keep saying what wasn't seen in the game.

## Known state on 2026-11-22 (same windowed and headless)

- **OpenPW `tyrano-test` fails since the "balance" commit `6384406`**: "it has their mean health (281 of 400); each
  has its health share (148, 148)". That commit changed `rules/tyrano/units.yaml` and `weapons/tyrano.yaml` but not
  the test's expected values. Confirmed windowed on the same build. Update the test or the balance.
- OpenPW `bot-medium-test`: "MedElf's attack has a Pixie with it" (failed before too).
- OpenSYW `pathing-test`: the bridge crossing (work in progress, see `OpenSYW-ramp.md`). Its numbers vary between
  runs because each game gets a new random seed.

## Good to know

- A replay recorded by a headless run sits next to its logs. Played back headless
  (`Game.Platform=Null Launch.Uncapped=true Launch.Replay=<file>`), it exits `0` when it reaches its end in sync and
  `5` on a desync. That makes it a quick check that a change didn't alter the simulation.
- Headless runs read the player's settings but pass a pinned 1920×1080 screen, so panel layouts don't depend on the
  player's window.
