extends Node
## Adaptive Soundscape — Godot audio sidecar.
## Receives newline-delimited JSON commands on TCP port 8765 from the Python host.

const DEFAULT_PORT := 8765
const LAYER_NAMES := ["ambient", "rhythm", "harmonic", "accent"]
const AUDIO_EXTENSIONS := ["mp3", "wav", "ogg"]

var _port: int = DEFAULT_PORT
var _assets_path: String = ""
var _tcp_server: TCPServer
var _client: StreamPeerTCP
var _read_buffer: String = ""
var _playing: bool = false
var _master_volume: float = 0.35

var _current_profile: String = "unknown"
var _target_profile: String = "unknown"
var _crossfade_duration: float = 0.0
var _crossfade_elapsed: float = 0.0
var _crossfade_active: bool = false

var _params := {"brightness": 0.5, "energy": 0.4, "warmth": 0.55}
var _target_params := {"brightness": 0.5, "energy": 0.4, "warmth": 0.55}

var _current_layers: Array[AudioStreamPlayer] = []
var _target_layers: Array[AudioStreamPlayer] = []
var _layer_root: Node


func _ready() -> void:
	_layer_root = Node.new()
	_layer_root.name = "LayerRoot"
	add_child(_layer_root)
	var port_arg := _read_cli_int("--port", DEFAULT_PORT)
	_port = port_arg
	var assets_arg := _read_cli_string("--assets", "")
	if assets_arg != "":
		_assets_path = assets_arg.replace("\\", "/")
	_tcp_server = TCPServer.new()
	var err := _tcp_server.listen(_port, "127.0.0.1")
	if err != OK:
		push_error("Failed to listen on port %d: %s" % [_port, err])
		return
	AudioServer.set_bus_volume_db(AudioServer.get_bus_index("Master"), 0.0)
	print(
		"SoundscapeManager listening on 127.0.0.1:%d assets=%s"
		% [_port, _assets_path if _assets_path != "" else "<unset>"]
	)


func _cli_args() -> PackedStringArray:
	var user_args := OS.get_cmdline_user_args()
	if not user_args.is_empty():
		return user_args
	return OS.get_cmdline_args()


func _read_cli_int(flag: String, default_value: int) -> int:
	var args := _cli_args()
	for i in range(args.size()):
		if args[i] == flag and i + 1 < args.size():
			return int(args[i + 1])
	return default_value


func _read_cli_string(flag: String, default_value: String) -> String:
	var args := _cli_args()
	for i in range(args.size()):
		if args[i] == flag and i + 1 < args.size():
			return args[i + 1]
	return default_value


func _process(delta: float) -> void:
	_accept_client()
	_poll_client()
	_update_crossfade(delta)


func _accept_client() -> void:
	if _client != null and _client.get_status() == StreamPeerTCP.STATUS_CONNECTED:
		return
	if _tcp_server.is_connection_available():
		_client = _tcp_server.take_connection()
		_read_buffer = ""
		_send_json({"ok": true, "event": "connected"})


func _poll_client() -> void:
	if _client == null:
		return
	var status := _client.get_status()
	if status == StreamPeerTCP.STATUS_NONE or status == StreamPeerTCP.STATUS_ERROR:
		_client = null
		return
	_client.poll()
	var available := _client.get_available_bytes()
	if available <= 0:
		return
	var result := _client.get_partial_data(available)
	if result[0] != OK:
		return
	var chunk: String = result[1].get_string_from_utf8()
	_read_buffer += chunk
	while _read_buffer.contains("\n"):
		var idx := _read_buffer.find("\n")
		var line := _read_buffer.substr(0, idx).strip_edges()
		_read_buffer = _read_buffer.substr(idx + 1)
		if line.is_empty():
			continue
		_handle_command(line)


func _handle_command(line: String) -> void:
	var json := JSON.new()
	if json.parse(line) != OK:
		_send_json({"ok": false, "error": "invalid_json"})
		return
	var data: Variant = json.get_data()
	if typeof(data) != TYPE_DICTIONARY:
		_send_json({"ok": false, "error": "expected_object"})
		return
	var op: String = str(data.get("op", ""))
	match op:
		"ping":
			_send_json(_status_payload())
		"status":
			_send_json(_status_payload())
		"configure":
			_assets_path = str(data.get("assets_path", _assets_path)).replace("\\", "/")
			_master_volume = float(data.get("master_volume", _master_volume))
			_send_json({"ok": true, "assets_path": _assets_path})
		"start":
			_start_playback()
			var start_payload := _status_payload()
			start_payload["event"] = "started"
			_send_json(start_payload)
		"stop":
			_stop_playback()
			_send_json({"ok": true, "playing": _playing, "layer_count": 0})
		"set_profile":
			var profile_id := str(data.get("profile_id", _current_profile))
			_set_profile_immediate(profile_id)
			_apply_layer_params(_current_layers, _params)
			var profile_payload := _status_payload()
			profile_payload["event"] = "profile_set"
			_send_json(profile_payload)
		"set_parameters":
			_params = _parse_params(data)
			_apply_layer_params(_current_layers, _params)
			_send_json({"ok": true})
		"crossfade":
			var profile_id := str(data.get("profile_id", _current_profile))
			var duration := float(data.get("duration", 8.0))
			_target_params = _parse_params(data)
			_begin_crossfade(profile_id, duration)
			_send_json({"ok": true, "profile_id": profile_id, "duration": duration})
		"quit":
			_send_json({"ok": true})
			get_tree().quit()
		_:
			_send_json({"ok": false, "error": "unknown_op"})


