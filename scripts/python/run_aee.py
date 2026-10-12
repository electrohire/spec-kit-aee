#!/usr/bin/env python3
"""Path-safe Spec Kit adapter for the external ``aee`` command.

Exit-code contract (runner level)
---------------------------------
The runner passes the engine's scored verdicts through unchanged and
reserves one code for every error, so a caller that only sees the exit
code can never mistake a failure for a scored outcome:

- ``0`` — engine outcome ``pass``/``warn``, or a successful non-scored
  operation (graph, gaps, verify, review).
- ``1`` — engine scored outcome ``iterate``/``clarify``/
  ``gather_evidence`` (assess, challenge, gate). Recovery is needed;
  this is a verdict, not an error.
- ``2`` — an error, never a scored assess/challenge verdict: runner
  refusals (missing, out-of-root, or symlinked paths; invalid phase;
  missing ``aee``; an ``aee`` version outside the required range;
  ``assess`` without the required spec-kit-evaluator extension) and
  engine-reported input/usage errors. (The engine's own ``gate``
  command also uses ``2`` for a ``block`` verdict; that is the
  engine's documented gate semantics, passed through unchanged.)
  Runner refusals print ``refused: ...`` to stderr and never leak a
  Python traceback.

JSON output contract
--------------------
Subcommands that print a JSON summary (assess, challenge, graph, and
gaps with ``--output``) always include ``aee_exit_code`` and ``ok``.
Output paths are named only when the file was actually written during
the invocation; otherwise the field is ``null`` — the runner never
emits a path to a file that does not exist.

Timeout contract (RT3-11)
-------------------------
Every engine subprocess runs under a timeout (``--timeout``, default
600 seconds; the version/help capability probes are bounded by
``min(30, --timeout)`` so a hung engine cannot stall them either).
On expiry the runner kills the child and returns exit 2 —
never a scored verdict. JSON-summary subcommands print their summary
with ``aee_exit_code: null``, ``timed_out: true``, ``ok: false`` and
no output paths (a timed-out run is refused as a whole, even if the
engine managed a partial write); passthrough subcommands (gate,
verify, review, gaps without ``--output``) print
``refused: ... timed out ...`` to stderr.

Latest-assessment pointer (RT3-13)
----------------------------------
A successful ``assess`` also maintains
``.specify/extensions/aee/assessments/latest-<phase>.json``, a plain
JSON pointer naming the assessment it just wrote. ``gate --latest
<phase>`` resolves that pointer (refusing when none exists) and notes
the assessment's age on stderr, so gating a stale assessment is a
visible act rather than an ambiguous path resolution.

Version contract
----------------
At startup the runner runs ``aee --version`` and refuses (exit 2) when
the installed engine is outside ``REQUIRED_AEE_VERSION``, naming both
the found and required versions. The range mirrors ``extension.yml``
(``requires.tools`` entry ``aee``); keep the two in sync.

Evaluator extension (required companion, Spec 005)
--------------------------------------------------
AEE is one evaluator among many by design: the result ``assess``
produces is written for the common evaluator, and composing it with
other evaluators' results through the spec-kit-evaluator extension is
part of the standard flow, so every evaluator's output is handled the
same way. The pair is one system — ``extension.yml`` declares
``spec-kit-evaluator`` required, and ``assess`` enforces it: when
``.specify/extensions/evaluator/`` is absent from the project,
``assess`` refuses (exit 2, naming the missing extension and the
install command) before the engine runs or any output is written.
Presence is still sampled before outputs are created (RT3-04) and is
reported as ``evaluator_extension_present`` in the assess JSON. The
other subcommands emit no Evaluator Contract results and are not
blocked; ``gate`` works on AEE's own assessments.

Extension version stamp (FR-4.2) and ledger verdict (FR-8.2)
------------------------------------------------------------
The engine CLI has no metadata-injection channel, so the runner
cannot ask it to record ``metadata.extension_version``. The runner
therefore stamps the assessment itself — and does so BEFORE
ledgering, never after: ``assess`` invokes the engine with
``--no-ledger`` (capability-probed: engines that ledger only on an
explicit ``--ledger`` — the released 1.4.0 CLI — never ledger here
anyway), stamps ``extension_version`` (and the truthful
``metadata.ledger`` record for the runner-chosen path) into the
assessment file, then appends THAT stamped assessment to the ledger
with the engine's own ``aee.ledger.HashChainLedger`` and verifies the
chain, reporting the verdict as ``ledger_verification`` in the JSON
summary. The ledger entry's SHA-256 therefore covers exactly the
assessment file the runner names; a post-ledger stamp would falsify
that record and is never applied. Assessments produced by the bare
CLI carry no ``extension_version`` key — the runner does not
fabricate one for runs it did not produce. With ``--no-ledger`` the
runner stamps the file only (its ``metadata.ledger`` echo stays the
engine's "disabled" record) and reports ``ledger_verification`` as
``null`` — no verdict is invented for a ledgering that did not happen.
Because the stamp/append step uses the engine's Python package, the
runner requires ``aee`` to be importable by its own interpreter (the
normal pip install provides the CLI and the package together); if it
is not importable, ``assess`` refuses cleanly (exit 2) before the
engine runs.

Drafting (FR-2 / FR-6.3)
------------------------
``draft-claims`` invokes the engine's drafting helper
(``aee.extract.draft_claims_from_spec``) — the engine CLI exposes no
drafting subcommand — and writes its output verbatim as a claims
bundle. The runner contains no code path that ratifies, supports, or
upgrades a drafted claim (FR-2.2): drafts are born ``status: draft``
with ``asserted``/``model`` evidence, TODO falsifiers pass through
untouched so strict loading rejects unfinished drafts downstream,
and ``depends_on`` proposals scaffolded from explicit spec
cross-references are surfaced in the JSON summary as proposals.
Drafting requires an engine build whose ``aee.extract`` provides the
helper (engine builds after 1.4.0); an older importable engine makes
``draft-claims`` refuse cleanly (exit 2), naming the missing helper.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

DEFAULT_TIMEOUT_SECONDS = 600.0

# Mirrors extension.yml requires.tools[aee]. Keep in sync.
REQUIRED_AEE_VERSION = ">=1.5.0,<2"
_AEE_VERSION_MIN = (1, 5, 0)
_AEE_VERSION_MAX = (2, 0, 0)  # exclusive
_VERSION_PATTERN = re.compile(r"(\d+)\.(\d+)\.(\d+)")


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument("--project-root", type=Path, default=Path.cwd())
    root.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help="seconds before an engine subprocess is killed and the "
        "run refused with exit 2 (default: %(default)s)",
    )
    sub = root.add_subparsers(dest="command", required=True)

    assess = sub.add_parser("assess")
    assess.add_argument("--input", type=Path, required=True)
    assess.add_argument("--phase", default="after_plan")
    assess.add_argument("--threshold", type=float, default=0.70)
    assess.add_argument("--project")
    assess.add_argument("--actor", default="spec-kit-aee")
    assess.add_argument("--no-ledger", action="store_true")
    assess.add_argument("--policy", action="store_true")
    assess.add_argument("--min-independent-sources", type=int, default=2)
    assess.add_argument("--contested-threshold", type=float, default=0.25)
    assess.add_argument("--reliability", type=Path)
    assess.add_argument("--reliability-alpha", type=float, default=0.5)

    challenge = sub.add_parser("challenge")
    challenge.add_argument("--input", type=Path, required=True)
    challenge.add_argument("--phase", default="after_plan")
    challenge.add_argument("--threshold", type=float, default=0.70)
    challenge.add_argument("--project")
    challenge.add_argument("--actor", default="spec-kit-aee")

    graph = sub.add_parser("graph")
    graph.add_argument("--input", type=Path, required=True)

    verify = sub.add_parser("verify")
    verify.add_argument("--ledger", type=Path)

    gate = sub.add_parser("gate")
    gate_source = gate.add_mutually_exclusive_group(required=True)
    gate_source.add_argument("--input", type=Path)
    gate_source.add_argument(
        "--latest",
        metavar="PHASE",
        help="gate the assessment named by the latest-<phase> pointer "
        "maintained by assess, instead of an explicit --input path",
    )

    gaps = sub.add_parser("gaps")
    gaps.add_argument("--matrix", type=Path, required=True)
    gaps.add_argument("--evidence", type=Path, required=True)
    gaps.add_argument("--output", type=Path)
    gaps.add_argument("--close")
    gaps.add_argument("--existing", type=Path)

    review = sub.add_parser("review")
    review.add_argument("--previous", type=Path, required=True)
    review.add_argument("--current", type=Path, required=True)
    review.add_argument("--materiality", type=float, default=0.05)
    review.add_argument("--limit", type=int)

    draft = sub.add_parser("draft-claims")
    draft.add_argument("--spec", type=Path, required=True)
    draft.add_argument("--output", type=Path)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        root = args.project_root.resolve(strict=True)
        _reject_symlink_chain(root, root)
        executable = shutil.which("aee")
        if executable is None:
            print(
                "refused: missing required 'aee' command. Install "
                f"applied-epistemic-engineering{REQUIRED_AEE_VERSION}.",
                file=sys.stderr,
            )
            return 2
        _check_aee_version(executable, timeout=min(30.0, args.timeout))
        if args.command == "assess":
            return _assess(executable, root, args)
        if args.command == "challenge":
            return _challenge(executable, root, args)
        if args.command == "graph":
            return _graph(executable, root, args)
        if args.command == "verify":
            return _verify(executable, root, args)
        if args.command == "gate":
            return _gate(executable, root, args)
        if args.command == "gaps":
            return _gaps(executable, root, args)
        if args.command == "review":
            return _review(executable, root, args)
        if args.command == "draft-claims":
            return _draft_claims(root, args)
        raise AssertionError("unreachable")
    except (ValueError, TypeError, OSError) as exc:
        # Runner refusals and OS-level failures are errors (exit 2),
        # never scored verdicts, and never surface as tracebacks.
        print(f"refused: {exc}", file=sys.stderr)
        return 2


def _parse_aee_version(text: str) -> tuple[int, int, int] | None:
    match = _VERSION_PATTERN.search(text)
    if match is None:
        return None
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)))


def _aee_version_satisfies(version: tuple[int, int, int]) -> bool:
    return _AEE_VERSION_MIN <= version < _AEE_VERSION_MAX


def _check_aee_version(executable: str, timeout: float = 30.0) -> None:
    """Refuse to run against an engine outside the declared range."""
    try:
        completed = subprocess.run(
            [executable, "--version"],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValueError(
            f"could not run 'aee --version' to verify the engine version "
            f"(required {REQUIRED_AEE_VERSION}): {exc}"
        ) from exc
    version = _parse_aee_version(f"{completed.stdout}\n{completed.stderr}")
    if completed.returncode != 0 or version is None:
        raise ValueError(
            "could not determine the installed aee version from "
            f"'aee --version' (required {REQUIRED_AEE_VERSION}); "
            "reinstall applied-epistemic-engineering"
            f"{REQUIRED_AEE_VERSION}."
        )
    if not _aee_version_satisfies(version):
        found = ".".join(str(part) for part in version)
        raise ValueError(
            f"aee version {found} does not satisfy the required range "
            f"{REQUIRED_AEE_VERSION} declared in extension.yml; install "
            f"applied-epistemic-engineering{REQUIRED_AEE_VERSION}."
        )


class _EngineTimeout(ValueError):
    """An engine subprocess exceeded its timeout and was killed.

    A ValueError subclass so the passthrough subcommands surface it
    through main()'s clean-refusal path (exit 2, no traceback); the
    JSON-summary subcommands catch it themselves to print their
    timed-out summary shape (RT3-11).
    """

    def __init__(self, timeout: float) -> None:
        super().__init__(
            f"aee subprocess timed out after {timeout:g} seconds and "
            "was killed; re-run with a larger --timeout if the engine "
            "was making progress"
        )
        self.timeout = timeout


def _run_engine(
    command: list[str], timeout: float, **kwargs: object
) -> subprocess.CompletedProcess:
    """Run the engine under a hard timeout (RT3-11).

    subprocess.run kills the child before raising TimeoutExpired, so
    converting it here is enough — no engine process is left running.
    """
    try:
        return subprocess.run(command, timeout=timeout, check=False, **kwargs)
    except subprocess.TimeoutExpired as exc:
        raise _EngineTimeout(timeout) from exc
    except OSError as exc:
        raise ValueError(f"could not run the aee engine: {exc}") from exc


def _unique_stamp() -> str:
    """Collision-proof filename stamp (RT3-08).

    Second-resolution stamps let two distinct runs in the same second
    share one filename — the ledger then attested content the disk no
    longer held. The stamp keeps the sortable UTC second prefix and
    adds microseconds plus a random component, so distinct runs never
    collide even within one microsecond.
    """
    now = datetime.now(UTC)
    return now.strftime("%Y%m%dT%H%M%S") + f"{now.microsecond:06d}-{secrets.token_hex(3)}Z"


def _extension_version() -> str | None:
    """This extension's version, read from its own extension.yml.

    The runner lives at scripts/python/run_aee.py inside the installed
    extension, so the manifest is two levels up. The manifest is
    parsed with a narrow pattern (the runner is dependency-free and
    does not load YAML). Returns None when the version cannot be
    determined — callers then stamp nothing rather than fabricating.
    """
    manifest = Path(__file__).resolve().parents[2] / "extension.yml"
    try:
        text = manifest.read_text(encoding="utf-8")
    except OSError:
        return None
    match = re.search(r"(?m)^extension:\s*\n(?:.*\n)*?  version:\s*'?(\d+\.\d+\.\d+)", text)
    if match is None:
        match = re.search(r"(?m)^  version:\s*'?(\d+\.\d+\.\d+)", text)
    return match.group(1) if match else None


class _AssessmentView:
    """Minimal to_dict() shim so the engine ledger can hash a dict."""

    def __init__(self, value: dict) -> None:
        self._value = value

    def to_dict(self) -> dict:
        return self._value


def _load_hash_chain_ledger() -> object:
    """Import the engine's HashChainLedger class or refuse cleanly."""
    try:
        from aee.ledger import HashChainLedger
    except ImportError as exc:
        raise ValueError(
            "the aee engine package is not importable by this Python "
            "interpreter; the runner stamps and ledgers assessments "
            "through aee.ledger (the pip install of "
            "applied-epistemic-engineering provides the CLI and the "
            f"package together): {exc}"
        ) from exc
    return HashChainLedger


