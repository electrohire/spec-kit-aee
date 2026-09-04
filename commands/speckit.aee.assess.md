---
description: "Assess explicit claims and emit AEE and Evaluator Contract results"
---

# AEE Assess

Run the complete Applied Epistemic Engineering pipeline against explicitly identified claims in a JSON or Markdown artifact.

## User input

```text
$ARGUMENTS
```

Accept `artifact=<path>`, `phase=<after_specify|after_plan|after_tasks|after_implement>`, and optional `threshold=<0..1>`. Infer the current phase and its primary artifact when omitted; if ambiguity remains, ask before running.

## Prerequisites

1. Confirm the `aee` command is available and reports version 1.x. If absent, stop and recommend `python -m pip install "applied-epistemic-engineering>=1.0.0,<2"`.
2. Confirm the Evaluator Contract is installed at `.specify/extensions/evaluator/`. If absent, stop and recommend installing `evaluator` before this extension.
3. Resolve the project root and source artifact. Never follow symlinks or read outside the project root.

## Execution

Run:

```bash
python .specify/extensions/aee/scripts/python/run_aee.py assess --input <artifact> --phase <phase> --threshold <threshold>
```

The adapter writes a rich assessment under `.specify/extensions/aee/assessments/`, an Evaluator Contract result under `.specify/extensions/evaluator/results/`, and a chained ledger record under `.specify/extensions/aee/ledger/`.

Report the outcome, confidence threshold, claim/finding counts, unresolved contradictions, recommended recovery, and exact output paths. Do not describe an assessment as proof, certification, or truth.

When other evaluators ran at the same phase, recommend `__SPECKIT_COMMAND_EVALUATOR_COMPOSE__ phase=<phase> strategy=strict`.

## Guardrails

- Assess only claims with stable IDs; do not silently convert free prose into claims.
- Preserve counterevidence and contradictions.
- Model output is `asserted`, never `observed`.
- Do not modify the source artifact during assessment.

