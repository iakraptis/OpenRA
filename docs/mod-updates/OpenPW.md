# OpenPW: update to the new engine (OpenRA bleed, .NET 10)

From the engine session (`../OpenRA`, branch `headless-rl`), 2026-11-20. The full plan is `../OpenRA/plan.md`. Read
`../OpenRA/docs/mod-updates/api-changes.md` first: it explains every engine change listed below.

## Why

The engine is moving from `release-20250330` to a pinned commit of upstream OpenRA `bleed`. Upstream has made no
release since then. The move brings a headless mode (no window, much faster test runs, parallel tests) and a gRPC
bridge for scripted/LLM/RL agents, both from the GPL-3 project OpenRA-RL, which is built on bleed. OpenWBC goes
first as the pilot; OpenPW can start in parallel, but if OpenWBC's agent finds a surprise, the user may relay it.

## What you need to know

- **Engine target:** upstream bleed `4cc9a9f6299c807c373bb233d9729518c0160c77` (2026-11-17). Later the engine session
  will publish a tag on `iakraptis/OpenRA` (this commit plus headless and RL additions); you will then change only
  `ENGINE_VERSION` and `AUTOMATIC_ENGINE_SOURCE`. Don't wait for it.
- **.NET 10** is required (`net10.0`, C# 13). SDK 10.0.404 is installed on this machine. Mono is no longer supported.
- **Compile survey.** A copy of `OpenRA.Mods.Pw` (branch `pathing`, 2026-11-19) was compiled against that commit,
  fixed, and rebuilt until it compiled:
  - **about 55 errors** in total (13 in the first wave, most of the rest hidden behind them);
  - then **131 style findings** under `-warnaserror` with this repo's `.editorconfig` (69 `CA1305`, 56 `IDE0028`,
    a few others).
  Most of it is the `float2` / `float3` removal in rendering and widget code. The fixes below are known to compile;
  they haven't been run in the game.

## Steps

Follow the repo's own rules (`workflow.md`): commits on the working branch, no push, the user merges, style check
and YAML lint before each commit, plain-language report with commit hash and what wasn't checked in the game.

