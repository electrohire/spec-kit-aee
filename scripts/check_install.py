#!/usr/bin/env python3
"""Install both real extensions in a disposable Spec Kit project; no inference.

Every verification is an explicit check that raises with a message
(RT3-16): bare ``assert`` statements are stripped under ``python -O``,
which would silently turn this script into a no-op that prints PASS.
The AEE extension under test can be installed from a local directory
(the ``--dev`` flow) or, with ``--from-archive``, from a release zip —
the flow real users follow.
"""
from __future__ import annotations

import argparse
import functools
import http.server
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
from collections.abc import Callable
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *_args: object) -> None:
        pass


def _serve_archive(archive: Path) -> tuple[http.server.ThreadingHTTPServer, str]:
    """Serve a release zip on an ephemeral localhost port.

    ``specify extension add --from`` accepts URLs only (a bare local
    path is rejected as an invalid URL), so archive mode serves the
    zip over loopback HTTP — the same download path a real catalog
    install exercises, without any network dependency.
    """
    handler = functools.partial(_QuietHandler, directory=str(archive.parent))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}/{archive.name}"


class CheckFailed(RuntimeError):
    """A verification in this script failed; the message says which."""


def check(condition: bool, message: str) -> None:
    if not condition:
        raise CheckFailed(message)


def _retry_after_clearing_readonly(
    func: Callable[[str], object], path: str, _exc: object
) -> None:
    """rmtree error handler: clear the read-only bit and retry the call.

    The scratch install copies the evaluator extension *with* its
    `.git` directory, whose object files are read-only. Windows
    refuses to unlink a read-only file (POSIX unlink ignores the
    bit), so removal of the real installed tree fails there with
    WinError 5 unless the bit is cleared first. The third argument is
    the exception (3.12+ ``onexc``) or an exc_info tuple (``onerror``);
    it is not needed either way.
    """
    os.chmod(path, stat.S_IWRITE)
    func(path)


def _rmtree(root: Path) -> None:
    """Remove a tree that may contain a copied `.git`, on any OS."""
    if sys.version_info >= (3, 12):
        shutil.rmtree(root, onexc=_retry_after_clearing_readonly)
    else:
        shutil.rmtree(root, onerror=_retry_after_clearing_readonly)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evaluator-dir", type=Path, required=True)
    parser.add_argument("--aee-dir", type=Path, default=ROOT)
    parser.add_argument(
        "--from-archive",
        type=Path,
        default=None,
        help="install the AEE extension from this release zip instead "
        "of the local --aee-dir directory",
    )
    args = parser.parse_args()
    evaluator = args.evaluator_dir.resolve(strict=True)
    specify = shutil.which("specify")
    check(
        specify is not None,
        "specify not found: activate the requirements/dev.txt environment",
    )
    archive: Path | None = None
    aee_source: Path | None = None
    server: http.server.ThreadingHTTPServer | None = None
    archive_url: str | None = None
    if args.from_archive is not None:
        archive = args.from_archive.resolve(strict=True)
        server, archive_url = _serve_archive(archive)
    else:
        aee_source = args.aee_dir.resolve(strict=True)
    env = {**os.environ, "PYTHONUTF8": "1", "NO_COLOR": "1"}
    try:
        _run_checks(specify, evaluator, aee_source, archive_url, env)
    finally:
        if server is not None:
            server.shutdown()
    origin = "release archive" if archive is not None else "local directory"
    print(f"PASS: initialized project, both extensions, ten rendered commands, "
          f"five AEE hooks, resolved placeholders, and all six installed "
          f"operations (aee installed from {origin})")


