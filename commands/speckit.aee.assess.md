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

Optional: `policy=<true|false>` attaches the engine's policy gates (per-claim ACCEPT / CHALLENGE / ABSTAIN verdicts; tune with `min_independent_sources=<n>` and `contested_threshold=<0..0.75>`), and `reliability=<path>` points at a ReliabilityTable JSON whose measured per-source reliability blends into scoring.

## Prerequisites

1. Confirm the `aee` command is available and reports version >=1.4.0,<2. If absent, stop and recommend `python -m pip install "applied-epistemic-engineering>=1.4.0,<2"`. The runner enforces this itself at startup: it runs `aee --version` and refuses with exit 2, naming the found and required versions, so a below-floor engine cannot silently produce incomparable scores.
2. The Evaluator Contract result is produced by the AEE engine itself (its `--evaluator-output`); the separate Evaluator extension from https://github.com/electrohire/spec-kit-evaluator is **not** required to run assess and the runner never invokes it. Install it only when you want its compose/report/route commands over the result. The runner reports `evaluator_extension_present` in its JSON so you can tell whether those commands are available.
3. Resolve the project root and source artifact. Never follow symlinks or read outside the project root.

Use threshold `0.70` when omitted. The adapter does not load YAML configuration; pass explicit flags for overrides. The engine repository is https://github.com/electrohire/applied-epistemic-engineering.

## Execution

Run:

```bash
python .specify/extensions/aee/scripts/python/run_aee.py assess --input <artifact> --phase <phase> --threshold <threshold>
```

With `policy=true`, append `--policy` (plus any threshold overrides); with `reliability=<path>`, append `--reliability <path>`.

The adapter writes a rich assessment under `.specify/extensions/aee/assessments/`, an Evaluator Contract result under `.specify/extensions/evaluator/results/`, and a chained ledger record under `.specify/extensions/aee/ledger/`.

The documented loop is assess → verify-ledger (FR-8.2): after appending, the runner itself verifies the ledger chain and reports the verdict in its JSON summary as `ledger_verification` (`valid`, `entries`, `head_hash`, `errors`), alongside the assessment, evaluator-result, and ledger paths. Read that verdict before trusting the record; a `valid: false` verdict means the chain — including records from before this run — does not verify. With `--no-ledger`, no append and no verification happen and `ledger_verification` is `null` — never a fabricated verdict. The bare engine CLI ledgers by default with identical semantics (same default path, `--no-ledger` opt-out, `--ledger` to choose another path). The assessment JSON file is a working copy; the ledger entry, which records the assessment's SHA-256, is the record of what was assessed (FR-8.3).

The runner also stamps its own version into the assessment as `metadata.extension_version` (FR-4.2). The stamp is applied before the ledger append hashes the assessment, so the ledger record covers the stamped file exactly. The engine stamps `metadata.engine_version` itself; assessments produced by the bare CLI have no `extension_version` key — its absence means no extension produced the run, and no tool fills it in after the fact.

Report the outcome, confidence threshold, claim/finding counts, unresolved contradictions, recommended recovery, and exact output paths. When the policy is attached, also report the verdict counts (accept / challenge / abstain) and name the abstained claims — an abstention is a deliberate non-verdict, not a low score. Do not describe an assessment as proof, certification, or truth.

When other evaluators ran at the same phase and the runner reported `evaluator_extension_present: true`, recommend `__SPECKIT_COMMAND_EVALUATOR_COMPOSE__ phase=<phase> strategy=strict`.

## Claim field vocabulary

The AEE engine validates every claim with `Claim.from_dict` and rejects the
whole bundle on the first invalid value. Use exactly these lowercase values;
`id` must be non-empty, and `confidence`, when present, must be between 0 and 1.

- `kind`: observation, requirement, assumption, inference, hypothesis, decision, prediction, compliance
- `status`: draft, supported, partially_supported, unsupported, contradicted, unverifiable, superseded
- `uncertainty`: none, low, medium, high, insufficient_evidence
- `severity`: critical, high, medium, low, info
- evidence `kind`: observed, inferred, asserted, contradicted, unsupported
- evidence `direction`: supports, contradicts, context
- evidence `source_quality`: primary, secondary, tertiary, artifact, test, human, model, unknown

## Guardrails

- Assess only claims with stable IDs; do not silently convert free prose into claims.
- Preserve counterevidence and contradictions.
- Model output is `asserted`, never `observed`.
- Do not modify the source artifact during assessment.