def _draft_claims(root: Path, args: argparse.Namespace) -> int:
    candidate = args.spec if args.spec.is_absolute() else root / args.spec
    if candidate.is_dir():
        spec_file = _safe_existing(root, args.spec / "spec.md")
        spec_dir = spec_file.parent
    else:
        spec_file = _safe_existing(root, args.spec)
        spec_dir = spec_file.parent
    if args.output:
        output = _safe_output(root, args.output)
    else:
        output = _safe_output(root, spec_dir.relative_to(root) / "aee-claims.json")
    if output.resolve(strict=False) == spec_file.resolve(strict=False):
        raise ValueError("draft output must not overwrite the source spec")
    try:
        from aee.extract import TODO_FALSIFIER, draft_claims_from_spec, dump_claims
    except ImportError as exc:
        raise ValueError(
            "draft-claims requires the engine drafting helper "
            "aee.extract.draft_claims_from_spec, which this Python "
            "interpreter cannot import; drafting ships in engine builds "
            "after 1.4.0 — install a current "
            f"applied-epistemic-engineering{REQUIRED_AEE_VERSION} build: {exc}"
        ) from exc
    spec_text = spec_file.read_text(encoding="utf-8")
    source_name = spec_file.relative_to(root).as_posix()
    claims = draft_claims_from_spec(spec_text, source_name=source_name)
    if not claims:
        raise ValueError(
            f"no requirements found in {source_name}; nothing to draft "
            "(the helper recognises FR-/US- references, user-story "
            "headings, and acceptance-criteria bullets)"
        )
    # The helper's output is written verbatim: the runner never edits
    # a draft's status, evidence, falsifiers, or dependencies (FR-2.2).
    bundle_text = dump_claims(claims)
    bundle = json.loads(bundle_text)
    drafted = bundle.get("claims", [])
    before = _snapshot(output)
    output.write_text(
        bundle_text if bundle_text.endswith("\n") else bundle_text + "\n",
        encoding="utf-8",
    )
    todo_count = sum(
        1
        for claim in drafted
        if any(
            TODO_FALSIFIER in str(test)
            for test in claim.get("falsification_tests", [])
        )
    )
    proposals = [
        {
            "claim_id": claim.get("id"),
            "depends_on": claim.get("depends_on", []),
            "proposed_from": claim.get("metadata", {}).get(
                "depends_on_proposed_from", []
            ),
        }
        for claim in drafted
        if claim.get("depends_on")
    ]
    print(
        json.dumps(
            {
                "draft_claims": _rel_or_none(root, output, before),
                "spec": source_name,
                "claim_count": len(drafted),
                "todo_falsifier_count": todo_count,
                "depends_on_proposals": proposals,
                "aee_exit_code": 0,
                "ok": True,
            },
            indent=2,
        )
    )
    return 0


