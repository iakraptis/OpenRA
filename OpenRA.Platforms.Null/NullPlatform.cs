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

// Null platform for headless OpenRA (automated tests, RL training, CI): no window, GPU or audio.
// From OpenRA-RL (yxc20089/OpenRA@9b271c1, OpenRA.Platforms.Null/NullPlatform.cs), adapted.
// Usage: Game.Platform=Null, e.g. OpenRA.exe Game.Mod=ra Game.Platform=Null Launch.Map=<map>
// Add Launch.Uncapped=true to run the simulation as fast as the CPU allows.
using System;
using System.IO;
using OpenRA.Primitives;

namespace OpenRA.Platforms.Null
{
	public class NullPlatform : IPlatform
	{
		// Used when the settings give no size: fullscreen modes default to 0x0, meaning "the desktop's size",
		// which a real window gets from the OS. A zero-sized screen breaks interface layout (e.g. divisions by width).
		static readonly Size DefaultSize = new(1920, 1080);

		public IPlatformWindow CreateWindow(
			Size size, WindowMode windowMode, float scaleModifier,
			int vertexBatchSize, int indexBatchSize, int videoDisplay, GLProfile profile)
		{
			return new NullPlatformWindow(size.Width > 0 && size.Height > 0 ? size : DefaultSize);
		}

		public ISoundEngine CreateSound(string device)
		{
			return new NullSoundEngine();
		}

		public IFont CreateFont(byte[] data)
		{
			return new NullFont();
		}
	}

	sealed class NullPlatformWindow : IPlatformWindow
	{
		public NullPlatformWindow(Size size)
		{
			NativeWindowSize = size;
			Context = new NullGraphicsContext();
		}

		public IGraphicsContext Context { get; }
		public Size NativeWindowSize { get; }
		public Size EffectiveWindowSize => NativeWindowSize;
		public float NativeWindowScale => 1f;
		public float EffectiveWindowScale => 1f;
		public Size SurfaceSize => NativeWindowSize;
		public int DisplayCount => 1;
		public int CurrentDisplay => 0;
		public bool HasInputFocus => false;
		public bool IsSuspended => false; // Must be false so the game loop runs normally
		public GLProfile GLProfile => GLProfile.Modern;
		public GLProfile[] SupportedGLProfiles => [GLProfile.Modern];

		public event Action<float, float, float, float> OnWindowScaleChanged
		{
			add { }
			remove { }
		}

		public void PumpInput(IInputHandler inputHandler) { }
		public string GetClipboardText() => "";
		public bool SetClipboardText(string text) => false;
		public bool TryOpenUrl(string url) => false;
		public void GrabWindowMouseFocus() { }
		public void ReleaseWindowMouseFocus() { }
		public IHardwareCursor CreateHardwareCursor(string name, Size size, byte[] data, int2 hotspot, bool pixelDouble) => new NullHardwareCursor();
		public void SetHardwareCursor(IHardwareCursor cursor) { }
		public void SetWindowTitle(string title) { }
		public void SetRelativeMouseMode(bool mode) { }
		public void SetScaleModifier(float scale) { }
		public void Dispose() { }
	}

	sealed class NullGraphicsContext : IGraphicsContext
	{
		public string GLVersion => "Null";

		public IVertexBuffer<T> CreateEmptyVertexBuffer<T>(int size) where T : struct => new NullVertexBuffer<T>();
		public IVertexBuffer<T> CreateVertexBuffer<T>(T[] data, bool dynamic = true) where T : struct => new NullVertexBuffer<T>();
		public T[] CreateVertices<T>(int size) where T : struct => new T[size];
		public IIndexBuffer CreateIndexBuffer(uint[] indices) => new NullIndexBuffer();
		public ITexture CreateTexture() => new NullTexture();
		public IFrameBuffer CreateFrameBuffer(Size s) => new NullFrameBuffer();
		public IFrameBuffer CreateFrameBuffer(Size s, Color clearColor) => new NullFrameBuffer();
		public IShader CreateShader(IShaderBindings shaderBindings) => new NullShader();
		public void EnableScissor(int x, int y, int width, int height) { }
		public void DisableScissor() { }
		public void Present() { }
		public void DrawPrimitives(PrimitiveType pt, int firstVertex, int numVertices) { }
		public void DrawElements(int numIndices, int offset) { }
		public void Clear() { }
		public void EnableDepthBuffer() { }
		public void DisableDepthBuffer() { }
		public void ClearDepthBuffer() { }
		public void SetBlendMode(BlendMode mode) { }
		public void SetVSyncEnabled(bool enabled) { }
		public void Dispose() { }
	}

