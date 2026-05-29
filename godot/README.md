# Godot Audio Sidecar

Optional **Godot 4** sidecar for four-layer stem mixing. The default app config uses the Python placeholder mixer instead; enable this only when you set `audio.backend: godot` in `config/default.yaml`.

## Requirements

- [Godot 4.x](https://godotengine.org/download) (4.2+ recommended)
- Set `audio.godot_executable` in `config/default.yaml`, or set `GODOT4` / add `godot` to `PATH`

## Architecture

```
PyQt6 host (Python)                    Godot sidecar
─────────────────────                    ─────────────
AdaptiveSoundscapeApp                    soundscape_manager.gd
  └─ GodotAudioBackend  ──TCP:8765──►      ├─ AudioStreamPlayer layers / profile
       JSON lines                             ├─ crossfade (volume + params)
       start / stop / crossfade               └─ loads stems from assets/
```

Launch uses `--audio-driver WASAPI` on Windows so audio is not routed through Godot's silent Dummy driver.

### JSON commands (one JSON object per line)

| `op` | Fields | Effect |
|------|--------|--------|
| `configure` | `assets_path`, `master_volume` | Set asset root directory |
| `start` / `stop` | — | Begin/stop playback; responses include `layer_count` |
| `set_profile` | `profile_id` | Immediate profile switch |
| `set_parameters` | `brightness`, `energy`, `warmth` | Adjust mix shaping |
| `crossfade` | `profile_id`, `duration`, params | Crossfade to profile |
| `status` / `ping` | — | Query playback state and loaded layers |
| `quit` | — | Exit Godot |

## Layer assets

**Preferred layout** (four synchronized stems per context):

```
assets/audio/
  programming/
    ambient.wav   # or .mp3 / .ogg
    rhythm.wav
    harmonic.wav
    accent.wav
  reading_writing/
    ...
```

**Fallback** (flat files when layered folders are missing):

```
assets/audio/
  programming.mp3
  programming_pad.wav
```

Supported formats: `.mp3`, `.wav`, `.ogg` (Godot). MP3 in the Python placeholder mixer requires `miniaudio`.

## Run manually

```powershell
godot --audio-driver WASAPI --path godot -- --port 8765 --assets "D:/stuff/Adaptive Focus Music System/assets/audio"
```

Arguments after `--` are read via `OS.get_cmdline_user_args()`.

## Python config

```yaml
audio:
  backend: godot              # default in repo is placeholder
  godot_project: godot
  godot_port: 8765
  godot_executable: "D:/path/to/Godot_v4.x-stable_win64.exe"
  fallback_to_placeholder: true
```

If Godot is not installed or fails to load layers, keep `fallback_to_placeholder: true` to use the built-in mixer.
