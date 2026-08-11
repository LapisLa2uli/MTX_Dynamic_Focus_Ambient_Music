"""One-shot real MusicGen generate → WAV (no stub, no FastAPI)."""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from generate import MusicGenEngine


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--prompt",
        default=(
            "soft instrumental ambient focus music, gentle pads, light melody, "
            "no vocals, calm studio quality, 70 BPM"
        ),
    )
    parser.add_argument("--seconds", type=float, default=30.0)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--model-size", default="small")
    parser.add_argument(
        "--out",
        default=str(Path(__file__).resolve().parent / "outputs" / "test_30s.wav"),
    )
    args = parser.parse_args()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    print(f"Loading MusicGen ({args.model_size}) …")
    t0 = time.perf_counter()
    engine = MusicGenEngine(model_size=args.model_size)
    engine.load()
    print(f"Loaded in {time.perf_counter() - t0:.1f}s on {engine.device} ({engine.model_id})")

    print(f"Generating {args.seconds}s …")
    print(f"Prompt: {args.prompt}")
    t1 = time.perf_counter()
    wav_bytes, duration = engine.generate(
        prompt=args.prompt,
        duration_seconds=args.seconds,
        seed=args.seed,
    )
    out.write_bytes(wav_bytes)
    print(f"Wrote {out} ({len(wav_bytes)} bytes, {duration:.2f}s) in {time.perf_counter() - t1:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
