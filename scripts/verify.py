"""Run prompt-vcs verification consistently on Windows, Linux, and macOS."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import venv
import zipfile
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - exercised on Python 3.10
    import tomli as tomllib


ROOT = Path(__file__).resolve().parents[1]
EXTENSION_DIR = ROOT / "vscode-extension"


def run(label: str, command: list[str], *, cwd: Path = ROOT) -> None:
    """Run one verification step and stop immediately on failure."""
    print(f"\n==> {label}", flush=True)
    print("    " + " ".join(command), flush=True)
    subprocess.run(command, cwd=cwd, check=True)


def npm_executable() -> str:
    """Return the platform-appropriate npm executable."""
    executable = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    if executable is None:
        raise RuntimeError("npm was not found. Install Node.js 20 or newer.")
    return executable


def verify_python(*, quick: bool) -> None:
    run(
        "Python lint",
        [
            sys.executable,
            "-m",
            "ruff",
            "check",
            "--no-cache",
            "src",
            "tests",
            "scripts",
        ],
    )

    pytest_command = [
        sys.executable,
        "-m",
        "pytest",
        "-p",
        "no:cacheprovider",
    ]
    if quick:
        pytest_command.append("-q")
    else:
        pytest_command.extend(
            [
                "tests",
                "--cov=prompt_vcs",
                "--cov-report=term-missing",
                "--cov-fail-under=70",
                "-v",
            ]
        )
    run("Python tests", pytest_command)

    if not quick:
        run(
            "Validation example",
            [sys.executable, "examples/validation_testing_demo.py"],
        )


def verify_extension(*, quick: bool, release: bool) -> None:
    npm = npm_executable()
    if not (EXTENSION_DIR / "node_modules").exists():
        raise RuntimeError(
            "vscode-extension/node_modules is missing. "
            "Run `npm --prefix vscode-extension ci` first."
        )

    run("Extension typecheck", [npm, "run", "typecheck"], cwd=EXTENSION_DIR)
    run("Extension tests", [npm, "test"], cwd=EXTENSION_DIR)

    if not quick:
        run("Extension compile", [npm, "run", "compile"], cwd=EXTENSION_DIR)
    if release:
        run(
            "Extension dependency audit",
            [npm, "audit", "--audit-level=high"],
            cwd=EXTENSION_DIR,
        )


def project_version() -> str:
    with open(ROOT / "pyproject.toml", "rb") as config_file:
        return tomllib.load(config_file)["project"]["version"]


def venv_python(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def venv_pvcs(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / "pvcs.exe"
    return venv_dir / "bin" / "pvcs"


def verify_release() -> None:
    version = project_version()
    wheel = ROOT / "dist" / f"prompt_vcs-{version}-py3-none-any.whl"
    sdist = ROOT / "dist" / f"prompt_vcs-{version}.tar.gz"

    run("Build distributions", [sys.executable, "-m", "build"])
    if not wheel.exists() or not sdist.exists():
        raise RuntimeError(f"Expected release artifacts for version {version} were not built")

    run(
        "Check distribution metadata",
        [sys.executable, "-m", "twine", "check", str(wheel), str(sdist)],
    )

    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
    if "prompt_vcs/py.typed" not in names:
        raise RuntimeError("Built wheel is missing prompt_vcs/py.typed")
    if any("vscode-extension" in name or ".npm-cache" in name for name in names):
        raise RuntimeError("Built wheel contains unintended extension/cache files")

    with tempfile.TemporaryDirectory(prefix="prompt-vcs-wheel-smoke-") as temp_dir:
        environment = Path(temp_dir) / "venv"
        venv.EnvBuilder(with_pip=True, system_site_packages=True).create(environment)
        python = venv_python(environment)
        pvcs = venv_pvcs(environment)
        run(
            "Install built wheel",
            [str(python), "-m", "pip", "install", "--no-deps", str(wheel)],
        )
        run(
            "Import built wheel",
            [
                str(python),
                "-c",
                (
                    "import prompt_vcs; "
                    f"assert prompt_vcs.__version__ == {version!r}; "
                    "print(prompt_vcs.__file__)"
                ),
            ],
        )
        run("Smoke-test installed CLI", [str(pvcs), "--help"])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument(
        "--python-only",
        action="store_true",
        help="Run only Python checks.",
    )
    scope.add_argument(
        "--extension-only",
        action="store_true",
        help="Run only VS Code extension checks.",
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Skip coverage, examples, extension compilation, and release checks.",
    )
    parser.add_argument(
        "--release",
        action="store_true",
        help="Also audit dependencies, build artifacts, and smoke-test the wheel.",
    )
    args = parser.parse_args()
    if args.quick and args.release:
        parser.error("--quick and --release cannot be used together")
    if args.extension_only and args.release:
        parser.error("--release requires the Python verification scope")
    return args


def main() -> int:
    args = parse_args()
    try:
        if not args.extension_only:
            verify_python(quick=args.quick)
        if not args.python_only:
            verify_extension(quick=args.quick, release=args.release)
        if args.release:
            verify_release()
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"\nVerification failed: {exc}", file=sys.stderr)
        return 1

    print("\nAll requested verification steps passed.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