func _parse_params(data: Dictionary) -> Dictionary:
	return {
		"brightness": float(data.get("brightness", _params.get("brightness", 0.5))),
		"energy": float(data.get("energy", _params.get("energy", 0.4))),
		"warmth": float(data.get("warmth", _params.get("warmth", 0.55))),
	}


func _start_playback() -> void:
	if _playing:
		return
	if _current_layers.is_empty():
		_set_profile_immediate(_current_profile)
	if _current_layers.is_empty():
		push_error(
			"No audio layers loaded for profile '%s' (assets=%s)"
			% [_current_profile, _assets_path]
		)
		_playing = false
		return
	for player in _current_layers:
		if not player.playing:
			player.play()
	_playing = true


func _stop_playback() -> void:
	for player in _current_layers + _target_layers:
		player.stop()
	_playing = false
	_crossfade_active = false


func _set_profile_immediate(profile_id: String) -> void:
	_clear_layers(_current_layers)
	_current_layers = _build_layers(profile_id)
	_current_profile = profile_id
	_target_profile = profile_id


func _begin_crossfade(profile_id: String, duration: float) -> void:
	_target_profile = profile_id
	_crossfade_duration = max(duration, 0.01)
	_crossfade_elapsed = 0.0
	_crossfade_active = profile_id != _current_profile
	if not _crossfade_active:
		_params = _target_params.duplicate()
		_apply_layer_params(_current_layers, _params)
		return
	_clear_layers(_target_layers)
	_target_layers = _build_layers(profile_id)
	for player in _target_layers:
		player.volume_db = -80.0
		if _playing and not player.playing:
			player.play()


func _update_crossfade(delta: float) -> void:
	if not _crossfade_active:
		return
	_crossfade_elapsed += delta
	var t := clampf(_crossfade_elapsed / _crossfade_duration, 0.0, 1.0)
	_apply_layer_params(_current_layers, _params, 1.0 - t)
	_apply_layer_params(_target_layers, _target_params, t)
	_set_layer_volumes(_current_layers, linear_to_db(1.0 - t) if t < 1.0 else -80.0)
	_set_layer_volumes(_target_layers, linear_to_db(t) if t > 0.0 else -80.0)
	if t >= 1.0:
		_clear_layers(_current_layers)
		_current_layers = _target_layers
		_target_layers = []
		_current_profile = _target_profile
		_params = _target_params.duplicate()
		_crossfade_active = false


func _build_layers(profile_id: String) -> Array[AudioStreamPlayer]:
	var players: Array[AudioStreamPlayer] = []
	var base_gains := {
		"ambient": 0.55,
		"rhythm": 0.35,
		"harmonic": 0.40,
		"accent": 0.20,
	}
	for layer_name in LAYER_NAMES:
		var stream := _load_layer_stream(profile_id, layer_name)
		if stream == null:
			continue
		var player := AudioStreamPlayer.new()
		player.name = "%s_%s" % [profile_id, layer_name]
		player.stream = stream
		player.volume_db = linear_to_db(base_gains.get(layer_name, 0.4) * _master_volume)
		player.autoplay = false
		player.bus = "Master"
		_configure_player_loop(player, stream)
		_layer_root.add_child(player)
		players.append(player)
	if players.is_empty():
		players = _build_fallback_layers(profile_id)
	return players


func _build_fallback_layers(profile_id: String) -> Array[AudioStreamPlayer]:
	var players: Array[AudioStreamPlayer] = []
	var stems := [
		["%s/%s" % [_assets_path, profile_id], 0.6],
		["%s/%s_pad" % [_assets_path, profile_id], 0.35],
	]
	for entry in stems:
		var stem: String = entry[0]
		var gain: float = entry[1]
		var path := _resolve_audio_path(stem)
		if path == "":
			continue
		var stream := _load_audio(path)
		if stream == null:
			continue
		var player := AudioStreamPlayer.new()
		player.name = "%s_%s" % [profile_id, path.get_file()]
		player.stream = stream
		player.volume_db = linear_to_db(gain * _master_volume)
		player.autoplay = false
		player.bus = "Master"
		player.set_meta("source_path", path)
		_configure_player_loop(player, stream)
		_layer_root.add_child(player)
		players.append(player)
	return players


