"""EfficientSAM-Tiの公式ONNX artifactをRuntime外で取得・checksum検証する。

Official yformer/EfficientSAM READMEが案内するHugging Face Space内の、単一ONNX版を使う。
このscriptはDocker/Cloud Run Runtimeからは呼ばない。
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
from urllib.request import urlopen

OFFICIAL_ONNX_URL = (
    "https://huggingface.co/spaces/yunyangx/EfficientSAM/resolve/d8dbb1e/efficientsam_ti.onnx"
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parents[1]
        / "backend"
        / ".models"
        / "efficientsam_ti.onnx",
    )
    parser.add_argument("--url", default=OFFICIAL_ONNX_URL)
    parser.add_argument(
        "--sha256",
        help="Expected SHA-256. Set this for a reproducible deploy artifact.",
    )
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    with urlopen(args.url, timeout=120) as response, args.output.open("wb") as output:
        while chunk := response.read(1024 * 1024):
            digest.update(chunk)
            output.write(chunk)
    actual = digest.hexdigest()
    if args.sha256 and actual.lower() != args.sha256.lower():
        args.output.unlink(missing_ok=True)
        raise SystemExit("SHA-256 mismatch; incomplete artifact was removed")
    print(f"downloaded={args.output}")
    print(f"sha256={actual}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