def _stamp_and_ledger(
    assessment: Path,
    ledger: Path | None,
    actor: str,
    ledger_class: object | None,
) -> tuple[str | None, dict | None]:
    """Stamp extension_version, then (optionally) ledger + verify.

    The stamp is applied to the assessment dict BEFORE the ledger
    append hashes it, so the ledger records exactly the file the
    runner names (FR-4.2 / FR-8.2). Returns (extension_version,
    ledger_verification) — both None-valued honestly when absent.
    """
    try:
        value = json.loads(assessment.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"could not stamp the assessment {assessment}: {exc}") from exc
    if not isinstance(value, dict):
        raise TypeError(f"assessment {assessment} is not a JSON object; cannot stamp it")
    metadata = value.setdefault("metadata", {})
    version = _extension_version()
    if version is not None:
        metadata["extension_version"] = version
    if ledger is not None:
        metadata["ledger"] = {"mode": "custom", "path": ledger.as_posix()}
    assessment.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    verification: dict | None = None
    if ledger is not None:
        assert ledger_class is not None
        chain = ledger_class(ledger)  # type: ignore[operator]
        try:
            chain.append_assessment(_AssessmentView(value), actor=actor)
            result = chain.verify()
        except (ValueError, KeyError, TypeError, OSError) as exc:
            raise ValueError(
                f"could not append/verify the assessment in ledger {ledger}: {exc}"
            ) from exc
        verification = {
            "valid": result.valid,
            "entries": result.entries,
            "head_hash": result.head_hash,
            "errors": list(result.errors),
        }
    return version, verification


