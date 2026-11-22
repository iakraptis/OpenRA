# OpenSYW: groups splitting at narrow passes (the "ramp" problem), and the `jmods` engine branch

From the OpenPW session, 2026-11-21. OpenPW found an engine pathing problem on its ramps and fixed it in the engine.
OpenSYW runs the same engine commit without the fix. This note explains the problem, why SYW may hit it on its
bridges even though its passes are wider, how to check, and how to switch to the fixed engine.

## The problem

Order a group through a narrow pass, and part of it goes on a long detour through another pass instead of filing
through behind the leaders.

On OpenPW's (2) One VS One, 12 Powermen were sent up a ramp two cells wide. 8 of them went 19 cells around to
another ramp, and the last arrived at tick 315. With the fix, every unit uses the ramp and all are across by tick 120.

## Cause

When a move starts, `Move` plans its first path with `BlockedByActor.All`, then `Stationary`, `Immovable` and
`None` (`OpenRA.Mods.Common/Activities/Move/Move.cs`, `PathSearchOrder`). With `All`, **every other unit, moving or
not, is treated as a wall.** When a group is ordered, the leading units are already in or at the pass, so the pass
looks closed to the units behind them. Each of those finds a path around through another pass, and takes it.

It only happens when **both** of these are true when the order is given:

1. the group's own units fill the whole width of the pass on the shortest route;
2. there is another way round (with no other route, the search falls back to `Stationary` and the unit goes through).

## Will SYW hit it?

Probably, at its bridges. Wider passes make it rarer, but they don't rule it out:

- **Bridges with alternatives.** `kmulti1.map` has four river bridges (`docs/formats/map.md`), which is exactly
  condition 2: a group crossing one bridge has three detours available.
- **One unit per cell.** SYW's `foot` locomotor doesn't set `SharesCell`, so each soldier fills a whole cell. Five
  soldiers abreast close a pass five cells wide.
- **Large groups.** A big group ordered from near the pass will have units inside it when the paths are planned,
  even on a wide bridge. A small group far from the pass won't.
- **Other chokes:** the narrow land bridge mentioned in `docs/formats/map.md`, gaps in walls, and gaps between
  buildings or trees.

What to look for in the game: select 15 to 20 infantry standing by a bridge on `kmulti1` and order them to a cell
straight across. If some peel off toward another bridge while the bridge in front of them is open, it's this
problem.

## The fix: branch `jmods` on our fork

- `iakraptis/OpenRA`, branch **`jmods`**, commit **`9f29d431d70552db93a61dddb0c163eec93b7caa`**.
- It is upstream bleed `4cc9a9f`, **the same commit OpenSYW already runs**, plus one commit. Switching changes
  nothing else.
- The change: `PathSearchOrder` starts at `Immovable`, then `None`. The first path ignores other units; buildings
  and other immovable actors still block it. A unit that meets a blocker on the way still waits and re-paths around
  it, as before (`PopPath`).
- OpenPW's results with it on bleed: `pathing-test` passes, with all 12 across by tick 120 and none more than 7 cells
  from the ramp. Without it on bleed: tick 305 and 19 cells. The same change was in OpenPW's old engine
  (`syw-20250330.2`), where OpenPW's whole suite passed with it.

To switch, in `mod.config`:

```
ENGINE_VERSION="9f29d431d70552db93a61dddb0c163eec93b7caa"
AUTOMATIC_ENGINE_SOURCE="https://github.com/iakraptis/OpenRA/archive/${ENGINE_VERSION}.zip"
```

Then `./make.cmd all`, which replaces `engine/`.

**Possible side effect to watch for:** units now plan straight through their own crowd, and then wait or re-path
when they meet it. In a crowded base, or when a group is ordered through a gap held by its own idle units, you may
see more short waits and fewer wide sweeps around. OpenPW hasn't seen a problem, but it hasn't tested
SYW-like crowds.

## Suggested steps

Follow the repo's own rules: commit on a working branch, no push, the user merges, style check and YAML lint before
each commit, and a report that says what wasn't checked in the game.

1. **Reproduce first, on the current engine.** Add a test map like OpenPW's `pathing-test`: a group ordered across
   one bridge on `kmulti1` (or a SYW map with two bridges close together). Check two numbers: when the last unit
   arrives, and the farthest any unit strays from the bridge. OpenPW's version is
   `OpenRA.Mods.Pw/AssetInstaller/MapTemplates/pathing-test/test.lua`, written onto a converted map by
   `TestMaps.ExportPathing` in `OpenRA.Mods.Pw/AssetInstaller/TestMaps.cs`. If nobody detours, SYW doesn't hit the
   problem at that bridge; try a bigger group before concluding.
2. If it reproduces, **switch `mod.config` to `jmods`** as above and run the test again. It should pass.
3. Run the suite, and play a short skirmish to watch movement at bridges and in the base.
4. Report: the before and after numbers, and whether you switched.

## Later

The engine session will publish a tag on `iakraptis/OpenRA` (bleed plus the headless and RL additions). This fix
needs to be in that tag. When the tag comes, both mods move to it and leave `jmods`.
