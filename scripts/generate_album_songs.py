"""Generate new album song seeds via MusicGen (full-mix prompts).

Creates a new song family under ``assets/audio/<scenario>/`` by writing a
generated focus loop, then optionally Demucs + AI intensity layers.

```powershell
conda activate MTX
python scripts/generate_album_songs.py --scenario programming --count 2
python scripts/generate_album_songs.py --all-scenarios --count 1 --no-separate --no-ai-layers
```

Stub (no GPU): set ``MUSICGEN_STUB=1`` in the musicgen env before starting the sidecar.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

# Line-buffer stdout so long MusicGen jobs still show progress in CI/terminals.
try:
    sys.stdout.reconfigure(line_buffering=True)  # type: ignore[attr-defined]
except Exception:
    pass

from adaptive_soundscape.audio.album import add_track
from adaptive_soundscape.audio.generate_layers import (
    generate_and_install_layer,
    validate_wav_bytes,
)
from adaptive_soundscape.audio.music_manifest import MusicIntensity, song_dirs
from adaptive_soundscape.audio.musicgen_client import MusicGenClient
from adaptive_soundscape.audio.prompt_builder import build_song_prompt, scenario_bpm
from adaptive_soundscape.audio.demucs_client import DemucsClient
from adaptive_soundscape.audio.separate_stems import separate_and_install_stems
from adaptive_soundscape.audio.sidecar_lifecycle import SidecarLifecycle
from adaptive_soundscape.core.config import load_settings, resolve_assets_dir

PROFILE_IDS = (
    "programming",
    "scientific",
    "reading_writing",
    "creative_design",
    "team_workflow",
    "distraction",
    "unknown",
)


def _next_song_id(assets: Path, scenario: str, prefix: str) -> str:
    existing = {p.name for p in song_dirs(assets, scenario)}
    n = 1
    while True:
        candidate = f"{prefix}_{n:02d}"
        if candidate not in existing:
            return candidate
        n += 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", default="programming")
    parser.add_argument(
        "--all-scenarios",
        action="store_true",
        help="Generate for every scenario profile",
    )
    parser.add_argument("--count", type=int, default=1, help="Songs per scenario")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--no-separate",
        action="store_true",
        help="Skip Demucs after writing the seed mix",
    )
    parser.add_argument(
        "--no-ai-layers",
        action="store_true",
        help="Skip MusicGen intensity layers (texture / melody_b)",
    )
    parser.add_argument(
        "--prefix",
        default="",
        help="Song id prefix (default: <scenario>_gen)",
    )
    args = parser.parse_args(argv)

    settings = load_settings()
    gen = settings.generative_layers
    stem_cfg = settings.stem_separation
    side_cfg = settings.sidecar_apis
    if not gen.enabled:
        print("generative_layers.enabled is false in config")
        return 1
    assets = resolve_assets_dir(settings)
    scenarios = list(PROFILE_IDS) if args.all_scenarios else [args.scenario]
    for sc in scenarios:
        if sc not in PROFILE_IDS:
            print(f"Unknown scenario: {sc}")
            return 1

    lifecycle = SidecarLifecycle(
        demucs_env=stem_cfg.conda_env,
        musicgen_env=gen.conda_env,
        startup_timeout_seconds=side_cfg.startup_timeout_seconds,
        stop_when_done=side_cfg.stop_when_done,
    )
    need_demucs = (
        not args.no_separate and stem_cfg.enabled and stem_cfg.auto_start_api
    )
    need_musicgen = bool(gen.auto_start_api)

    try:
        if need_musicgen:
            print("Ensuring MusicGen sidecar…")
            lifecycle.ensure(lifecycle.musicgen)
        if need_demucs:
            print("Ensuring Demucs sidecar…")
            lifecycle.ensure(lifecycle.demucs)

        client = MusicGenClient(
            gen.api_base_url, timeout_seconds=gen.timeout_seconds
        )
        try:
            health = client.health()
            print(f"MusicGen health: {health}")
        except RuntimeError as exc:
            print(exc)
            return 1

        loop_seconds = 27.428
        failures = 0
        created: list[Path] = []

        for scenario in scenarios:
            prefix = args.prefix or f"{scenario}_gen"
            bpm = scenario_bpm(scenario)
            for i in range(max(1, args.count)):
                song_id = _next_song_id(assets, scenario, prefix)
                built = build_song_prompt(
                    scenario=scenario,
                    variant_index=i,
                    bpm=bpm,
                    loop_seconds=loop_seconds,
                )
                seed = int(args.seed) + i * 17 + (abs(hash(scenario)) % 1000)
                print(f"GENERATE song {scenario}/{song_id} (seed={seed}) …")
                try:
                    resp = client.generate_layer(
                        prompt=built.prompt,
                        negative_prompt=built.negative_prompt,
                        duration_seconds=loop_seconds,
                        bpm=bpm,
                        seed=seed,
                        model_size=gen.model_size,
                    )
                    validate_wav_bytes(
                        resp.wav_bytes,
                        expected_seconds=loop_seconds,
                        tolerance=0.12,
                    )
                    with tempfile.TemporaryDirectory() as tmp:
                        wav_path = Path(tmp) / f"{song_id}.wav"
                        wav_path.write_bytes(resp.wav_bytes)
                        dest = add_track(
                            assets,
                            scenario,
                            wav_path,
                            intensity=MusicIntensity.FOCUS,
                            song_id=song_id,
                        )
                    song_dir = dest.parent.parent
                    created.append(song_dir)
                    print(f"  wrote {dest}")

                    if not args.no_separate and stem_cfg.enabled:
                        print(f"  Demucs → layers for {song_id} …")
                        try:
                            demucs = DemucsClient(
                                stem_cfg.api_base_url,
                                timeout_seconds=stem_cfg.timeout_seconds,
                            )
                            paths = separate_and_install_stems(
                                song_dir,
                                client=demucs,
                                model=stem_cfg.model,
                                force=False,
                            )
                            print(f"  stems: {len(paths)} file(s)")
                        except Exception as exc:
                            print(f"  WARN demucs: {exc}")
                            failures += 1

                    if not args.no_ai_layers:
                        for layer_id in list(gen.output_layers):
                            print(f"  AI layer {layer_id} …")
                            try:
                                generate_and_install_layer(
                                    song_dir,
                                    scenario=scenario,
                                    layer_id=layer_id,
                                    client=client,
                                    model_size=gen.model_size,
                                    seed=seed + abs(hash(layer_id)) % 97,
                                )
                            except Exception as exc:
                                print(f"  WARN {layer_id}: {exc}")
                                failures += 1
                except Exception as exc:
                    print(f"FAIL {scenario}/{song_id}: {exc}")
                    failures += 1

        print(f"Created {len(created)} song(s); failures={failures}")
        for p in created:
            print(f"  {p.relative_to(assets)}")
        return 1 if failures and not created else 0
    finally:
        lifecycle.stop_owned()


if __name__ == "__main__":
    raise SystemExit(main())
