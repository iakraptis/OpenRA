# OpenWBC: update to the new engine (OpenRA bleed, .NET 10)

From the engine session (`../OpenRA`, branch `headless-rl`), 2026-11-20. The full plan is `../OpenRA/plan.md`. Read
`../OpenRA/docs/mod-updates/api-changes.md` first: it explains every engine change listed below.

## Why

The engine is moving from `release-20250330` to a pinned commit of upstream OpenRA `bleed`. Upstream has made no
release since then. The move brings a headless mode (no window, much faster test runs, parallel tests) and a gRPC
bridge for scripted/LLM/RL agents, both from the GPL-3 project OpenRA-RL, which is built on bleed. OpenWBC is the
**pilot**: it is the smallest of the three mods, so it goes first.

## What you need to know

- **Engine target:** upstream bleed `4cc9a9f6299c807c373bb233d9729518c0160c77` (2026-11-17). Later the engine session
  will publish a tag on `iakraptis/OpenRA` (this commit plus headless and RL additions); you will then change only
  `ENGINE_VERSION` and `AUTOMATIC_ENGINE_SOURCE`. Don't wait for it.
- **.NET 10** is required (`net10.0`, C# 13). SDK 10.0.404 is installed on this machine. Mono is no longer supported.
- **Compile survey.** A copy of `OpenRA.Mods.Wbc` (`mechanics`, 2026-11-18) was compiled against that commit, fixed,
  and rebuilt until it compiled:
  - **13 errors** in total (12 in the first wave, 1 hidden behind them);
  - then **about 8 style findings** under `-warnaserror` with this repo's `.editorconfig` (7 `IDE0028`).
  The fixes below are known to compile; they haven't been run in the game.

## Steps

Follow the repo's own rules (`workflow.md`): commits on the working branch, no push, the user merges, style check
and YAML lint before each commit, plain-language report with commit hash and what wasn't checked in the game.

1. **Branch.** Commit or park the current `mechanics` work first. Then create `engine-bleed` from an up-to-date
   `main`. If `mechanics` should be merged first, ask the user.
2. **Baseline on the old engine.** Before changing anything: `python run_tests.py` (full suite, with bot battles), and
   keep the results as `test-results/baseline-release-20250330/` (summary plus per-map logs). Record the total time
   and each map's time. You'll compare against this in step 8.
3. **Pin the engine.** In `mod.config`:
   ```
   ENGINE_VERSION="4cc9a9f6299c807c373bb233d9729518c0160c77"
   AUTOMATIC_ENGINE_SOURCE="https://github.com/OpenRA/OpenRA/archive/${ENGINE_VERSION}.zip"
   ```
   Then `./make.cmd all`. It replaces `engine/` (gitignored) automatically.
4. **Compile fixes.**
   - `[Sync]` → `[VerifySync]` (attribute renamed, same meaning), 10 places:
     `Traits/Buildings/WbcUnderConstruction.cs` (1), `Traits/Player/WbcResources.cs` (4), `Traits/WbcMapObject.cs` (2),
     `Traits/WbcMine.cs` (3).
   - `INotifyBuildingPlaced` now passes the building: `void BuildingPlaced(Actor self, Actor building)`.
     `Traits/WbcBuilder.cs:66` works around the old signature. Its comment says the engine didn't say which building
     was placed, so it searches for this owner's site placed on this tick. **Use the `building` argument directly**
     and drop the search. That's a behaviour fix, so give it a check in the relevant test map.
   - **`Orders/WbcUnitOrderGenerator.cs` needs a `(World)` constructor:**
     `public WbcUnitOrderGenerator(World world) : base(world) { }`. It is the mod's `DefaultOrderGenerator`
     (`mod.yaml:51`). Bleed creates it through a `(World)` constructor and **silently gets `null` without one, so
     the player would have no input.** No test map would catch this; launch the game and click around.
5. **YAML.** `./utility.cmd wbc --update-mod release-20250330 --apply` (add `--detailed` first, without `--apply`, to
   review). Expected hit: **`RemoveAlwaysVisible`** in 6 files (`rules/defaults/base.yaml`,
   `rules/defaults/map-objects.yaml`, `rules/mpspawn.yaml`, `rules/placeholder.yaml`, `rules/player.yaml`,
   `rules/world.yaml`). `AlwaysVisible` was removed because it is now the default. Check that actors meant to hide
   under fog still carry `HiddenUnderFog` / `FrozenUnderFog`.
   - `--update-mod` only changes files on disk. **YAML that the asset installer or map converter writes**
     (converted maps, generated test maps, generated rules) must be fixed in that C# generator code, then re-run
     the installer.
6. **Scripts and packaging** (the upstream Mod SDK has not been updated for bleed):
   - `packaging/windows/buildpackage.sh`: the engine's `install_assemblies` no longer takes a runtime argument. The
     new signature is `SRC DEST TARGETPLATFORM COPY_GENERIC_LAUNCHER COPY_CNC_DLL COPY_D2K_DLL`, so drop `"net6"`.
     Fix the mod-side `install_mod_assemblies` the same way.
   - `Makefile` comments and defaults mentioning `RUNTIME=net6` / Mono: update or remove.
   - Any CI workflow: `dotnet-version: '10.0.x'`.
   - Build a portable package once and launch it on this machine, to confirm the .NET 10 runtime is bundled.
7. **Style.** `./make.cmd check` with `-warnaserror`. Expect about 8 findings, mostly `IDE0028`
   (`dotnet format style --diagnostics IDE0028` fixes them).
8. **Compare with the baseline.**
   - Full suite plus bot battles. Every map that passed before must pass.
   - **AI:** upstream changed `BaseBuilderBotModule` and other bot modules. Compare battle outcomes and lengths with
     the baseline and **report the differences**. Don't retune the AI unless the user asks.
   - Launch the game once, windowed, and play a short skirmish; list what you didn't see.
9. **Re-diff copied upstream code.** Any class in `OpenRA.Mods.Wbc` copied or adapted from an upstream class won't get
   upstream's fixes. Compare each with its bleed version (in `engine/`) and note what changed.
10. **Report** to the user: commits, test results against the baseline, AI differences, what wasn't checked in the
    game. Update `plan.md` (decision dated 2026-11-20, engine pin).

## Things that changed upstream that may matter to WBC

- Mouse buttons for order generators come from the `MouseControlStyle` setting (default `Modern`), not hard-coded
  left/right. `WbcUnitOrderGenerator` inherits this from `UnitOrderGenerator`. If you add a targeting mode, derive
  from `OrderGenerator`, pick an `ActionType` (`ConfirmOrder` = **right** button under `Modern`; `SupportPower`,
  `PlaceBuilding`, `GlobalCommand` = left), and don't check `MouseButton.Right` inside `OrderInner` (see
  `api-changes.md`).
- Viewport positions are now `System.Numerics.Vector2` (`Viewport.CenterLocation`); `float2` / `float3` usage in the
  engine is being replaced by `System.Numerics`.

## Not your job

The headless switches (`Game.Platform=Null`, `Launch.Uncapped`, the Lua `Test` API, the shared parallel runner) are
built in the engine (plan.md Phases 1, 3 and 4). When they land, you'll get a short follow-up: switch to the engine
tag, and make `testlib.lua` call `Test.Pass` / `Test.Fail`.
