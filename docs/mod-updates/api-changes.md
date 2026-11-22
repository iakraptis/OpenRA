# Engine API changes from release-20250330 to bleed 4cc9a9f (what our mods hit)

From the engine session, 2026-11-20. Found by compiling copies of OpenSYW, OpenPW and OpenWBC against upstream bleed
`4cc9a9f6299c807c373bb233d9729518c0160c77`, fixing, and rebuilding until all three compiled. Each mod's handoff
lists where its own code is affected; this file explains each change once.

The compiler reports errors in two waves. Declaration errors (missing interface members, unknown types in
signatures) come first and **hide** errors inside method bodies. Expect a second batch after the first fixes.

## Vectors: `float2` / `float3` removed

| Old | New |
|---|---|
| `float2` | `System.Numerics.Vector2` |
| `float3` | `System.Numerics.Vector3` |
| `float3.Ones` | `Vector3.One` |
| `v.XY` (on a `float3`) | `new Vector2(v.X, v.Y)` |
| `int2` ↔ vector | `int2.ToVector2()`, `int2.FromVector(Vector2)` (truncates) |
| `Size` → vector | `size.ToVector2()` |

Engine members that now take or return vectors:
- `WorldRenderer.ScreenPosition(WPos)` returns `Vector2`.
- `Viewport.WorldToViewPx` takes `int2` or `in Vector3`.
- `Viewport.CenterLocation` is a `Vector2`.
- `UISpriteRenderable(sprite, WPos, Vector2 screenPos, …)` takes a `Vector2` screen position.

Add `using System.Numerics;` rather than writing the full name everywhere.

## `[Sync]` → `[VerifySync]`

Renamed, same meaning: the field or property is included in the sync hash.

## Order generators and mouse buttons

Order buttons now come from the player's **`MouseControlStyle`** setting (`Classic`, `Modern`, `OtherRTS`;
default **`Modern`**), through `Game.Settings.Game.ResolveActionButton(MouseActionType)` and
`ResolveCancelButton(...)`. The cancel button is always the other one.

| `MouseActionType` | Button under `Modern` | Under `Classic` |
|---|---|---|
| `ConfirmOrder` | **right** | left |
| `Contextual` | right | left |
| `SupportPower`, `PlaceBuilding`, `GlobalCommand` | left | left |

`GameSettings.MouseButtonPreference` was removed.

**Classes deriving from `OrderGenerator`** (`OpenRA.Mods.Common/Orders/OrderGenerator.cs`):
- The constructor is now `protected OrderGenerator(World world)`. Call `: base(world)` (e.g. `base(caster.World)`).
  Under `Classic` it also clears the selection.
- Override `protected override MouseActionType ActionType => …;`. Upstream examples: `GuardOrderGenerator`
  (`ConfirmOrder`), `BeaconOrderGenerator` (`PlaceBuilding`), `GlobalButtonOrderGenerator` (`GlobalCommand`).
- **Behaviour change.** The base `Order()` calls `OrderInner` **only** for the action button's *Down* event, and
  cancels the mode itself on the cancel button's *Up* event. Before, `OrderInner` got left-Down **and** right-Up,
  and our generators cancelled on `mi.Button == MouseButton.Right` inside `OrderInner`.
  **Remove those right-button checks.** If `ActionType` resolves to the right button, they would cancel on the
  confirming click.

**Classes implementing `IOrderGenerator` directly** need `MouseButton ActionButton { get; }`. Return the resolved
button, and use it (and the resolved cancel button) instead of hard-coded `MouseButton.Left` / `MouseButton.Right`.

**A mod's `DefaultOrderGenerator`** (`mod.yaml`) is created with a `(World)` constructor:
`GetConstructor([typeof(World)])?.Invoke([this])`. **Without one, it silently becomes `null` and the player has no
input.** `UnitOrderGenerator` subclasses need `public X(World world) : base(world) { }`.

`AttackMoveOrderGenerator(World world, IEnumerable<Actor> subjects)`: the button argument is gone.

## Other signatures

| Change | Fix |
|---|---|
| `INotifyBuildingPlaced.BuildingPlaced(Actor self, Actor building)` | Use `building`; no need to search for the placed actor. |
| `ITiledTerrainRenderer.RenderPreview(WorldRenderer, TerrainTile, WPos)` (new, single tile, map editor) | Implement; upstream's is at the end of `OpenRA.Mods.Common/Traits/World/TerrainRenderer.cs`. |
| `IResourceLayer.CanAddResource` / `AddResource(string, CPos, byte amount = 1)` | Amount is a `byte`; cast, and make sure it can't exceed 255. |
| `BuildableInfo.Prerequisites` is `ImmutableArray<string>` (a struct) | `info.TraitInfoOrDefault<BuildableInfo>()?.Prerequisites ?? []` |
| `MapGrid.TileSize` removed | `map.Rules.TerrainInfo.TileSize` (or `WorldRenderer.TileSize`) |
| `Game.InitializeMod(Manifest manifest, Arguments args)` | `Game.InitializeMod(Game.Mods[modId], args)` |

## Chrome: observer labels are `LabelWithTooltip` (found 2026-11-21; no update rule)