1. **Branch.** The `pathing` branch is in progress. **Ask the user** whether to finish and merge it first
   (recommended, so the update doesn't mix with pathing changes) or to branch from `main` now. Then create
   `engine-bleed` from the agreed, up-to-date base.
2. **Baseline on the old engine.** Before changing anything: `python run_tests.py` (full suite, with `--battles`), and
   keep the results as `test-results/baseline-release-20250330/` (summary plus per-map logs). Record the total time
   and each map's time. You'll compare against this in step 8.
3. **Pin the engine.** In `mod.config`:
   ```
   ENGINE_VERSION="4cc9a9f6299c807c373bb233d9729518c0160c77"
   AUTOMATIC_ENGINE_SOURCE="https://github.com/OpenRA/OpenRA/archive/${ENGINE_VERSION}.zip"
   ```
   Then `./make.cmd all`. It replaces `engine/` (gitignored) automatically.
4. **Compile fixes** (paths under `OpenRA.Mods.Pw/`; see `api-changes.md` for each change).
   - **`float2` / `float3` were removed** → `System.Numerics.Vector2` / `Vector3` (`using System.Numerics;`).
     - Files: `AssetInstaller/MenuButtons.cs`, `Traits/World/PwExposure.cs`, `Traits/World/PwTerrainRenderer.cs`,
       `Widgets/ExposureRadarWidget.cs`, `Widgets/InterfaceBarWidget.cs`, `Widgets/OutlineWidget.cs`,
       `Widgets/PwEndScreenWidget.cs`, `Widgets/StretchedImageWidget.cs`.
     - Plain renaming covers most of it. The rest:
       - `float3.Ones` → `Vector3.One` (`PwEndScreenWidget.cs:85`, `:91`; `PwTerrainRenderer.cs:439`);
       - `PwTerrainRenderer.cs:432`: `UISpriteRenderable` now takes a `Vector2` screen position, and `.XY` is gone.
         What compiled: `origin.ToVector2() - 0.5f * scale * new Vector2(sprite.Size.X, sprite.Size.Y)`;
       - `PwExposure.cs:209`: `wr.ScreenPosition` returns `Vector2`.
         `wr.Viewport.WorldToViewPx(int2.FromVector(wr.ScreenPosition(Pos)))` compiled; check that truncating
         doesn't shift the exposure overlay by a pixel.
   - **`MapGrid.TileSize` removed**: `PwTerrainRenderer.cs:423` → `world.Map.Rules.TerrainInfo.TileSize`.
   - **Prerequisites** are a struct now: `Traits/BotModules/PwBaseBuilderBotModule.cs:208` →
     `…TraitInfoOrDefault<BuildableInfo>()?.Prerequisites ?? [];`. This one error also breaks type inference
     further down, giving the `'T' does not contain 'Name'` errors at lines ~220 and ~254. They go away with it.
   - **Attack-move**: `Widgets/Logic/CommandPanelLogic.cs:280` →
     `new AttackMoveOrderGenerator(world, attackers.Where(a => !a.IsDead))`. `MouseButtonPreference` is gone; the
     generator resolves its own button.
   - **`Game.InitializeMod` takes a `Manifest`**: `Widgets/Logic/PwContentLogic.cs:83` and `:164` →
     `Game.InitializeMod(Game.Mods[GameMod], …)`.
   - **Order generators.** `IOrderGenerator` now has `MouseButton ActionButton { get; }`. Missing in
     `Orders/AbilityOrderGenerator.cs`, `Orders/BuildAtCellOrderGenerator.cs`, `Orders/PatrolOrderGenerator.cs`,
     `Orders/UnloadAtOrderGenerator.cs`. Each implements `IOrderGenerator` directly and hard-codes left = confirm,
     right = cancel.
     - Upstream resolves buttons from the player's `MouseControlStyle` setting (default **`Modern`**) through
       `Game.Settings.Game.ResolveActionButton(MouseActionType)` / `ResolveCancelButton(...)`. `ConfirmOrder` is
       the **right** button under `Modern`; Keep the right mouse button for spells, abilities, building etc.
   - **`ITiledTerrainRenderer.RenderPreview(WorldRenderer wr, TerrainTile tile, WPos origin)`** is new (a single
     tile, used by the map editor). `Traits/World/PwTerrainRenderer.cs` only has the `TerrainTemplateInfo`
     overload (line 435). Implement it; upstream's version is in
     `engine/OpenRA.Mods.Common/Traits/World/TerrainRenderer.cs` around line 212. Since PW has a custom terrain
     renderer, also re-diff `PwTerrainRenderer` against bleed's `TerrainRenderer` for other upstream changes.
5. **YAML.** `./utility.cmd pw --update-mod release-20250330 --apply` (add `--detailed` first, without `--apply`, to
   review). Expected hits:
   - **`RemoveAlwaysVisible`** in 5 files (`rules/defaults.yaml`, `rules/mpspawn.yaml`, `rules/placeholder.yaml`,
     `rules/player.yaml`, `rules/world.yaml`). It was removed because it is now the default. Check that actors meant
     to hide under fog still carry `HiddenUnderFog` / `FrozenUnderFog` (fog and exposure matter in PW:
     `PwExposure`, `ExposureRadarWidget`).
   - **`ReplaceBaseAttackNotitifer`** in `rules/player.yaml:27` (`BaseAttackNotifier`). Check the result still
     plays PW's under-attack notification.
   - `--update-mod` only changes files on disk. **YAML that the asset installer writes** (converted maps,
     `TestMaps.cs` battle and test maps, any generated rules) must be fixed in that C# generator code, then re-run
     the installer.
6. **Scripts and packaging** (the upstream Mod SDK has not been updated for bleed):
   - `packaging/windows/buildpackage.sh` lines 90 and 99 pass `"net6"`. The engine's `install_assemblies` no longer
     takes a runtime argument. The new signature is
     `SRC DEST TARGETPLATFORM COPY_GENERIC_LAUNCHER COPY_CNC_DLL COPY_D2K_DLL`. Fix the mod-side
     `install_mod_assemblies` the same way.
   - `.github/workflows/release-windows.yml:23`: `dotnet-version: '10.0.x'`.
   - `packaging/windows/update-portable.ps1 -Pack`: build once and launch the portable game on this machine, to
     confirm the .NET 10 runtime is bundled.
   - `Makefile` comments and defaults mentioning `RUNTIME=net6` / Mono: update or remove.
7. **Style.** `./make.cmd check` with `-warnaserror`. Expect about 131 findings:
   - 69 `CA1305`: `StringBuilder.Append($"…")` → `Append(CultureInfo.InvariantCulture, $"…")`;
   - 56 `IDE0028`: `dotnet format style --diagnostics IDE0028` fixes them;
   - a handful of `RCS1077`, `RCS0056`, `IDE0044`, `IDE0032`, `IDE0004`.
8. **Compare with the baseline.**
   - Full suite plus bot battles. Every map that passed before must pass.
   - **AI:** upstream changed `BaseBuilderBotModule` and other bot modules, and PW has its own bot modules on top.
     Compare battle outcomes and lengths with the baseline and **report the differences**. The skirmish AI is a
     protected system: don't retune it unless the user asks.
   - **Pathing:** upstream bleed changed movement and pathfinding code. Re-run the pathing tests, and diff any PW code
     derived from upstream locomotor or pathfinder classes.
   - Launch the game once, windowed, and play a short skirmish. Check the interface bar, terrain rendering, exposure
     radar, lightning and the order generators above. List what you didn't see.
9. **Re-diff copied upstream code.** Any class in `OpenRA.Mods.Pw` copied or adapted from an upstream class (order
   generators, `PwTerrainRenderer`, widgets) won't get upstream's fixes. Compare each with its bleed version in
   `engine/` and note what changed. Also re-check the engine traps listed in `../OpenSY/Plan.md` §8.2 that PW
   relies on.
10. **Report** to the user: commits, test results against the baseline, AI and pathing differences, the
    mouse-button choice, what wasn't checked in the game. Update `plan.md` (decision dated 2026-11-20, engine pin).

## Not your job

The headless switches (`Game.Platform=Null`, `Launch.Uncapped`, the Lua `Test` API, the shared parallel runner) are
built in the engine (plan.md Phases 1, 3 and 4). When they land, you'll get a short follow-up: switch to the engine
tag, and make `testlib.lua` call `Test.Pass` / `Test.Fail`.
