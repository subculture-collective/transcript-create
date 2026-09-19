"""Bounded, offline audio/ML smoke; no model download or production data access."""

from __future__ import annotations

import argparse
import math
import struct
import tempfile
import wave
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cpu", help="cuda also selects ROCm via Torch")
    args = parser.parse_args()

    import torch
    import torchaudio
    from pyannote.audio.core.task import Problem, Resolution, Specifications
    from pyannote.audio.models.segmentation import PyanNet
    from torchcodec.decoders import AudioDecoder

    torch.set_num_threads(2)
    if args.device == "cuda" and not torch.cuda.is_available():
        raise SystemExit("Requested accelerator is unavailable")
    with tempfile.TemporaryDirectory(prefix="hasanara-ml-smoke-") as directory:
        path = Path(directory) / "tone.wav"
        with wave.open(str(path), "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(16000)
            output.writeframes(
                b"".join(struct.pack("<h", int(8000 * math.sin(i * 2 * math.pi * 440 / 16000))) for i in range(16000))
            )
        samples = AudioDecoder(str(path)).get_all_samples()
        assert samples.sample_rate == 16000 and samples.data.shape == (1, 16000)
        assert samples.data.abs().max() > 0.1
        assert torchaudio.functional.resample(samples.data, 16000, 8000).shape == (1, 8000)

    # Random weights exercise the installed architecture, not model quality.
    model = PyanNet()
    model.specifications = Specifications(
        problem=Problem.MULTI_LABEL_CLASSIFICATION,
        resolution=Resolution.FRAME,
        duration=2.0,
        classes=["speaker1", "speaker2"],
    )
    model.setup()
    model.eval().to(args.device)
    with torch.inference_mode():
        prediction = model(torch.zeros(1, 1, 32000, device=args.device))
    assert prediction.shape[0] == 1 and prediction.shape[-1] == 2
    assert bool(torch.isfinite(prediction).all())
    device = torch.cuda.get_device_name(0) if args.device == "cuda" else "CPU"
    print(f"Audio decode/resample and synthetic pyannote forward passed: {torch.__version__}, {device}")


if __name__ == "__main__":
    main()
