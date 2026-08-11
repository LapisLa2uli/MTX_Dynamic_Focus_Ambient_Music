"""One-shot Demucs separate → WAV stems (optional stub via DEMUCS_STUB)."""

from __future__ import annotations

import argparse
import time
import wave
from pathlib import Path

import numpy as np

from separate import DemucsEngine


def _sine_wav(seconds: float = 2.0, rate: int = 44100) -> bytes:
    import io

    t = np.linspace(0, seconds, int(rate * seconds), endpoint=False)
    samples = (0.2 * np.sin(2 * np.pi * 220 * t) * 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(samples.tobytes())
    return buf.getvalue()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="", help="Optional mix path (.wav/.mp3)")
    parser.add_argument("--model", default="htdemucs")
    parser.add_argument(
        "--out-dir",
        default=str(Path(__file__).resolve().parent / "outputs" / "smoke"),
    )
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.input:
        audio = Path(args.input).read_bytes()
        filename = Path(args.input).name
    else:
        audio = _sine_wav(2.0)
        filename = "stub_mix.wav"

    print(f"Loading Demucs ({args.model}) …")
    t0 = time.perf_counter()
    engine = DemucsEngine(model=args.model)
    engine.load()
    print(
        f"Loaded in {time.perf_counter() - t0:.1f}s on {engine.device} "
        f"(stub={engine.stub_mode})"
    )

    print("Separating …")
    t1 = time.perf_counter()
    stems, duration = engine.separate(audio, filename=filename)
    for name, wav in stems.items():
        dest = out_dir / f"{name}.wav"
        dest.write_bytes(wav)
        print(f"  wrote {dest} ({len(wav)} bytes)")
    print(f"Done in {time.perf_counter() - t1:.1f}s (duration={duration:.2f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
