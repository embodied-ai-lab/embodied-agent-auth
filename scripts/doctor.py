#!/usr/bin/env python3
"""Read-only environment checks for the ROS 2, SST, and live VLM environment."""

from __future__ import annotations

import importlib.metadata
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IOTAUTH = ROOT / "third_party" / "iotauth"
REQUIRED_API = ("IoTAuthContext", "SecureClient", "SecureServer", "SecureChannel")


class Report:
    def __init__(self) -> None:
        self.failed = False

    def row(self, name: str, ok: bool, detail: str, *, required: bool = True) -> None:
        marker = " ok " if ok else ("FAIL" if required else "warn")
        print(f"[{marker}] {name:24} {detail}")
        if required and not ok:
            self.failed = True


def command(args: list[str]) -> tuple[int, str]:
    try:
        result = subprocess.run(
            args, capture_output=True, text=True, timeout=10, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 127, str(exc)
    return result.returncode, (result.stdout + result.stderr).strip()


def endpoint_json(url: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"} if data else {},
        method="POST" if data else "GET",
    )
    with urllib.request.urlopen(request, timeout=4) as response:  # noqa: S310
        return json.loads(response.read())


def main() -> int:
    report = Report()
    print("ISCPS embodied-agent-auth environment doctor")
    print(f"host={socket.gethostname()} platform={platform.platform()}")
    report.row(
        "Python 3.10-3.12",
        (3, 10) <= sys.version_info[:2] < (3, 13),
        f"{platform.python_version()} ({sys.executable})",
    )
    try:
        import rclpy

        report.row("rclpy Python ABI", True, str(Path(rclpy.__file__).resolve()))
    except Exception as exc:
        system_code, system_output = command(
            ["/usr/bin/python3", "-c", "import rclpy; print(rclpy.__file__)"]
        )
        if system_code == 0:
            detail = (
                f"{sys.executable} cannot import rclpy, but /usr/bin/python3 can "
                f"({system_output}); recreate .venv with make setup"
            )
        else:
            detail = (
                f"{sys.executable} cannot import rclpy ({exc}); "
                "install/source ROS 2 Jazzy and use its system Python"
            )
        report.row("rclpy Python ABI", False, detail)

    code, tree = command(["git", "-C", str(ROOT), "ls-tree", "HEAD", "third_party/iotauth"])
    recorded = tree.split()[2] if code == 0 and len(tree.split()) >= 3 else ""
    initialized = (IOTAUTH / "entity" / "python" / "pyproject.toml").is_file()
    report.row(
        "iotauth submodule",
        initialized,
        "initialized" if initialized else "run: make submodules",
    )
    checked_out = ""
    if initialized:
        code, checked_out = command(["git", "-C", str(IOTAUTH), "rev-parse", "HEAD"])
        checked_out = checked_out.strip()
    report.row(
        "submodule commit",
        bool(recorded) and checked_out == recorded,
        f"recorded={recorded[:12] or '?'} checked_out={checked_out[:12] or '?'}",
    )
    report.row(
        "no dependency copy",
        not (ROOT / ".deps" / "iotauth").exists(),
        (
            "no legacy dependency tree is present"
            if not (ROOT / ".deps" / "iotauth").exists()
            else "review and remove the legacy dependency tree"
        ),
    )

    try:
        import iotauth

        missing = [name for name in REQUIRED_API if not hasattr(iotauth, name)]
        module_path = Path(iotauth.__file__).resolve()
        expected = (IOTAUTH / "entity" / "python").resolve()
        direct_url = importlib.metadata.distribution("iotauth").read_text(
            "direct_url.json"
        )
        installed_from = None
        if direct_url:
            source_url = json.loads(direct_url).get("url", "")
            parsed = urllib.parse.urlparse(source_url)
            if parsed.scheme == "file":
                installed_from = Path(urllib.parse.unquote(parsed.path)).resolve()
        from_submodule = expected in module_path.parents or installed_from == expected
        report.row(
            "iotauth public API",
            not missing,
            "all required names present" if not missing else f"missing: {missing}",
        )
        report.row(
            "iotauth install source",
            from_submodule,
            f"module={module_path}; source={installed_from or 'unknown'}",
        )
    except Exception as exc:
        report.row("iotauth public API", False, f"{exc}; run: make setup")

    for name, args in (
        ("ROS 2 Jazzy", ["ros2", "--help"]),
        ("colcon", ["colcon", "--help"]),
        ("Java", ["java", "-version"]),
        ("Maven", ["mvn", "--version"]),
        ("Node", ["node", "--version"]),
        ("OpenSSL", ["openssl", "version"]),
    ):
        code, output = command(args)
        required = name in {"ROS 2 Jazzy", "colcon"}
        report.row(
            name,
            code == 0,
            output.splitlines()[0] if output else "not found",
            required=required,
        )
    code, output = command([sys.executable, "-m", "colcon", "--help"])
    report.row(
        "python -m colcon",
        code == 0,
        (
            output.splitlines()[0]
            if output
            else "unsupported; scripts/build.sh will use the colcon executable"
        ),
        required=False,
    )

    endpoint = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
    if not endpoint.startswith(("http://", "https://")):
        endpoint = f"http://{endpoint}"
    endpoint = endpoint.rstrip("/")
    model = os.environ.get("VLM_MODEL", "qwen2.5vl:3b")
    try:
        version = str(endpoint_json(f"{endpoint}/api/version").get("version", "unknown"))
        tags = endpoint_json(f"{endpoint}/api/tags")
        names = [str(item.get("name")) for item in tags.get("models", [])]
        details = endpoint_json(f"{endpoint}/api/show", {"model": model}) if model in names else {}
        capabilities = details.get("capabilities", [])
        report.row("Ollama endpoint", True, f"{endpoint}, version={version}")
        report.row("required VLM", model in names, f"{model}; installed={names}")
        report.row(
            "vision capability",
            "vision" in capabilities,
            str(capabilities or "model not available"),
        )
    except (OSError, urllib.error.URLError, ValueError, json.JSONDecodeError) as exc:
        report.row("Ollama endpoint", False, f"{endpoint}: {exc}")
        report.row("required VLM", False, f"{model} could not be checked")

    gpu = shutil.which("nvidia-smi")
    code, output = command(
        [gpu, "--query-gpu=name,memory.total", "--format=csv,noheader"]
        if gpu
        else ["nvidia-smi"]
    )
    report.row(
        "GPU visibility",
        code == 0,
        output.splitlines()[0] if output else "not visible; course endpoint is also supported",
        required=False,
    )
    print("\nRun `make vlm-check` for the required image + structured-output inference.")
    return 1 if report.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
