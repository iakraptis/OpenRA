# Headless test runs and RL bridge: plan

Branch `headless-rl`, recreated 2026-11-21 from `jmods` (`9f29d43`) = upstream bleed `4cc9a9f` + one movement fix
("Move: plan the first path through other units, not around them"); rebased 2026-11-22 onto `netframe` (`90e2d05` =
`jmods` + NetFrameInterval per game speed), which OpenPW now uses. Engine fork: `iakraptis/OpenRA`. Upstream's
`AGENTS.md` was removed from this fork by its owner (2026-11-22): the fork is independent of the OpenRA project.

Goals, in order:

1. **Headless tests.** Run the mods' Lua test maps with no window, GPU or audio, as fast as the CPU allows, several
   at once, each with a clear exit code.
2. **More bot battles.** Use that speed to run many AI games per race pairing, so balance conclusions don't rest on
   a single game.
3. **RL / external agents.** Let a Python agent (scripted, LLM or RL) play our mods through OpenRA-RL's gRPC bridge.

Status (2026-11-22): **Phases 1–3 done in the engine** (committed on `headless-rl`, not pushed). Rebased onto
`netframe` (`90e2d05`), which OpenPW now uses. OpenPW's whole suite runs in 87 s (was ~18 min), OpenSYW's in 8 s (was
~3.7 min), same verdicts as windowed. Next: push, mods switch over (`docs/mod-updates/headless-tests.md`), then Phase 4.

---

## 1. Where we are

### 1.1 Engine and mods

| Mod | Branch | Engine |
|---|---|---|
| OpenSYW | `pathing-bridge` | fork commit `9f29d43` (`jmods`) |
| OpenPW (`../primwars`) | `engine-bleed` | fork commit `9f29d43` (`jmods`) |
| OpenWBC | `mechanics` | upstream `release-20250330` (not updated yet; handoff in `docs/mod-updates/OpenWBC.md`) |

- The mods pin the fork by full commit hash
  (`AUTOMATIC_ENGINE_SOURCE="https://github.com/iakraptis/OpenRA/archive/${ENGINE_VERSION}.zip"`).
  New engine work reaches them by pushing the branch and bumping that hash.
