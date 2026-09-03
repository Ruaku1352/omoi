"""ローカル速度計測に必要な再現可能な環境fingerprintをprivate artifactへ保存する。"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import platform
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL_PATH = REPO_ROOT / "backend" / ".models" / "efficientsam_ti.onnx"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "poc-output" / "performance-optimization-environment"


def _run(command: list[str]) -> str | None:
    try:
        completed = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None
    return (completed.stdout or "").strip() or None


def _powershell_json(script: str) -> dict[str, Any] | None:
    output = _run(["powershell", "-NoProfile", "-Command", script])
    if output is None:
        return None
    try:
        parsed = json.loads(output)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _package_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def _git(*args: str) -> str | None:
    return _run(["git", *args])


def collect(model_path: Path) -> dict[str, Any]:
    try:
        import onnxruntime as ort
    except ImportError:
        providers: list[str] | None = None
    else:
        providers = list(ort.get_available_providers())

    hardware = _powershell_json(
        """
        $ErrorActionPreference = 'Stop'
        $cpu = Get-CimInstance Win32_Processor
        $os = Get-CimInstance Win32_OperatingSystem
        $cs = Get-CimInstance Win32_ComputerSystem
        $gpu = Get-CimInstance Win32_VideoController
        $battery = Get-CimInstance Win32_Battery -ErrorAction SilentlyContinue
        [pscustomobject]@{
          cpuName = ($cpu.Name -join '; ')
          physicalCores = ($cpu.NumberOfCores | Measure-Object -Sum).Sum
          logicalProcessors = ($cpu.NumberOfLogicalProcessors | Measure-Object -Sum).Sum
          maxClockMHz = ($cpu.MaxClockSpeed | Measure-Object -Maximum).Maximum
          ramGB = [math]::Round($cs.TotalPhysicalMemory / 1GB, 2)
          os = $os.Caption
          osVersion = $os.Version
          gpu = ($gpu.Name -join '; ')
          batteryStatus = ($battery.BatteryStatus -join '; ')
          batteryEstimatedChargeRemaining = ($battery.EstimatedChargeRemaining -join '; ')
        } | ConvertTo-Json -Compress
        """
    )
    model: dict[str, Any] = {"path": str(model_path), "exists": model_path.is_file()}
    if model_path.is_file():
        model["sizeBytes"] = model_path.stat().st_size
        model["sha256"] = _sha256(model_path)

    return {
        "capturedAt": datetime.now(UTC).isoformat(),
        "repository": {
            "branch": _git("branch", "--show-current"),
            "revision": _git("rev-parse", "HEAD"),
            "baseRevision": _git(
                "rev-parse", "origin/codex/ai-quality-baseline-review"
            ),
            "statusShort": _git("status", "--short"),
        },
        "runtime": {
            "pythonExecutable": sys.executable,
            "pythonVersion": platform.python_version(),
            "numpyVersion": _package_version("numpy"),
            "pillowVersion": _package_version("pillow"),
            "onnxruntimeVersion": _package_version("onnxruntime"),
            "onnxruntimeAvailableProviders": providers,
        },
        "hardware": hardware,
        "power": {"activeScheme": _run(["powercfg", "/GETACTIVESCHEME"])},
        "model": model,
        "notes": [
            "Benchmark runs require AC power, sleep disabled, lid open, and no competing heavy workload.",
            "This artifact intentionally excludes environment variables and all secrets.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--model-path", type=Path, default=DEFAULT_MODEL_PATH)
    args = parser.parse_args()

    artifact = collect(args.model_path.resolve())
    args.output_dir.mkdir(parents=True, exist_ok=True)
    output_path = args.output_dir / "environment.json"
    output_path.write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