def _run_checks(
    specify: str,
    evaluator: Path,
    aee_source: Path | None,
    archive_url: str | None,
    env: dict[str, str],
) -> None:
    with tempfile.TemporaryDirectory(prefix="aee-install-") as directory:
        root = Path(directory)

        def command(*parts: str, code: int = 0) -> str:
            # `specify extension add --from <url>` prompts
            # "Continue with installation? [y/N]:" and hangs forever on
            # an unattended stdin; feed affirmative answers (harmless
            # for the non-interactive commands).
            completed = subprocess.run(
                list(parts), cwd=root, env=env, text=True, encoding="utf-8",
                input="y\n" * 20, capture_output=True, check=False,
            )
            check(
                completed.returncode == code,
                f"command {parts!r} exited {completed.returncode}, "
                f"expected {code}:\n{completed.stdout}{completed.stderr}",
            )
            return completed.stdout

        command(specify, "init", "--here", "--integration", "claude",
                "--ignore-agent-tools", "--non-interactive")
        command(specify, "extension", "add", "--dev", str(evaluator))
        if archive_url is not None:
            command(specify, "extension", "add", "aee", "--from", archive_url)
        else:
            check(aee_source is not None, "an aee source is required")
            command(specify, "extension", "add", "--dev", str(aee_source))
        listed = command(specify, "extension", "list", "--json")
        installed = {item["id"]: item for item in json.loads(listed)}
        check(
            installed["evaluator"]["enabled"] and installed["aee"]["enabled"],
            f"both extensions must be enabled after install: {listed}",
        )
        check(
            installed["aee"]["provides"]["commands"] == 10,
            "aee must provide ten commands, got "
            f"{installed['aee']['provides']['commands']}",
        )
        check(
            installed["aee"]["provides"]["hooks"] == 5,
            "aee must provide five hooks, got "
            f"{installed['aee']['provides']['hooks']}",
        )
        commands = list((root / ".claude/commands").glob("speckit.aee.*.md"))
        commands += list((root / ".claude/skills").glob("speckit-aee-*/SKILL.md"))
        check(len(commands) == 10, f"expected ten rendered commands: {commands}")
        for path in commands:
            check(
                not re.search(r"__SPECKIT_COMMAND_[A-Z_]+__", path.read_text()),
                f"unresolved command placeholder left in {path}",
            )
        hooks = yaml.safe_load((root / ".specify/extensions.yml").read_text())["hooks"]
        check("after_verify" in hooks, f"after_verify hook missing: {hooks}")
        shutil.copyfile(root / ".specify/extensions/aee/templates/aee-claims.json",
                        root / "claims.json")
        claims_path = root / "claims.json"
        claims = json.loads(claims_path.read_text())
        claims["claims"][0]["status"] = "draft"
        claims["claims"][0]["evidence"] = []
        claims_path.write_text(json.dumps(claims))
        result = command(sys.executable,
                         str(root / ".specify/extensions/aee/scripts/python/run_aee.py"),
                         "assess", "--input", "claims.json", code=1)
        paths = json.loads(result)
        check(
            (root / paths["assessment"]).is_file(),
            f"assess named a missing assessment file: {paths}",
        )
        check(
            (root / paths["evaluator_result"]).is_file(),
            f"assess named a missing evaluator result: {paths}",
        )
        runner = str(root / ".specify/extensions/aee/scripts/python/run_aee.py")
        command(sys.executable, runner, "gate", "--input", paths["assessment"], code=1)
        verified = json.loads(command(sys.executable, runner, "verify"))
        check(
            verified["valid"] and verified["entries"] == 1,
            f"ledger must verify with exactly one entry: {verified}",
        )
        graph = json.loads(command(sys.executable, runner, "graph", "--input", "claims.json"))
        check(
            (root / graph["graph"]).is_file(),
            f"graph named a missing file: {graph}",
        )
        challenge = json.loads(command(sys.executable, runner, "challenge",
                                       "--input", "claims.json", code=1))
        check(
            (root / challenge["challenge"]).is_file(),
            f"challenge named a missing file: {challenge}",
        )
        (root / "matrix.md").write_text(
            "| Test ID | Requirements | Layer | Gate |\n"
            "| T-API-001 | Returns 200 | integration | gate-1 |\n")
        (root / "evidence").mkdir()
        command(sys.executable, runner, "gaps", "--matrix", "matrix.md",
                "--evidence", "evidence", "--output", "GAPS.md")
        check(
            "**Open:** 1" in (root / "GAPS.md").read_text(),
            "gap register must show the one open gap",
        )
        # RT3-01 exit-code contract, exercised against the installed
        # runner: a missing input is a clean refusal (exit 2), never a
        # traceback and never the scored-verdict code 1.
        refused = subprocess.run(
            [sys.executable, runner, "assess", "--input", "does-not-exist.json"],
            cwd=root, env=env, text=True, encoding="utf-8",
            capture_output=True, check=False,
        )
        check(
            refused.returncode == 2,
            f"missing input must exit 2, got {refused.returncode}",
        )
        check(
            "Traceback" not in refused.stderr and "refused:" in refused.stderr,
            f"missing input must refuse cleanly: {refused.stderr}",
        )
        # Spec 005 (ER-04): the evaluator extension is a required
        # companion, enforced by the runner itself. Remove it from the
        # installed project and the installed runner's assess must
        # refuse — exit 2, naming the missing extension — instead of
        # scoring without the common evaluator.
        evaluator_dir = root / ".specify" / "extensions" / "evaluator"
        assessments_dir = root / ".specify" / "extensions" / "aee" / "assessments"
        before = {path.name for path in assessments_dir.glob("*.json")}
        _rmtree(evaluator_dir)
        refused = subprocess.run(
            [sys.executable, runner, "assess", "--input", "claims.json"],
            cwd=root, env=env, text=True, encoding="utf-8",
            capture_output=True, check=False,
        )
        check(
            refused.returncode == 2,
            "assess without the evaluator extension must exit 2, got "
            f"{refused.returncode}",
        )
        check(
            "spec-kit-evaluator" in refused.stderr
            and "Traceback" not in refused.stderr,
            "assess without the evaluator extension must refuse cleanly "
            f"naming it: {refused.stderr}",
        )
        check(
            {path.name for path in assessments_dir.glob("*.json")} == before,
            "a refused assess must not write a new assessment",
        )


if __name__ == "__main__":
    try:
        main()
    except CheckFailed as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