Upstream `7e8f4a3479` ("Truncate less of the player name, add a tooltip") changed the observer UI's logic to expect
`LabelWithTooltipWidget`:
- `ObserverShroudSelectorLogic`: `LABEL` in the `SHROUD_SELECTOR` dropdown and in its dropdown item template;
- `ObserverStatsLogic` / `GameInfoStatsLogic`: `PLAYER` in the stats rows.

All three mods carry their own `chrome/ingame-observer.yaml` with `Label@LABEL`. **Watching a replay or spectating
crashes** (`InvalidCastException: Unable to cast LabelWidget to LabelWithTooltipWidget`, in
`ObserverShroudSelectorLogic`). No test map covers this; it was found by replaying a game headless.

Fix: in the mod's chrome, change those widgets to `LabelWithTooltip@LABEL` / `LabelWithTooltip@PLAYER`, and copy the
rest of the upstream change (`TooltipContainer: TOOLTIP_CONTAINER`, `TooltipTemplate: SIMPLE_TOOLTIP`, the narrower
`Width`, `EnableChildMouseOver: true` on the rows). See the commit's changes to `mods/ra/chrome/ingame-observer.yaml`,
`mods/common/chrome/dropdowns.yaml` and `mods/common/chrome/ingame-infostats.yaml`. Then open a replay windowed and
check the observer panels.

OpenPW: fixed in `6facf97` (only the shroud selector's `LABEL`; it takes `dropdowns.yaml` and `ingame-infostats.yaml`
from common). Replays checked in the game by the user.

## Chrome: new common files a mod's `ChromeLayout` must list (found 2026-11-21; no update rule)

A mod that lists common chrome files itself gets bleed's versions of those files, but not the files bleed added.
Bleed's `common|chrome/settings.yaml` lists a Gameplay tab whose panel is in a new file, so **opening Settings from
the main menu crashes**: `InvalidDataException: Cannot find widget with Id GAMEPLAY_PANEL` (in `SettingsLogic`).
`--check-yaml` doesn't catch it.

Add to `ChromeLayout` (in `mod.yaml`, or the file it includes), when the mod uses the matching common file:

| New file | Defines | Needed by |
|---|---|---|
| `common|chrome/settings-gameplay.yaml` | `GAMEPLAY_PANEL` | `common|chrome/settings.yaml` (the Settings window) |
| `common|chrome/load-game-browser.yaml` | `LOAD_GAME_BROWSER_PANEL` | the main menu's and in-game menu's Load button (`MainMenuLogic`, `IngameMenuLogic`) |
| `common|chrome/ingame-debug-hpf.yaml` | `HPF_OVERLAY` | the debug menu's pathfinder overlay |

A mod with its own copy of `settings.yaml` (or its own main menu) only needs what its copy names.

To check a mod: `python audit-chrome.py <mod repository> <mod id>` (next to this file). It lists widgets that the
logic of each loaded chrome file requires and panels named in the chrome that no loaded file defines. It reports
`GAMEPLAY_PANEL` on OpenPW before the fix. `MainMenuLogic: needs ENCYCLOPEDIA_PANEL` can be ignored when the menu has
no `ENCYCLOPEDIA_BUTTON` (the logic looks the button up with `GetOrNull`). On 2026-11-21 it reports nothing else for
OpenPW (after the fix), OpenSYW or OpenWBC. It finds missing panels only; still click through the main menu once
(Settings and each tab, Load, Replays, Music, Map Editor, Asset Browser).

OpenPW: fixed in `3281272`.

## YAML (`./utility.cmd <mod> --update-mod release-20250330 --apply`)

Rules after `release-20250330`:
- `RemoveAlwaysVisible`: the trait is gone; always visible is now the default.
- `ReplaceBaseAttackNotitifer`
- `RemoveBuildingInfoAllowPlacementOnResources`
- `RemoveAndRenameDefenseRadiusInBaseBuilderBotModule`
- `RemoveBarracksTypesAndVehiclesTypesInBaseBuilderBotModule`
- `WithDamageOverlayPropertyRename`
- `EditorMarkerTileLabels`
- `RenameMapGeneratorParameters`

It changes files on disk only. YAML that an asset installer or map converter **generates** must be fixed in that
generator's C# code.

## Style (`make check`, `-warnaserror`)

After the compile fixes, each repo's own `.editorconfig` reports mostly mechanical findings:
- `IDE0028` (use collection expressions): `dotnet format style --diagnostics IDE0028` fixes them;
- `CA1305` (culture): `StringBuilder.Append($"…")` → `Append(CultureInfo.InvariantCulture, $"…")`;
- a few `SA1128` (constructor initializer on its own line), `SA1515`, `IDE0004`, `IDE0032`, `IDE0044`, `RCS1077`,
  `RCS0056`.

## Build, scripts, packaging

- .NET 10 (`net10.0`, C# 13); Mono removed. SDK 10.0.404 is installed on this machine.
- The engine solution is `OpenRA.slnx`. The mods' own `.sln` files keep working (they reference the engine's
  `.csproj` files).
- `packaging/functions.sh` `install_assemblies` lost its runtime argument:
  `install_assemblies SRC DEST TARGETPLATFORM COPY_GENERIC_LAUNCHER COPY_CNC_DLL COPY_D2K_DLL`.
- CI: `dotnet-version: '10.0.x'`.
- The upstream Mod SDK has not been updated for bleed, so there is no newer SDK to copy scripts from.