func _load_layer_stream(profile_id: String, layer_name: String) -> AudioStream:
	var layered_stem := "%s/%s/%s" % [_assets_path, profile_id, layer_name]
	var layered_path := _resolve_audio_path(layered_stem)
	if layered_path != "":
		return _load_audio(layered_path)
	for ext in AUDIO_EXTENSIONS:
		var res_path := "res://audio/%s/%s.%s" % [profile_id, layer_name, ext]
		if ResourceLoader.exists(res_path):
			return load(res_path)
	return null


func _load_fallback_stream(profile_id: String) -> AudioStream:
	var main_path := _resolve_audio_path("%s/%s" % [_assets_path, profile_id])
	if main_path != "":
		return _load_audio(main_path)
	var pad_path := _resolve_audio_path("%s/%s_pad" % [_assets_path, profile_id])
	if pad_path != "":
		return _load_audio(pad_path)
	return null


func _resolve_audio_path(stem: String) -> String:
	for ext in AUDIO_EXTENSIONS:
		var path := "%s.%s" % [stem, ext]
		if FileAccess.file_exists(path):
			return path
	return ""


func _load_audio(path: String) -> AudioStream:
	var ext := path.get_extension().to_lower()
	match ext:
		"wav":
			var wav: AudioStreamWAV = AudioStreamWAV.load_from_file(path)
			if wav == null:
				push_warning("Failed to load WAV: %s" % path)
				return null
			wav.loop_mode = AudioStreamWAV.LOOP_FORWARD
			return wav
		"mp3":
			var file := FileAccess.open(path, FileAccess.READ)
			if file == null:
				push_warning("Failed to open MP3: %s" % path)
				return null
			var mp3 := AudioStreamMP3.new()
			mp3.data = file.get_buffer(file.get_length())
			mp3.loop = true
			return mp3
		"ogg":
			var ogg := AudioStreamOggVorbis.load_from_file(path)
			if ogg == null:
				push_warning("Failed to load OGG: %s" % path)
			return ogg
		_:
			push_warning("Unsupported audio extension: %s" % path)
			return null


func _configure_player_loop(player: AudioStreamPlayer, stream: AudioStream) -> void:
	if stream is AudioStreamMP3:
		player.finished.connect(func() -> void:
			if _playing:
				player.play()
		)


func _apply_layer_params(players: Array[AudioStreamPlayer], params: Dictionary, mix: float = 1.0) -> void:
	var brightness: float = params.get("brightness", 0.5)
	var energy: float = params.get("energy", 0.4)
	var warmth: float = params.get("warmth", 0.55)
	var gain := (0.5 + (energy - 0.5) * 0.5) * (0.85 + brightness * 0.3) * (0.9 + warmth * 0.15)
	gain = clampf(gain, 0.05, 1.0) * _master_volume * mix
	var volume_db := linear_to_db(max(gain, 0.001))
	for player in players:
		if player.playing or mix > 0.01:
			player.volume_db = volume_db


func _set_layer_volumes(players: Array[AudioStreamPlayer], db: float) -> void:
	for player in players:
		player.volume_db = db


func _clear_layers(players: Array[AudioStreamPlayer]) -> void:
	for player in players:
		player.stop()
		player.queue_free()
	players.clear()


func _status_payload() -> Dictionary:
	return {
		"ok": true,
		"playing": _playing,
		"profile_id": _current_profile,
		"assets_path": _assets_path,
		"layer_count": _current_layers.size(),
		"layer_paths": _layer_paths(_current_layers),
	}


func _layer_paths(players: Array[AudioStreamPlayer]) -> Array[String]:
	var paths: Array[String] = []
	for player in players:
		if player.has_meta("source_path"):
			paths.append(str(player.get_meta("source_path")))
			continue
		var stream := player.stream
		if stream == null:
			continue
		if stream.resource_path != "":
			paths.append(stream.resource_path)
		elif stream is AudioStreamWAV:
			paths.append("wav:%s" % player.name)
		elif stream is AudioStreamMP3:
			paths.append("mp3:%s" % player.name)
		else:
			paths.append(player.name)
	return paths


func _send_json(payload: Dictionary) -> void:
	if _client == null:
		return
	var line := JSON.stringify(payload) + "\n"
	_client.put_data(line.to_utf8_buffer())
