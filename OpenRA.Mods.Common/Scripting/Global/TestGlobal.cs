#region Copyright & License Information
/*
 * Copyright (c) The OpenRA Developers and Contributors
 * This file is part of OpenRA, which is free software. It is made
 * available to you under the terms of the GNU General Public License
 * as published by the Free Software Foundation, either version 3 of
 * the License, or (at your option) any later version. For more
 * information, see COPYING.
 */
#endregion

using OpenRA.Scripting;

namespace OpenRA.Mods.Common.Scripting
{
	[ScriptGlobal("Test")]
	public class TestGlobal : ScriptGlobal
	{
		public TestGlobal(ScriptContext context)
			: base(context) { }

		[Desc("True when the game runs without a window (Game.Platform=Null), e.g. in an automated test run.")]
		public bool Headless => Game.IsHeadless;

		[Desc("Report that the test passed. Prints the given line, if any, to stdout. Without a window the game then " +
			"exits with code 0; with a window it keeps running. Only the first Pass or Fail counts.")]
		public void Pass(string line = null)
		{
			Game.EndTest(RunStatus.Success, line);
		}

		[Desc("Report that the test failed. Prints the given line, if any, to stdout. Without a window the game then " +
			"exits with code 1; with a window it keeps running. Only the first Pass or Fail counts.")]
		public void Fail(string line = null)
		{
			Game.EndTest(RunStatus.TestFailed, line);
		}
	}
}
