# OpenSYW: update to the new engine (OpenRA bleed, .NET 10)

From the engine session (`../OpenRA`, branch `headless-rl`), 2026-11-20. The full plan is `../OpenRA/plan.md`. Read
`../OpenRA/docs/mod-updates/api-changes.md` first: it explains every engine change listed below.

## Why

The engine is moving from `release-20250330` to a pinned commit of upstream OpenRA `bleed`. Upstream has made no
release since then. The move brings a headless mode (no window, much faster test runs, parallel tests) and a gRPC
bridge for scripted/LLM/RL agents, both from the GPL-3 project OpenRA-RL, which is built on bleed. OpenWBC goes first
as the pilot; OpenSYW and OpenPW can start in parallel.

## What you need to know

- **Engine target:** upstream bleed `4cc9a9f6299c807c373bb233d9729518c0160c77` (2026-11-17).
  - OpenSYW currently uses our fork's tag `syw-20250330.1`. Its one patch (sub-pixel remainder in `Viewport.Scroll`)
    is superseded on bleed, where `Viewport.CenterLocation` is a float `Vector2`. So pointing at upstream directly
    loses nothing, but **check scrolling in the game** (slow, diagonal, zoomed in), since that was the patch's
    reason.
  - Later the engine session will publish a new tag on `iakraptis/OpenRA` (this commit plus headless and RL
    additions); you will then change only `ENGINE_VERSION` and `AUTOMATIC_ENGINE_SOURCE` back to the fork.
- **.NET 10** is required (`net10.0`, C# 13). SDK 10.0.404 is installed on this machine. Mono is no longer supported.
- **Compile survey.** A copy of `OpenRA.Mods.Syw` (`main`, 2026-11-18) was compiled against that commit, fixed, and
  rebuilt until it compiled:
  - **19 errors** in total (6 in the first wave, 13 hidden behind them);
  - then **31 style findings** under `-warnaserror` with this repo's `.editorconfig` (26 `IDE0028`, 4 `SA1128`,
    1 `SA1515`).
  The fixes below are known to compile; they haven't been run in the game.

## Steps

Follow the repo's own rules: commits on the working branch, no push, the user merges, style check and YAML lint
before each commit, plain-language report with commit hash and what wasn't checked in the game.

1. **Branch.** `main` is clean. Create `engine-bleed` from an up-to-date `main`.
2. **Baseline on the old engine.** Before changing anything: `python run_tests.py` (full suite, including `bot-test`
   from the content maps). Keep the results as `test-results/baseline-release-20250330/` (summary plus per-map
   logs). Record the total time and each map's time; you'll compare against this in step 8.
3. **Pin the engine.** In `mod.config`:
   ```
   ENGINE_VERSION="4cc9a9f6299c807c373bb233d9729518c0160c77"
   AUTOMATIC_ENGINE_SOURCE="https://github.com/OpenRA/OpenRA/archive/${ENGINE_VERSION}.zip"
   ```
   Then `./make.cmd all`. It replaces `engine/` (gitignored) automatically.
4. **Compile fixes** (paths under `OpenRA.Mods.Syw/`; see `api-changes.md` for each change):
   - **Order generators** (the main item; it changes how players cast):
     - `Orders/GroundSpellOrderGenerator.cs`, `Orders/SpellOrderGenerator.cs`, `Orders/TransformOrderGenerator.cs`,
       `Orders/UnloadAtOrderGenerator.cs` derive from `OrderGenerator`:
       - Add `ActionType`.
       - Pass the world to the new base constructor: `: base(caster.World)` on `GroundSpellOrderGenerator(Actor)`
         (line 15), `SpellOrderGenerator(Actor, Armament)` (18), and `TransformOrderGenerator(Actor,
         IUnitTargetSpell)` (19).
       - `UnloadAtOrderGenerator` has no constructor: add `(World world) : base(world)` and pass `world` at
         `Widgets/Logic/UnloadButtonLogic.cs:28`.
     - **Remove the right-button cancel checks inside `OrderInner`**: `GroundSpellOrderGenerator.cs:27`,
       `SpellOrderGenerator.cs:40`, `TransformOrderGenerator.cs:34`, `UnloadAtOrderGenerator.cs:21`. The base class
       now cancels on the cancel button itself. If `ActionType` resolves to the right button, these checks would
       cancel the confirming click.
     - `Orders/BuildAtCellOrderGenerator.cs` and `Orders/MineLineOrderGenerator.cs` implement `IOrderGenerator`
       directly. Add `ActionButton` and use the resolved action and cancel buttons instead of the hard-coded checks
       (`BuildAtCellOrderGenerator.cs:44/50`, `MineLineOrderGenerator.cs:48/54`).
     - Suggested `ActionType`s:
       - spells, ground spells and the shaman transform: `SupportPower` (left under every style);
       - build-at-cell and mine line: `PlaceBuilding` (left);
       - unload-at: `ConfirmOrder` (**right** under the default `Modern` style, left under `Classic`) or
         `SupportPower` to keep it on the left.
       **This decides which button players use**, so tell the user what you chose. The Lua tests issue orders
       directly and won't catch a wrong choice; check each one in the game.
   - **`float3` → `Vector3`** (`using System.Numerics;`): `Widgets/AnimatedImageWidget.cs:54-55`,
     `Widgets/StretchedImageWidget.cs:32-33`.
   - **Prerequisites** are a struct now: `Traits/BotModules/PeasantBaseBuilderBotModule.cs:242` →
     `…TraitInfoOrDefault<BuildableInfo>()?.Prerequisites ?? [];`.
   - **Resource amount is a `byte`**: `Traits/RegrowsResources.cs:69-70`. `amount` comes from
     `Math.Min(info.Amount, density - content.Density)`. Cast it, and make sure `RegrowsResources.Amount` can't
     exceed 255 (validate in the trait info or clamp).
   - **`Game.InitializeMod` takes a `Manifest`**: `Widgets/Logic/SywContentLogic.cs:72` and `:151` →
     `Game.InitializeMod(Game.Mods[GameMod], …)`.