- Bleed needs .NET 10 (`net10.0`, C# 13); SDK 10.0.404 is installed. Engine solution: `OpenRA.slnx`.
- The engine-update handoffs and API notes stay in `docs/mod-updates/` (`api-changes.md`, one file per mod).

### 1.2 How tests run today

- Each mod's `run_tests.py` starts the windowed `OpenRA.exe` with `Launch.Map=<test>`, **one map at a time**. It
  kills every `OpenRA.exe` first, and polls `%APPDATA%\OpenRA\Logs\lua.log` and stdout once a second for
  `TEST PASS` / `TEST FAIL`. `lua.log` is only flushed when the game exits. Timeouts are wall-clock.
- `Game.Loop()` runs one logic tick per `Timestep` of real time and sleeps in between, rendering at least once per
  tick. Test speeds: PW `test` speed `Timestep: 14` (≈71 ticks/s ceiling), SYW `Timestep: 8` (≈125 ticks/s).

### 1.3 Measurements (2026-11-21)

Suite times from the mods' own `test-results/`:

| Mod | Suite | Total | Longest map |
|---|---|---:|---|
| OpenPW | 12 maps (`test-results/engine-bleed/`) | 1087 s (~18 min) | `bot-test` 654 s (runs to its 40,000-tick cap), `bot-medium-test` 138 s, `gather-test` 89 s |
| OpenPW | `--battles` (bot-test + `battle-*` maps) | ~90 min (per `run_tests.py`) | |
| OpenSYW | 8 maps (`test-results/bleed-4cc9a9f/`) | 223 s | `bot-test` 131 s |
| OpenWBC | 6 maps (2026-11-18) | 156 s | `knights-test` 35 s |

- **CPU use:** OpenPW `bot-test`, windowed at full test speed, early game (seconds 25–65), used **21% of one core**
  on a 16-core machine, including rendering. The game spends most of each tick sleeping until the clock allows the
  next one. Late-game ticks will cost more; this sample is a lower bound on cost per tick.
- `bot-test` reaches 40,000 ticks in 654 s ≈ 61 ticks/s, close to the ≈71 ticks/s clock ceiling. The run is clock-bound.
- Battle statistics currently come from **one game per race pairing** (`battles.md`: `Games 1`).

**Estimate, to be confirmed by Phase 1:** 3–5× faster per test without clock pacing and rendering, plus parallel runs
across cores. That would put the OpenPW suite at a few minutes and `--battles` at 10–20 minutes.

### 1.4 OpenRA-RL (https://github.com/yxc20089/OpenRA-RL, reviewed at `5dadd44`)

GPL-3.0 (Python repo and engine fork), same as OpenRA and our mods: we reuse the code as is, keeping its headers,
and name the source in each commit (`From yxc20089/OpenRA@9b271c1 <path>`).

- Engine fork `yxc20089/OpenRA@9b271c1`: 51 commits, 46 files (+11.4k lines) on bleed `ef5541c` (2026-02-07). A
  test merge onto `headless-rl` conflicts in 3 files only: `OpenRA.Game/Graphics/SpriteLoader.cs`,
  `OpenRA.Game/Traits/World/ScreenShaker.cs`, and `OpenRA.sln` (deleted upstream; use `OpenRA.slnx`).
- **Headless pieces** (wanted now):
  - `OpenRA.Platforms.Null/NullPlatform.cs` (221 lines): no-op window, GL context, textures, shaders, buffers, font
    and sound; selected with `Game.Platform=Null`; `Game.IsHeadless`.
  - `Game.Loop()` burst mode: up to 5000 `LogicTick()`s per iteration with no sleep or render, backdating
    `OrderManager.LastTickTime`. Theirs only runs while the RL bridge sets a tick scale below 1
    (`OrderManager.IsFastForwarding`).
  - Skip `TickRender` when headless; guards for effects that assume a world renderer (`SpriteEffect`, `NukeLaunch`,
    sound notifications); `PerfHistory.Disabled`.
  - Missing-asset tolerance (zero streams, dummy sprites, content check skipped) and exception swallowing (`Actor`
    trait creation, `World` `IWorldLoaded`) whenever headless. **Not wanted for tests**: it turns real failures into
    passes (decision 2).
- **RL pieces** (later): `ExternalBotBridge` (`IBot`, `Type: rl-agent`), gRPC service `RLBridge` (`GameSession`,
  `GetState`, `FastAdvance` with interrupts, `CreateSession` / `DestroySession`), `ActionHandler` (21 action types),
  `ObservationSerializer`, `RLSessionManager` (many games per process sharing `ModData`), `BulkProductionQueue`,
  `Launch.Bots`, `Launch.MultiSession`, `rl-bot.yaml`. Packages `Grpc.AspNetCore`, `Google.Protobuf`, `Grpc.Tools` in
  `OpenRA.Mods.Common`. Python side: environment, reward, MCP server, LLM agent; Red Alert assumptions throughout
  (`game_data.py` is a hand-written RA unit table).

---

## 2. Decisions (2026-11-21)

1. **Headless first, RL later.** Take OpenRA-RL's headless pieces now, by copying the files and changes we need.
   Merge the rest of their fork (the RL bridge and its gRPC packages) only when RL work starts (Phase 5), so the
   mods' packages don't carry ASP.NET Core / gRPC before then.
2. **Strict headless for tests.** `Game.Platform=Null` only replaces the window, GPU and audio. Missing files, trait
   exceptions and Lua errors fail exactly as in the windowed game. Their tolerance code, if taken at all, goes behind
   a separate `Game.AllowMissingAssets=true` switch, off by default (Phase 6).
3. **Uncapped speed is its own switch** (`Launch.Uncapped=true`), using their burst loop for the whole game, not tied
   to the RL tick scale.
4. **Prove the speed-up before building the rest.** Phase 1 ends with a measurement; Phases 2–4 go ahead only if it
   is worth it.
5. **One shared test runner** in the engine repo, replacing the three copies of `run_tests.py`.
6. **Engine changes reach the mods by commit hash**, as now. Keep `jmods`'s movement fix; add our work on top.

---

## 3. Phases

### Phase 1: null platform and uncapped loop, then measure (done 2026-11-21)

Changes (uncommitted on `headless-rl`):

| File | Change |
|---|---|
| `OpenRA.Platforms.Null/` (new), `OpenRA.slnx` | Their null platform, adapted: standard header; `ITexture.SetSubData` (added upstream since their base); `GetData()` returns a zeroed `w*h*4` buffer; style fixes. The mods' engine `make` builds the `.slnx`, so the DLL lands in `bin/`. |
| `OpenRA.Game/Game.cs` | `Game.IsHeadless` (`Game.Platform=Null`); `TickRender` skipped when headless; `Game.IsUncapped` from `Launch.Uncapped=true` (ignored, with a message, without the null platform); `UncappedLoop()`: bursts of up to 5000 `LogicTick()`s with the tick time backdated, no render; sleeps 1 ms when no world frame advanced (lobby, waiting for the server). **The UI ticks once after every world tick** (see findings). |
| `OpenRA.Game/Support/LaunchArguments.cs` | `Uncapped` documented. |
| `OpenRA.Game/Network/OrderManager.cs` | A desync also prints `Out of sync in frame N` to stdout. |
| `OpenRA.Game/Network/ReplayConnection.cs` | Their fix: replays with no metadata (game stopped, not quit) and truncated last packets play; `FinalGameTick` falls back to the last frame. |
| `OpenRA.Mods.Common/LoadScreens/BlankLoadScreen.cs` | Headless `Launch.Replay` plays directly instead of opening the compatibility dialog nobody can click. |

The cursor manager is kept (we have the assets). Build: 0 warnings with `-warnaserror`; 509 unit tests pass.

Results (probe scripts in the session scratchpad; mods built from scratch copies against this branch):

| Map | Windowed | Uncapped | Speed-up | Verdict |
|---|---:|---:|---:|---|
| OpenPW `bot-test` (39,751 ticks) | 654 s | 68 s | 9.6× | PASS (18 checks), same |
| OpenSYW `bot-test` (~12,000 ticks) | 131 s | 6.6 s | 20× | PASS, same |
| OpenPW other 11 maps | ~433 s | 98 s | 4.4× | same verdicts (`bot-medium-test` fails the same check as windowed) |
| OpenSYW other 8 maps | ~92 s | ~17 s | 5× | same verdicts (`pathing-test` fails as windowed) |

- Start-up dominates short tests: ~7 s for OpenPW (12-map suite ≈ 7 s × 12), ~1.7 s for OpenSYW. The test logic
  itself runs in well under a second. Phase 3's parallel runs attack the start-up cost.
- Live uncapped speed: OpenPW ~630 ticks/s, OpenSYW ~2,400 ticks/s.
- No window appeared in headless runs.

Determinism:
- The uncapped OpenPW `bot-test` replayed (uncapped) **in sync**, with identical bot reports (workers, buildings,
  army, berries, kills, losses) at every 5,000-tick checkpoint through tick 35,001.
- A `bot-test` recorded **windowed** on this build replayed **uncapped in sync**, identical reports at ticks 0, 5,001
  and 10,001; a 1,081-frame windowed replay from the mod's own engine build too.
- Negative control: a replay recorded on the engine without the `jmods` movement fix desynced at frame 122, so the
  check does detect a different simulation.
- Repeated runs of a test differ by design (each game gets a new random seed), e.g. OpenSYW `pathing-test` gave
  12/640, 12/665 (uncapped) and 10/585 (headless at normal speed).

Findings:
1. **The UI must tick with the world.** The UI normally ticks on a wall-clock timer. Uncapped, OpenSYW's
   `start-test`, `spell-test` and `naval-air-test` failed their panel checks (they select a unit, then read the
   production, spell and cargo panels after the next UI tick). Fixed by ticking the UI once after every world tick;
   no measurable speed cost.
2. **Observer UI crash on bleed (all three mods; not headless-specific).** Upstream `7e8f4a3479` changed the observer
   shroud selector's `LABEL` (and the stats panels' `PLAYER`) to `LabelWithTooltip`. The mods' own
   `chrome/ingame-observer.yaml` still has `Label@LABEL`, so watching a replay or spectating crashes with an
   `InvalidCastException` in `ObserverShroudSelectorLogic`. Added to `docs/mod-updates/api-changes.md`.
