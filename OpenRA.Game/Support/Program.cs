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

namespace OpenRA
{
	/// <summary>The process exit code. Values 1-5 are only produced by automated (headless) test runs.</summary>
	public enum RunStatus
	{
		/// <summary>Unhandled exception (crash).</summary>
		Error = -1,

		/// <summary>Normal exit, or Test.Pass().</summary>
		Success = 0,

		/// <summary>Test.Fail(reason).</summary>
		TestFailed = 1,

		/// <summary>The world reached Launch.MaxTicks before the test reported a result.</summary>
		TestTickLimit = 2,

		/// <summary>A fatal Lua error in the map script.</summary>
		LuaError = 4,

		/// <summary>The simulation went out of sync (e.g. a replay re-simulated differently).</summary>
		OutOfSync = 5,

		Running = int.MaxValue
	}
}
