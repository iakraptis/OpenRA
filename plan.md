# Headless test runs and RL bridge: plan

Branch `headless-rl`, recreated 2026-11-21 from `jmods` (`9f29d43`) = upstream bleed `4cc9a9f` + one movement fix
("Move: plan the first path through other units, not around them"). Engine fork: `iakraptis/OpenRA`.

Goals, in order:

1. **Headless tests.** Run the mods' Lua test maps with no window, GPU or audio, as fast as the CPU allows, several
   at once, each with a clear exit code.
2. **More bot battles.** Use that speed to run many AI games per race pairing, so balance conclusions don't rest on
   a single game.
3. **RL / external agents.** Let a Python agent (scripted, LLM or RL) play our mods through OpenRA-RL's gRPC bridge.

Status (2026-11-21): **Phase 1 done** (uncommitted on `headless-rl`). OpenPW `bot-test` 654 s → 68 s, OpenSYW
`bot-test` 131 s → 6.6 s, same verdicts as windowed on every map, replays in sync. Next: Phase 2.

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

### Phase 2: test protocol

- [ ] `Launch.MaxTicks=N`: end with a timeout after N world ticks (replaces wall-clock timeouts).
- [ ] Lua `Test` global: `Test.Pass()`, `Test.Fail(message)`, `Test.Log(message)`. Exit codes: `0` pass, `1` fail,
      `2` tick budget, `3` crash (stack trace on stderr), `4` fatal Lua error. Flush logs before exiting.
- [ ] When headless, echo Lua `print` and `Fatal Lua Error` to stdout as well as `lua.log`.
- [ ] Mods' `testlib.lua`: call `Test.Pass` / `Test.Fail`, keeping the `TEST PASS` lines for windowed runs.

### Phase 3: parallel runs and one shared runner

- [ ] `Engine.LogDir=<path>`: per-run log folder while `SupportDir` (and `Content/<mod>/`) stays shared. Fallback: a
      temporary support dir with a junction to `Content`.
- [ ] `tools/run_tests.py` in the engine repo, called from each mod with its mod id, map folders and tick budgets:
  - no `taskkill` (it also kills a game being played);
  - `--jobs N` (default: cores / 2);
  - each run with `Game.Platform=Null Launch.Uncapped=true Launch.MaxTicks=… Engine.LogDir=test-results/<map>/`;
  - verdict from the exit code and stdout;
  - `--windowed` to watch one test;
  - same `summary.md` format.
- [ ] Each mod: bump the engine hash, switch `run_tests.py` to the shared runner, run the full suite. Verdicts must
      match the windowed baseline.

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

## 6. Open questions

1. Where the Python side lives: a fork of `OpenRA-RL` (recommended) or a folder in each mod repo.
2. Whether to offer the null platform, uncapped mode and `Test` API upstream to OpenRA later.
3. When OpenWBC moves to the fork engine.