3. **Uncapped replay playback is slow** (~30–150 ticks/s against ~630 live). Not needed for tests; look at it
   before using replays for anything bulk.
4. Headless at normal speed (`Game.Platform=Null` without `Launch.Uncapped`) also works, and still runs the draw
   pass into no-ops: a fallback if a test ever depends on drawing.

**Decision point: passed** (9.6× and 20× on `bot-test`, target ≥ 3×).

### Phase 2: test protocol (done 2026-11-22, `6d4b295637`)

- [x] Exit codes (`RunStatus`): `0` pass, `1` fail, `2` tick limit, `4` fatal Lua error, `5` out of sync, `-1` crash
      (unchanged; report on stderr, no dialog). `Game.EndTest(status, message)`: first result wins, printed to stdout;
      headless the game exits with it, windowed it keeps running.
- [x] Lua global `Test`: `Test.Pass(line?)`, `Test.Fail(line?)`, `Test.Headless`. (No `Test.Log`: Lua `print`
      already reaches stdout as `Lua debug: …` on bleed.)
- [x] `Launch.MaxTicks=N`.
- [x] A headless replay ends at its last recorded frame (exit `0`, "Replay finished in sync…") instead of waiting
      forever; a desync ends it with `5`.
- [x] Null platform falls back to 1920×1080 when the settings give no size (the default `PseudoFullscreen` is `0×0`;
      it crashed OpenPW's interface bar layout with a division by zero).
- Checked on OpenPW: each code from a matching map or replay. `combat-test` 0; a copy with a failing check 1; a copy
  with a Lua error 4; `bot-test` with `MaxTicks=300` 2; a `bot-test` replay 0, and with every Demon unit's cost
  changed 5 (out of sync at frame 24). Changing one building's cost didn't desync: it isn't bought in 2,000 ticks.
- [ ] Mods' `testlib.lua`: call `Test.Pass` / `Test.Fail` (`if Test then …`). Mod agents; see
      `docs/mod-updates/headless-tests.md`.

**Found while testing (fixed, `31016261c8`): headless runs wrote the player's settings.** Starting a local game saves
the skirmish lobby settings, which persisted the command-line `Game.Platform=Null` into
`%APPDATA%\OpenRA\settings.yaml`. Engines without the null platform fall back to the normal window; this branch's
build would have started without one. The line was removed from the settings file (backup in the session
scratchpad), and `Settings.Save` is now a no-op on the null platform.

### Phase 3: parallel runs and one shared runner (done 2026-11-22, `45e568cb05`)

- [x] `Engine.LogDir=<path>` and `Engine.ReplayDir=<path>`: one game's logs and new replays in their own folders;
      settings and `Content/<mod>/` stay shared. (The logger already avoided crashing on a busy file by switching to
      `lua.log.1`, but a runner couldn't tell which file was its own.)
- [x] `tools/run_tests.py`: every `*-test` map of the mod (`mods/<id>/maps` and the installer's `Content/<mod>/maps` or
      `Content/<mod>/<version>/maps`); `--jobs N` (default half the cores, at most 8); each run headless + uncapped
      with a pinned 1920×1080 screen, its own `logs/`, replay, `stdout.txt`, `stderr.txt`; verdict from the exit code,
      or from the PASS/FAIL line for scripts that don't call `Test.Pass/Fail` yet (it then stops that game only);
      `--windowed`; optional `tests.json`; the same `summary.md` table plus an exit-code column. Never touches other
      processes.
- [x] Measured on the real mod folders: OpenPW 13 maps in **87 s** (8 at a time; `bot-test` 87 s alone dominates),
      OpenSYW 9 maps in **8 s**. Verdicts as windowed: OpenPW `tyrano-test` (since OpenPW's "balance" commit
      `6384406`, confirmed windowed on the same build) and `bot-medium-test`, OpenSYW `pathing-test`.
- [ ] Each mod: bump the engine hash (after the push), switch to the shared runner, compare with windowed. Handoff:
      `docs/mod-updates/headless-tests.md`.

### Phase 4: more bot battles

- [ ] `--battles --games N`: N seeded games per race pairing, in parallel. `battle_stats.py` reports means and spread,
      not single results.
- [ ] Record what a full battle run costs at N = 10 and N = 20.

### Phase 5: RL bridge

- [ ] Merge the rest of `yxc20089/OpenRA@9b271c1` (RL bridge, gRPC, `Launch.Bots`, `Launch.MultiSession`). Resolve
      `SpriteLoader.cs`, `ScreenShaker.cs`, and the `.sln` → `.slnx` change.
- [ ] Decide where the RL code lives. Their layout (`OpenRA.Mods.Common`) keeps future merges easy; a separate
      `OpenRA.Mods.RL` assembly keeps gRPC out of the mods' packages. Measure the package size difference first.
- [ ] Validate on stock RA: their `pytest tests/`, `examples/scripted_bot.py`, `FastAdvance` speed.
- [ ] Python side: fork `yxc20089/OpenRA-RL` and point its `OpenRA` submodule at our branch (open question 1).
- [ ] Mod support:
  - `rl-bot.yaml` per mod;
  - trait interfaces `IRLObservationContributor` / `IRLActionHandler` for mod-specific state and actions (PW berries
    and population, WBC heroes, SYW spells);
  - a utility command `--rl-game-data` that exports a mod's actors, costs, prerequisites and weapons as JSON,
    replacing the hand-written `game_data.py`.
- [ ] Windows `launch-rl.cmd`.

### Phase 6 (optional): runs without converted content

- [ ] Their missing-asset tolerance behind `Game.AllowMissingAssets`, for CI or Docker RL only.

### Phase 7 (optional): many games in one process

- [ ] Their `RLSessionManager` for RL throughput; evaluate it for tests (load `ModData` once). Risk: static `Game`
      state, and Lua and some traits assume one world per process.

---

## 4. Risks and things to check

- **Hidden render dependencies.** Some logic may assume a world renderer, a real texture or real font sizes (widgets,
  effects, `ScreenMap`). Phase 1 runs every existing test map headless to find them.
- **Determinism.** Uncapped runs must give the same results as windowed ones (Phase 1 check).
- **The local server.** Every net frame goes through the in-process loopback server; it may cap the speed.
- **What headless can't check.** Rendering, effects, sound and screenshots still need the windowed game. Reports
  keep saying what wasn't seen in the game.
- **OpenWBC** is still on `release-20250330`. It can't use headless runs until it moves to the fork commit.

## 5. Measurements log

| Date | Engine | Mode | Map / suite | Time | Ticks/s | Notes |
|---|---|---|---|---:|---:|---|
| 2026-11-21 | `9f29d43` | windowed, sequential | OpenPW suite (12 maps) | 1087 s | | from `primwars/test-results/engine-bleed/` |
| 2026-11-21 | `9f29d43` | windowed | OpenPW `bot-test` | 654 s | ~61 | 40,000-tick cap |
| 2026-11-21 | `9f29d43` | windowed | OpenPW `bot-test`, seconds 25–65 | | | 21% of one core |
| 2026-11-21 | `4cc9a9f` | windowed, sequential | OpenSYW suite (8 maps) | 223 s | | from `OpenSYW/test-results/bleed-4cc9a9f/` |
| 2026-11-21 | `headless-rl` (Phase 1) | uncapped, sequential | OpenPW `bot-test` | 68 s | ~630 | PASS; start-up 6.9 s |
| 2026-11-21 | `headless-rl` (Phase 1) | uncapped, sequential | OpenPW 12 maps | 166 s | | was 1087 s windowed |
| 2026-11-21 | `headless-rl` (Phase 1) | uncapped, sequential | OpenSYW `bot-test` | 6.6 s | ~2,400 | PASS; start-up 1.5 s |
| 2026-11-21 | `headless-rl` (Phase 1) | uncapped, sequential | OpenSYW 9 maps | 23 s | | was ~223 s windowed (8 maps) |
| 2026-11-22 | `headless-rl` (Phase 3, on `netframe`) | shared runner, 8 at a time | OpenPW 13 maps (incl. `bot-test`) | 87 s | | was ~1087 s windowed |
| 2026-11-22 | `headless-rl` (Phase 3, on `netframe`) | shared runner, 8 at a time | OpenSYW 9 maps | 8 s | | was ~223 s windowed |

## 6. Open questions

1. Where the Python side lives: a fork of `OpenRA-RL` (recommended) or a folder in each mod repo.
2. Whether to offer the null platform, uncapped mode and `Test` API upstream to OpenRA later.
3. When OpenWBC moves to the fork engine.
