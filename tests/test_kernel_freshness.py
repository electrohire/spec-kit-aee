"""Kernel freshness: the shipped board kernel definitions must agree
with the canonical kernel in the engine repo.

The kernel (the Agent Board transition table and its guard
definitions) has one canonical machine form: ``board.kernel`` in
electrohire/applied-epistemic-engineering. This extension ships a
copy (``templates/board-kernel-definitions.json``) pinned by hash to
that form, per spec AB-001 Section 4.7: where generation is not yet
built, the shipped definitions are pinned to the canonical form by
hash with a freshness test in this suite, in the style of the
catalog-freshness test. Pinning is the pilot mechanism; generation
replacing pinning is a later task, and nothing here establishes
that it exists.

Two legs, mirroring the catalog test's pinning of surfaces to each
other:

- The pin leg always runs: the shipped file's canonical hash must
  equal PINNED_KERNEL_HASH, the hash of the canonical definitions
  at PINNED_ENGINE_COMMIT.
- The live leg runs whenever an engine checkout is available (the
  sibling checkout beside this repo, ``artifacts/engine`` in CI, or
  $AEE_ENGINE_CHECKOUT): the engine's own ``kernel_definitions()``
  output and ``kernel_definitions_hash()`` are computed in a
  subprocess from that checkout, and the shipped file must match
  both exactly. A hand-copied fixture could drift silently; this
  leg compares against the real engine output.

The canonical form is the engine's pinned rule (board/canonical.py):
JSON with sorted keys, Unicode NFC, separators ``,`` and ``:``,
UTF-8, string values with CRLF / CR line endings normalized to LF.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import sys
import unicodedata
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SHIPPED = ROOT / "templates" / "board-kernel-definitions.json"

# The canonical kernel at the engine commit the shipped definitions
# were generated from. The CI workflow checks the engine out at this
# same commit (artifacts/engine) so the live leg runs there too.
PINNED_ENGINE_COMMIT = "2e36f7ab90ce151a6c0c16adfe182e7095ed1f57"
PINNED_KERNEL_HASH = "ac47b06e700417c7d4155b0dceda20160b191bf6615f32d3ee7f3d93e743e8ce"


def _normalize(value: object) -> object:
    if isinstance(value, str):
        text = unicodedata.normalize("NFC", value)
        return text.replace("\r\n", "\n").replace("\r", "\n")
    if isinstance(value, dict):
        return {_normalize(key): _normalize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]
    return value


def definitions_hash(definitions: object) -> str:
    """SHA-256 of the canonical form, the engine's pinned rule."""
    text = json.dumps(
        _normalize(definitions),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def is_fresh(shipped: object, canonical_hash: str) -> bool:
    return definitions_hash(shipped) == canonical_hash


def _shipped() -> dict:
    return json.loads(SHIPPED.read_text(encoding="utf-8"))


def test_shipped_definitions_match_the_pinned_hash() -> None:
    assert is_fresh(_shipped(), PINNED_KERNEL_HASH), (
        "shipped kernel definitions diverge from the canonical hash "
        f"{PINNED_KERNEL_HASH} pinned at engine commit "
        f"{PINNED_ENGINE_COMMIT}; regenerate the shipped file from "
        "board.kernel.kernel_definitions() and update the pin"
    )


def test_shipped_definitions_shape() -> None:
    shipped = _shipped()
    assert shipped["schema"] == "aee-board-kernel/1"
    assert set(shipped) == {
        "schema",
        "statuses",
        "terminal_statuses",
        "transitions",
        "note_parts",
        "amendable_fields",
        "row_update_change_fields",
        "wait_kinds",
        "execution_states",
    }


def test_freshness_check_rejects_a_perturbed_copy() -> None:
    shipped = _shipped()
    perturbed = copy.deepcopy(shipped)
    perturbed["transitions"][0]["guard"] += " (perturbed)"
    assert not is_fresh(perturbed, PINNED_KERNEL_HASH)
    truncated = copy.deepcopy(shipped)
    del truncated["transitions"][0]
    assert not is_fresh(truncated, PINNED_KERNEL_HASH)


# ---------------------------------------------------------------------------
# Live engine leg: the real kernel_definitions() from an engine checkout.
# ---------------------------------------------------------------------------


def _engine_checkout() -> Path | None:
    candidates = []
    override = os.environ.get("AEE_ENGINE_CHECKOUT")
    if override:
        candidates.append(Path(override))
    candidates.append(
        Path(__file__).resolve().parents[3]
        / "electrohire"
        / "applied-epistemic-engineering"
    )
    candidates.append(ROOT / "artifacts" / "engine")
    for candidate in candidates:
        if (candidate / "board" / "kernel.py").is_file():
            return candidate
    return None


requires_live_engine = pytest.mark.skipif(
    _engine_checkout() is None,
    reason="engine checkout not present beside this repo",
)

_PROBE = """\
import json, sys
sys.path.insert(0, sys.argv[1])
from board import kernel
print(json.dumps({
    "hash": kernel.kernel_definitions_hash(),
    "definitions": kernel.kernel_definitions(),
}))
"""


@requires_live_engine
def test_shipped_definitions_match_the_live_engine() -> None:
    checkout = _engine_checkout()
    assert checkout is not None
    completed = subprocess.run(
        [sys.executable, "-c", _PROBE, str(checkout)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    live = json.loads(completed.stdout)
    assert live["hash"] == PINNED_KERNEL_HASH, (
        "the engine checkout's canonical kernel hash differs from "
        "the pin; the pin belongs to engine commit "
        f"{PINNED_ENGINE_COMMIT} — if the checkout is that commit, "
        "the kernel changed without the shipped definitions moving"
    )
    assert _shipped() == live["definitions"], (
        "shipped kernel definitions diverge from the engine "
        "checkout's kernel_definitions() output"
    )
    assert is_fresh(_shipped(), live["hash"])