_NO_LEDGER_SUPPORT: dict[str, bool] = {}


def _assess_supports_no_ledger(executable: str, timeout: float = 30.0) -> bool:
    """True when `aee assess --help` advertises --no-ledger.

    Capability-probed (cached per executable) instead of assumed from
    the version: engines that ledger by default need the opt-out,
    engines that ledger only on --ledger reject the unknown flag.
    A failed probe means "not advertised" — the safe default.
    """
    if executable not in _NO_LEDGER_SUPPORT:
        try:
            completed = subprocess.run(
                [executable, "assess", "--help"],
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
            _NO_LEDGER_SUPPORT[executable] = "--no-ledger" in completed.stdout
        except (OSError, subprocess.SubprocessError):
            _NO_LEDGER_SUPPORT[executable] = False
    return _NO_LEDGER_SUPPORT[executable]


_LENIENT_SUPPORT: dict[tuple[str, str], bool] = {}


def _supports_lenient(executable: str, subcommand: str, timeout: float = 30.0) -> bool:
    """True when `aee <subcommand> --help` advertises --lenient.

    The runner drives the engine's recorded compatibility mode
    (Spec 002 FR-1.3) for project claim bundles: bundles written
    before the Spec 004 stage vocabulary lack the `stage` field,
    and strict loading refuses them outright. Lenient loading
    defaults the stage to `created` ON THE RECORD (the assessment
    metadata carries `loading_mode` and `stage_defaults`), so the
    transition stays honest instead of becoming a hard refusal of
    every pre-realignment project. Capability-probed per
    subcommand, like --no-ledger: engines without the flag (the
    released 1.4.0 `challenge` has none) are invoked without it.
    """
    key = (executable, subcommand)
    if key not in _LENIENT_SUPPORT:
        try:
            completed = subprocess.run(
                [executable, subcommand, "--help"],
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
            _LENIENT_SUPPORT[key] = "--lenient" in completed.stdout
        except (OSError, subprocess.SubprocessError):
            _LENIENT_SUPPORT[key] = False
    return _LENIENT_SUPPORT[key]


def _snapshot(path: Path) -> tuple[int, int] | None:
    """(size, mtime_ns) for an existing file, else None."""
    try:
        stat = path.stat()
    except OSError:
        return None
    return (stat.st_size, stat.st_mtime_ns)


def _written(path: Path, before: tuple[int, int] | None) -> bool:
    """True when the file exists now and was (re)written since `before`."""
    after = _snapshot(path)
    return after is not None and after != before


def _rel_or_none(root: Path, path: Path, before: tuple[int, int] | None) -> str | None:
    """Project-relative path when the file was written, else None.

    The runner only ever names files the engine actually wrote during
    this invocation; a pre-existing or never-created file is reported
    as null instead of a phantom path.
    """
    if not _written(path, before):
        return None
    return path.relative_to(root).as_posix()


def _gate(executable: str, root: Path, args: argparse.Namespace) -> int:
    if args.latest is not None:
        value = _resolve_latest(root, args.latest)
    else:
        value = _safe_existing(root, args.input)
    return _run_engine([executable, "gate", "--input", str(value)], args.timeout).returncode


def _resolve_latest(root: Path, phase_arg: str) -> Path:
    """Resolve the latest-<phase> pointer written by assess (RT3-13).

    Refuses (ValueError -> exit 2) when no pointer exists for the
    phase, when the pointer is malformed, or when the assessment it
    names is gone; the resolved assessment's age is noted on stderr
    so a stale gate is visible to the operator.
    """
    phase = _safe_segment(phase_arg)
    pointer = _safe_existing(
        root, Path(f".specify/extensions/aee/assessments/latest-{phase}.json")
    )
    try:
        record = json.loads(pointer.read_text(encoding="utf-8"))
        target_rel = record["assessment"]
        written_at = record.get("written_at", "unknown time")
    except (ValueError, KeyError, TypeError) as exc:
        raise ValueError(f"latest pointer {pointer} is malformed: {exc}") from exc
    target = _safe_existing(root, Path(str(target_rel)))
    age_note = ""
    try:
        written = datetime.fromisoformat(str(written_at).replace("Z", "+00:00"))
        age = datetime.now(UTC) - written
        age_note = f", age {int(age.total_seconds())}s"
    except ValueError:
        pass
    print(
        f"note: --latest {phase} resolved to {target.relative_to(root).as_posix()} "
        f"(written {written_at}{age_note})",
        file=sys.stderr,
    )
    return target


def _review(executable: str, root: Path, args: argparse.Namespace) -> int:
    previous = _safe_existing(root, args.previous)
    current = _safe_existing(root, args.current)
    command = [
        executable,
        "review",
        "--previous",
        str(previous),
        "--current",
        str(current),
        "--materiality",
        str(args.materiality),
    ]
    if args.limit is not None:
        command.extend(["--limit", str(args.limit)])
    return _run_engine(command, args.timeout).returncode


def _check_evidence_tree(root: Path, evidence: Path) -> None:
    """Refuse symlinked or out-of-root evidence contents (RT3-05).

    _safe_dir validates the evidence directory chain itself, but the
    engine discovers evidence by walking the tree and following file
    symlinks — a symlinked file inside a valid directory smuggled
    out-of-root data into the gap register. This pre-flight walks the
    whole tree before the engine runs and refuses any symlink and any
    entry resolving outside the project root, naming the offenders.
    """
    offenders: list[str] = []
    for dirpath, dirnames, filenames in os.walk(evidence, followlinks=False):
        for name in (*dirnames, *filenames):
            entry = Path(dirpath) / name
            shown = entry.relative_to(root).as_posix()
            if entry.is_symlink():
                offenders.append(f"{shown} (symlink)")
                continue
            try:
                entry.resolve(strict=True).relative_to(root)
            except (OSError, ValueError):
                offenders.append(f"{shown} (escapes project root)")
    if offenders:
        raise ValueError(
            "evidence tree contains entries the runner refuses to let "
            "the engine read: " + "; ".join(sorted(offenders))
        )


def _gaps(executable: str, root: Path, args: argparse.Namespace) -> int:
    matrix = _safe_existing(root, args.matrix)
    evidence = _safe_dir(root, args.evidence)
    _check_evidence_tree(root, evidence)
    command = [
        executable,
        "gaps",
        "--matrix",
        str(matrix),
        "--evidence",
        str(evidence),
    ]
    if args.close:
        command.extend(["--close", args.close])
    if args.existing:
        existing = _safe_existing(root, args.existing)
        command.extend(["--existing", str(existing)])
    output: Path | None = None
    before: tuple[int, int] | None = None
    if args.output:
        if args.close:
            # In --close mode the engine updates an existing register;
            # refuse a mistyped target here instead of surfacing an
            # engine error for a file that was never a register.
            _safe_existing(root, args.output)
        output = _safe_output(root, args.output)
        before = _snapshot(output)
        command.extend(["--output", str(output)])
    if output is None:
        return _run_engine(command, args.timeout).returncode
    # With --output the engine's stdout chatter goes to stderr so the
    # runner's stdout stays a single machine-parseable JSON document.
    try:
        completed = _run_engine(
            command, args.timeout, capture_output=True, text=True
        )
    except _EngineTimeout as exc:
        print(f"refused: {exc}", file=sys.stderr)
        print(
            json.dumps(
                {
                    "gaps": None,
                    "aee_exit_code": None,
                    "timed_out": True,
                    "ok": False,
                },
                indent=2,
            )
        )
        return 2
    if completed.stdout:
        print(completed.stdout, file=sys.stderr, end="")
    if completed.stderr:
        print(completed.stderr, file=sys.stderr, end="")
    gaps_rel = _rel_or_none(root, output, before)
    print(
        json.dumps(
            {
                "gaps": gaps_rel,
                "aee_exit_code": completed.returncode,
                "timed_out": False,
                "ok": completed.returncode == 0 and gaps_rel is not None,
            },
            indent=2,
        )
    )
    return completed.returncode


def _assess(executable: str, root: Path, args: argparse.Namespace) -> int:
    source = _safe_existing(root, args.input)
    # Sample evaluator-extension presence BEFORE creating outputs: the
    # runner itself creates .specify/extensions/evaluator/results/ for
    # the engine-produced contract result, so checking afterwards
    # would always report a phantom installation (RT3-04).
    evaluator_extension_present = (
        root / ".specify" / "extensions" / "evaluator"
    ).is_dir()
    if not evaluator_extension_present:
        # Spec 005 (ER-01): the evaluator extension is a required
        # companion, not an optional extra. Refuse here — after the
        # presence sample, before any output path is created and
        # before the engine runs — so a refused assess writes nothing.
        raise ValueError(
            "the spec-kit-evaluator extension is required for assess "
            "but is not installed in this project "
            "(.specify/extensions/evaluator/ not found). AEE is one "
            "evaluator among many by design: the result assess "
            "produces is written for the common evaluator, and "
            "composing it with other evaluators' results through "
            "that extension is part of the standard flow, so every "
            "evaluator's output is handled the same way. Install the "
            "pair together: specify extension add spec-kit-evaluator "
            "(see the Spec Kit catalog or this extension's README), "
            "then re-run assess."
        )
    stamp = _unique_stamp()
    phase = _safe_segment(args.phase)
    assessment = _safe_output(
        root, Path(f".specify/extensions/aee/assessments/aee-{phase}-{stamp}.json")
    )
    evaluator = _safe_output(
        root, Path(f".specify/extensions/evaluator/results/aee-{phase}-{stamp}.json")
    )
    command = [
        executable,
        "assess",
        "--input",
        str(source),
        "--project",
        args.project or root.name,
        "--phase",
        phase,
        "--threshold",
        str(args.threshold),
        "--output",
        str(assessment),
        "--evaluator-output",
        str(evaluator),
        "--artifact",
        source.relative_to(root).as_posix(),
        "--actor",
        args.actor,
    ]
    if _supports_lenient(executable, "assess", timeout=min(30.0, args.timeout)):
        command.append("--lenient")
    if args.policy:
        command.extend([
            "--policy",
            "--min-independent-sources",
            str(args.min_independent_sources),
            "--contested-threshold",
            str(args.contested_threshold),
        ])
    if args.reliability:
        table = _safe_existing(root, args.reliability)
        command.extend([
            "--reliability",
            str(table),
            "--reliability-alpha",
            str(args.reliability_alpha),
        ])
    ledger: Path | None = None
    ledger_class: object | None = None
    if not args.no_ledger:
        ledger = _safe_output(
            root, Path(".specify/extensions/aee/ledger/epistemic-ledger.jsonl")
        )
        # The runner ledgers the STAMPED assessment itself (see the
        # module docstring): the engine is told --no-ledger so its own
        # append cannot record an unstamped hash, and _load failures
        # refuse here, before the engine runs.
        ledger_class = _load_hash_chain_ledger()
    # The runner disables engine-side ledgering so its own append can
    # record the STAMPED assessment: with ledgering requested, the
    # runner appends after stamping; without it, the engine's
    # disabled-ledger echo is the truth. --no-ledger exists only on
    # engines that ledger by default (post-1.4.0); the released 1.4.0
    # CLI ledgers only on an explicit --ledger, so the flag is passed
    # only when the installed CLI advertises it.
    if _assess_supports_no_ledger(executable, timeout=min(30.0, args.timeout)):
        command.append("--no-ledger")
    before = {
        "assessment": _snapshot(assessment),
        "evaluator": _snapshot(evaluator),
        "ledger": _snapshot(ledger) if ledger else None,
    }
    # The Evaluator Contract result named below is produced by the
    # engine itself (--evaluator-output); composing it with other
    # evaluators' results is the spec-kit-evaluator extension's work,
    # whose presence the pre-flight above has already enforced. The
    # JSON still reports evaluator_extension_present so consumers can
    # see the pair is installed.
    try:
        completed = _run_engine(command, args.timeout)
        returncode: int | None = completed.returncode
        timed_out = False
    except _EngineTimeout as exc:
        # A timed-out run is refused as a whole (RT3-11): no stamp, no
        # ledger append, no named outputs — even if the engine managed
        # a partial write before it was killed.
        print(f"refused: {exc}", file=sys.stderr)
        returncode = None
        timed_out = True
    assessment_rel = (
        None if timed_out else _rel_or_none(root, assessment, before["assessment"])
    )
    extension_version: str | None = None
    ledger_verification: dict | None = None
    latest_rel: str | None = None
    verdict_display: dict | None = None
    if assessment_rel is not None:
        extension_version, ledger_verification = _stamp_and_ledger(
            assessment, ledger, args.actor, ledger_class
        )
        latest_rel = _write_latest_pointer(root, phase, assessment_rel)
        verdict_display = _verdict_display(assessment)
    print(
        json.dumps(
            {
                "assessment": assessment_rel,
                "verdict_display": verdict_display,
                "evaluator_result": (
                    None
                    if timed_out
                    else _rel_or_none(root, evaluator, before["evaluator"])
                ),
                "evaluator_extension_present": evaluator_extension_present,
                "extension_version": extension_version,
                "ledger": (
                    _rel_or_none(root, ledger, before["ledger"])
                    if ledger and not timed_out
                    else None
                ),
                "ledger_verification": ledger_verification,
                "latest_pointer": latest_rel,
                "aee_exit_code": returncode,
                "timed_out": timed_out,
                "ok": returncode in (0, 1),
            },
            indent=2,
        )
    )
    return 2 if timed_out else returncode


def _verdict_display(assessment_path: Path) -> dict | None:
    """The realigned verdict display (Spec 004 P5-E2): the stamped
    assessment's own verdict vocabulary, copied for the runner's
    JSON so a consumer of the runner sees exactly what the bare CLI
    reports on the same bundle - the stage-capped
    `reported_statuses`, the `stage_caps` records, the lane pair
    (lane 1 machine verification, lane 2 human acceptance), and the
    `not_understood` residual-unknowns statement that must render
    with every verdict (R5.3/R6.3). The runner computes nothing
    here: every value is the engine's. A record lacking the fields
    (pre-realignment) yields None, never fabricated values.
    """
    try:
        value = json.loads(assessment_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(value, dict) or "reported_statuses" not in value:
        return None
    lanes = value.get("lanes") if isinstance(value.get("lanes"), dict) else {}
    return {
        "outcome": value.get("outcome"),
        "methodology_version": value.get("methodology_version"),
        "reported_statuses": value.get("reported_statuses"),
        "stage_caps": value.get("stage_caps"),
        "lanes": {
            "lane_1": lanes.get("lane_1"),
            "lane_2": lanes.get("lane_2"),
        },
        "not_understood": value.get("not_understood"),
    }


def _write_latest_pointer(root: Path, phase: str, assessment_rel: str) -> str:
    """Maintain the latest-<phase> assessment pointer (RT3-13).

    A plain JSON file (never a symlink) naming the assessment the most
    recent successful assess for the phase wrote; `gate --latest`
    resolves it. Written only after the assessment is stamped and
    ledgered, so the pointer never names an unfinished record.
    """
    pointer = _safe_output(
        root, Path(f".specify/extensions/aee/assessments/latest-{phase}.json")
    )
    pointer.write_text(
        json.dumps(
            {
                "assessment": assessment_rel,
                "phase": phase,
                "written_at": datetime.now(UTC).isoformat(timespec="seconds"),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return pointer.relative_to(root).as_posix()


def _challenge(executable: str, root: Path, args: argparse.Namespace) -> int:
    source = _safe_existing(root, args.input)
    stamp = _unique_stamp()
    phase = _safe_segment(args.phase)
    output = _safe_output(
        root, Path(f".specify/extensions/aee/challenges/aee-{phase}-{stamp}.json")
    )
    command = [
        executable,
        "challenge",
        "--input",
        str(source),
        "--project",
        args.project or root.name,
        "--phase",
        phase,
        "--threshold",
        str(args.threshold),
        "--output",
        str(output),
        "--actor",
        args.actor,
    ]
    if _supports_lenient(executable, "challenge", timeout=min(30.0, args.timeout)):
        command.append("--lenient")
    before = _snapshot(output)
    try:
        completed = _run_engine(command, args.timeout)
        returncode: int | None = completed.returncode
        timed_out = False
    except _EngineTimeout as exc:
        print(f"refused: {exc}", file=sys.stderr)
        returncode = None
        timed_out = True
    print(
        json.dumps(
            {
                "challenge": (
                    None if timed_out else _rel_or_none(root, output, before)
                ),
                "aee_exit_code": returncode,
                "timed_out": timed_out,
                "ok": returncode in (0, 1),
            },
            indent=2,
        )
    )
    return 2 if timed_out else returncode


def _graph(executable: str, root: Path, args: argparse.Namespace) -> int:
    source = _safe_existing(root, args.input)
    stamp = _unique_stamp()
    output = _safe_output(
        root, Path(f".specify/extensions/aee/graphs/aee-claims-{stamp}.mmd")
    )
    before = _snapshot(output)
    graph_command = [executable, "graph", "--input", str(source), "--output", str(output)]
    if _supports_lenient(executable, "graph", timeout=min(30.0, args.timeout)):
        graph_command.append("--lenient")
    try:
        completed = _run_engine(
            graph_command,
            args.timeout,
        )
        returncode: int | None = completed.returncode
        timed_out = False
    except _EngineTimeout as exc:
        print(f"refused: {exc}", file=sys.stderr)
        returncode = None
        timed_out = True
    graph_rel = None if timed_out else _rel_or_none(root, output, before)
    print(
        json.dumps(
            {
                "graph": graph_rel,
                "aee_exit_code": returncode,
                "timed_out": timed_out,
                "ok": returncode == 0 and graph_rel is not None,
            },
            indent=2,
        )
    )
    return 2 if timed_out else returncode


def _verify(executable: str, root: Path, args: argparse.Namespace) -> int:
    ledger_arg = args.ledger or Path(
        ".specify/extensions/aee/ledger/epistemic-ledger.jsonl"
    )
    ledger = _safe_existing(root, ledger_arg)
    return _run_engine(
        [executable, "verify-ledger", "--ledger", str(ledger)], args.timeout
    ).returncode


def _safe_existing(root: Path, value: Path) -> Path:
    candidate = value if value.is_absolute() else root / value
    _reject_symlink_chain(root, candidate)
    resolved = candidate.resolve(strict=True)
    _require_inside(root, resolved)
    if not resolved.is_file():
        raise ValueError(f"not a regular file: {value}")
    return resolved


def _safe_dir(root: Path, value: Path) -> Path:
    candidate = value if value.is_absolute() else root / value
    _reject_symlink_chain(root, candidate)
    resolved = candidate.resolve(strict=True)
    _require_inside(root, resolved)
    if not resolved.is_dir():
        raise ValueError(f"not a directory: {value}")
    return resolved


def _safe_output(root: Path, value: Path) -> Path:
    candidate = value if value.is_absolute() else root / value
    _require_inside(root, candidate.resolve(strict=False))
    _reject_symlink_chain(root, candidate)
    candidate.parent.mkdir(parents=True, exist_ok=True)
    _reject_symlink_chain(root, candidate)
    # Return the RESOLVED path (RT3-17): callers hand this path to the
    # engine for a later write, and returning the unresolved candidate
    # left a check-then-use window between this validation and that
    # write.
    return candidate.resolve(strict=False)


def _require_inside(root: Path, candidate: Path) -> None:
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"path escapes project root: {candidate}") from exc


def _reject_symlink_chain(root: Path, candidate: Path) -> None:
    absolute = candidate if candidate.is_absolute() else root / candidate
    _require_inside(root, absolute.resolve(strict=False))
    current = root
    try:
        parts = absolute.relative_to(root).parts
    except ValueError as exc:
        raise ValueError(f"path escapes project root: {absolute}") from exc
    for part in parts:
        current = current / part
        if current.exists() and current.is_symlink():
            raise ValueError(f"symlinked path component refused: {current}")


def _safe_segment(value: str) -> str:
    if not value or any(
        char not in "abcdefghijklmnopqrstuvwxyz0123456789_" for char in value
    ):
        raise ValueError(f"invalid phase: {value!r}")
    normalized = value if value.startswith("after_") else f"after_{value}"
    if normalized == "after_":
        # A bare "after_" names no lifecycle phase; the engine would
        # reject it later with a less clear error.
        raise ValueError(f"invalid phase: {value!r}")
    return normalized


if __name__ == "__main__":
    sys.exit(main())