5. **YAML.** `./utility.cmd syw --update-mod release-20250330 --apply` (add `--detailed` first, without `--apply`, to
   review). Expected hit: **`RemoveAlwaysVisible`** in `rules/mpspawn.yaml`, `rules/player.yaml`, `rules/world.yaml`.
   It was removed because it is now the default. Check that actors meant to hide under fog still carry
   `HiddenUnderFog` / `FrozenUnderFog`.
   - `--update-mod` only changes files on disk. **YAML that the asset installer writes** (converted maps, the
     generated `bot-test` map in the content folder, any generated rules) must be fixed in the installer's C#, then
     re-run the installer.
6. **Scripts and packaging** (the upstream Mod SDK has not been updated for bleed):
   - `packaging/windows/buildpackage.sh:90` and `:99` pass `"net6"`. Drop it from `install_assemblies` (new
     signature in `api-changes.md`) and fix `install_mod_assemblies` the same way.
   - `.github/workflows/release-windows.yml:23`: `dotnet-version: '10.0.x'`.
   - `packaging/windows/update-portable.ps1` and `package-windows.ps1`: build once and launch the result on this
     machine, to confirm the .NET 10 runtime is bundled.
   - `Makefile` comments and defaults mentioning `RUNTIME=net6` / Mono: update or remove.
7. **Style.** `./make.cmd check` with `-warnaserror`. Expect about 31 findings, mostly `IDE0028`
   (`dotnet format style --diagnostics IDE0028` fixes them) and a few `SA1128` / `SA1515`.
8. **Compare with the baseline.**
   - Full suite. Every map that passed before must pass.
   - **AI:** upstream changed `BaseBuilderBotModule` and other bot modules, and SYW has `PeasantBaseBuilderBotModule`
     on top. Compare `bot-test` outcomes and lengths with the baseline and **report the differences**. Don't retune
     the AI unless the user asks.
   - Launch the game once, windowed, and play a short skirmish. Check: every spell and order generator above (cast,
     cancel, and both mouse styles if you can), mine lines, building at a cell, unloading, scrolling, the
     day/night cycle, rain, the animated and stretched image widgets, and the content installer screen. List what
     you didn't see.
9. **Re-diff copied upstream code.** Any class in `OpenRA.Mods.Syw` copied or adapted from an upstream class (order
   generators, `PeasantBaseBuilderBotModule`, `ConstructBuilding`, widgets) won't get upstream's fixes. Compare each
   with its bleed version in `engine/` and note what changed. Re-check the engine traps listed in
   `../OpenSY/Plan.md` §8.2.
10. **Report** to the user: commits, test results against the baseline, AI differences, the mouse-button choices,
    what wasn't checked in the game. Update the mod's plan or docs with a dated note on the engine pin.

## Not your job

The headless switches (`Game.Platform=Null`, `Launch.Uncapped`, the Lua `Test` API, the shared parallel runner) are
built in the engine (plan.md Phases 1, 3 and 4). When they land, you'll get a short follow-up: switch to the engine
tag, and make `testlib.lua` call `Test.Pass` / `Test.Fail`.
