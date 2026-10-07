"""Device selection and an MPS diagnostic (``python -m src.ml.device``)."""
from __future__ import annotations

import json
import platform
import time
from typing import Any, Dict


def resolve_device(preference: str = "auto") -> str:
    """Return 'mps', 'cuda' or 'cpu'. Falls back to CPU if the request can't be met."""
    pref = (preference or "auto").lower()
    try:
        import torch
    except ImportError:
        return "cpu"

    mps_ok = hasattr(torch.backends, "mps") and torch.backends.mps.is_available()
    cuda_ok = torch.cuda.is_available()

    if pref == "cpu":
        return "cpu"
    if pref == "mps":
        return "mps" if mps_ok else "cpu"
    if pref == "cuda":
        return "cuda" if cuda_ok else "cpu"
    if mps_ok:
        return "mps"
    if cuda_ok:
        return "cuda"
    return "cpu"


def device_report(preference: str = "auto") -> Dict[str, Any]:
    """Collect facts about the torch install and run a tiny CPU-vs-device matmul check."""
    report: Dict[str, Any] = {
        "platform": platform.platform(),
        "machine": platform.machine(),
        "python": platform.python_version(),
    }
    try:
        import torch
    except ImportError:
        report["torch_installed"] = False
        report["selected_device"] = "cpu"
        return report

    report["torch_installed"] = True
    report["torch_version"] = torch.__version__
    mps_backend = getattr(torch.backends, "mps", None)
    report["mps_built"] = bool(mps_backend and mps_backend.is_built())
    report["mps_available"] = bool(mps_backend and mps_backend.is_available())
    report["cuda_available"] = torch.cuda.is_available()
    selected = resolve_device(preference)
    report["selected_device"] = selected

    torch.manual_seed(0)
    a = torch.randn(1024, 1024)
    b = torch.randn(1024, 1024)
    expected = a @ b
    t0 = time.perf_counter()
    got = (a.to(selected) @ b.to(selected)).cpu()
    report["matmul_seconds_on_selected_device"] = round(time.perf_counter() - t0, 4)
    report["matmul_matches_cpu"] = bool(torch.allclose(expected, got, atol=1e-2, rtol=1e-3))
    return report


def main() -> None:
    report = device_report()
    print(json.dumps(report, indent=2))
    if report.get("selected_device") == "mps" and report.get("matmul_matches_cpu"):
        print("\nOK: PyTorch MPS acceleration is active.")
    elif report.get("torch_installed") and not report.get("mps_available"):
        print("\nMPS is not available - the pipeline will run on CPU. See README > 'Verify MPS'.")


if __name__ == "__main__":
    main()