	sealed class NullTexture : ITexture
	{
		public void SetData(byte[] colors, int width, int height)
		{
			Size = new Size(width, height);
		}

		public void SetFloatData(float[] data, int width, int height)
		{
			Size = new Size(width, height);
		}

		public void SetSubData(byte[] colors, int xoffset, int yoffset, int width, int height) { }

		public void SetDataFromReadBuffer(Rectangle rect) { }

		// Callers (radar, sheets, cursors) read the data back and index into it, so return a correctly sized buffer.
		public byte[] GetData() => new byte[Size.Width * Size.Height * 4];
		public Size Size { get; private set; }
		public TextureScaleFilter ScaleFilter { get; set; }
		public void Dispose() { }
	}

	sealed class NullFrameBuffer : IFrameBuffer
	{
		public ITexture Texture { get; } = new NullTexture();
		public void Bind() { }
		public void Unbind() { }
		public void EnableScissor(Rectangle rect) { }
		public void DisableScissor() { }
		public void Dispose() { }
	}

	sealed class NullVertexBuffer<T> : IVertexBuffer<T> where T : struct
	{
		public void Bind() { }
		public void SetData(T[] vertices, int length) { }
		public void SetData(ref T[] vertices, int length) { }
		public void SetData(T[] vertices, int offset, int start, int length) { }
		public void Dispose() { }
	}

	sealed class NullIndexBuffer : IIndexBuffer
	{
		public void Bind() { }
		public void Dispose() { }
	}

	sealed class NullShader : IShader
	{
		public void SetBool(string name, bool value) { }
		public void SetVec(string name, float x) { }
		public void SetVec(string name, float x, float y) { }
		public void SetVec(string name, float x, float y, float z) { }
		public void SetVec(string name, ReadOnlyMemory<float> vec, int length) { }
		public void SetTexture(string param, ITexture texture) { }
		public void SetMatrix(string param, float[] mtx) { }
		public void PrepareRender() { }
		public void Bind() { }
	}

	sealed class NullHardwareCursor : IHardwareCursor
	{
		public void Dispose() { }
	}

	sealed class NullFont : IFont
	{
		public FontGlyph CreateGlyph(char c, int size, float deviceScale)
		{
			return new FontGlyph
			{
				Offset = int2.Zero,
				Size = new Size(1, 1),
				Advance = size * 0.5f,
				Data = new byte[4],
			};
		}

		public void Dispose() { }
	}

	sealed class NullSoundEngine : ISoundEngine
	{
		public bool Dummy => true;

		public SoundDevice[] AvailableDevices() => [new SoundDevice(null, "Null Sound")];

		public ISoundSource AddSoundSourceFromMemory(byte[] data, int channels, int sampleBits, int sampleRate) => new NullSoundSource();
		public ISound Play2D(ISoundSource soundSource, bool loop, bool relative, WPos pos, float volume, bool attenuateVolume) => new NullSoundInstance();
		public ISound Play2DStream(Stream stream, int channels, int sampleBits, int sampleRate, bool loop, bool relative, WPos pos, float volume) => null;

		public float Volume { get; set; }

		public void PauseSound(ISound sound, bool paused) { }
		public void SetAllSoundsPaused(bool paused) { }
		public void SetSoundVolume(float volume, ISound music, ISound video) { }
		public void StopSound(ISound sound) { }
		public void StopAllSounds() { }
		public void SetListenerPosition(WPos position) { }
		public void SetSoundLooping(bool looping, ISound sound) { }
		public void SetSoundPosition(ISound sound, WPos position) { }
		public void Dispose() { }
	}

	sealed class NullSoundSource : ISoundSource
	{
		public void Dispose() { }
	}

	sealed class NullSoundInstance : ISound
	{
		public float Volume { get; set; }
		public float SeekPosition => 0;
		public bool Complete => false;
		public void SetPosition(WPos position) { }
	}
}
