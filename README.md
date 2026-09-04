# Applied Epistemic Engineering for Spec Kit

`spec-kit-aee` applies evidence-centered claim engineering to Spec-Driven Development. It turns explicit requirements, assumptions, hypotheses, decisions, and compliance claims into a challengeable claim graph; distinguishes observations from assertions; preserves contradictions; propagates weakest-link uncertainty; proposes bounded recovery work; and emits results that conform to ElectroHire's [Evaluator Contract](https://github.com/electrohire/spec-kit-evaluator).

This is the Spec Kit successor to the standalone AEE component first explored in SpecSmith. The implementation is a new ElectroHire design split into two deliberate layers:

- [`applied-epistemic-engineering`](https://github.com/electrohire/applied-epistemic-engineering) owns the Python model, deterministic engine, CLI, and ledger.
- `spec-kit-aee` is the thin lifecycle adapter, command surface, hooks, and evaluator-result integration.

## What it does

1. Extracts only explicitly identified claims; ordinary prose is never silently promoted into evidence.
2. Challenges claim atomicity, observability, boundaries, falsifiability, dependencies, contradictions, and evidence independence.
3. Scores evidence using published weights and caps dependent confidence at the weakest supporting claim.
4. Records recovery actions instead of manufacturing certainty.
5. Writes a rich AEE assessment and a provider-neutral Evaluator Contract result.
6. Optionally appends assessments to a tamper-evident SHA-256 ledger.

AEE is a decision aid. It does **not** prove truth, certify compliance, replace domain review, or make a model's self-attestation into observed evidence.

## Installation

Install the Python engine and the Evaluator Contract first:

```bash
python -m pip install "applied-epistemic-engineering>=1.0.0,<2"
specify extension add evaluator --from https://github.com/electrohire/spec-kit-evaluator/archive/refs/tags/v1.0.0.zip
```

Then install this community extension from its pinned release:

```bash
specify extension add aee --from https://github.com/electrohire/spec-kit-aee/archive/refs/tags/v1.0.0.zip
```

The Spec Kit community catalog is discovery-only. The explicit `--from` URL above makes the install source unambiguous.

For local development:

```bash
specify extension add --dev /path/to/spec-kit-aee
```

## Brief example

Use stable IDs in a specification:

```markdown
## REQ-LATENCY-001 — Search responds within 250 ms

- **Boundary:** Production, p95, 50 requests/second
- **Falsification test:** A 30-minute load test observes p95 above 250 ms
```

Then run:

```text
/speckit.aee.assess phase=after_specify artifact=specs/001-search/spec.md
```

The assessment is stored under `.specify/extensions/aee/assessments/`; the shared result is stored under `.specify/extensions/evaluator/results/`. A claim without inspectable evidence remains unsupported even when generated prose says it passed.

## Commands

| Command | Purpose |
| --- | --- |
| `speckit.aee.assess` | Run the complete deterministic AEE pipeline |
| `speckit.aee.challenge` | Focus on breakpoints and recovery work |
| `speckit.aee.trace` | Render dependencies and review provenance |
| `speckit.aee.verify` | Verify ledger integrity |
| `speckit.aee.gate` | Return CI-friendly exit status from an assessment |

Compose AEE with other evaluators using `/speckit.evaluator.compose`, render it with `/speckit.evaluator.report`, or use `/speckit.evaluator.route` for the next-phase model recommendation. Invocation separators vary by integration; Spec Kit renders the installed command files appropriately.

## Files written

```text
.specify/extensions/aee/
├── assessments/aee-<phase>-<timestamp>.json
├── graphs/aee-claims-<timestamp>.mmd
└── ledger/epistemic-ledger.jsonl

.specify/extensions/evaluator/results/
└── aee-<phase>-<timestamp>.json
```

The command adapter refuses paths outside the project root and refuses symlinked path components. Source artifacts are read-only; only extension-owned output directories are written.

## Development

```bash
python -m pip install pytest pyyaml
pytest -q
```

See [SECURITY.md](SECURITY.md) for the trust boundary and [CHANGELOG.md](CHANGELOG.md) for releases.

## License

MIT © 2026 ElectroHire Inc.
