# Changelog

All notable changes follow Semantic Versioning.

## 1.4.0 - 2026-10-12

- Design correction (specs/005-evaluator-required): the
  spec-kit-evaluator extension is now a **required** companion,
  declared `required: true` in `extension.yml` and enforced by the
  runner — `assess` refuses with exit 2, naming the missing extension
  and how to install it, when `.specify/extensions/evaluator/` is
  absent from the project, and writes nothing. In 1.3.0 the extension
  was declared optional and only the contract was required, which
  made consistency opt-in; AEE is one evaluator among many by design,
  and its results are composed through the common evaluator so every
  evaluator's output is handled the same way. The pair is one system.
  `check_install.py` now also exercises the refusal end to end
  (evaluator extension removed → `assess` exits 2 naming it), README,
  the assess command document, and the usage docs teach the pair as
  one system, and the evaluator install reference moves to its
  v1.1.0 release archive.

## 1.3.0 - 2026-10-12

- RT3 remediation (specs/rt3-remediation): `gaps` refuses symlinked or
  out-of-root evidence in a runner-side pre-flight instead of letting it
  close gaps (RT3-05); generated assessment/challenge/graph filenames
  carry microsecond + random suffixes so same-second runs never collide
  (RT3-08); every engine subprocess runs under `--timeout` (default
  600 s) with a distinct timed-out verdict — exit 2, `timed_out: true`,
  never a scored outcome (RT3-11); `assess` maintains a
  `latest-<phase>` pointer and `gate --latest <phase>` gates it with an
  age note (RT3-13); token-router discovery is confined to the project
  root/parent, router ranges are strictly typed, and the route record
  names the router path + SHA-256 (RT3-10); token-economy `shell` runs
  in the project root under a timeout and redacts secret-looking argv
  values from telemetry (RT3-09); `route` refuses files over a 256 MB
  byte cap instead of loading them whole (RT3-18); `_safe_output`
  returns resolved paths in both adapters (RT3-17); command templates
  quote path placeholders verbatim (RT3-12); README/CHANGELOG/usage
  drift corrected and pinned by tests (RT3-14); `check_install.py`
  checks are explicit (survive `python -O`) with an optional
  `--from-archive` mode (RT3-16); the config template header states
  that no script loads it (RT3-19).
- Spec 004 P5 vocabulary alignment (specs/004-vocabulary-alignment):
  the engine floor moves to the realigned engine
  (`applied-epistemic-engineering>=1.5.0,<2` — methodology 2.0, Spec
  004 stage vocabulary) in the runner, `extension.yml`, and README,
  and the runner's startup enforcement refuses older engines by name;
  the `assess` JSON gains a `verdict_display` block copied from the
  stamped assessment (outcome, methodology version, stage-capped
  `reported_statuses`, `stage_caps`, the lane pair, `not_understood`),
  so the extension displays exactly what the bare CLI reports on the
  same bundle; the runner drives the engine's recorded `--lenient`
  compatibility mode for assess/challenge/graph when the installed
  engine advertises it, so pre-realignment bundles (no `stage`
  field) load with the default on the record instead of being
  refused; the assess/gate command documents teach the realigned
  vocabulary (stages, exposition, headline decomposition roles,
  reported-not-declared statuses, lane-paired reporting,
  `not_understood` with every verdict, unjudged distinct from
  abstained).

## 1.2.0 - 2026-10-06

- Spec 002 Phase 4 (extension parts): new `speckit.aee.draft-claims` command
  (ten commands total) and runner `draft-claims` subcommand over the engine's
  `aee.extract` drafting helper — drafts are born `draft` with
  `asserted`/`model` evidence, TODO falsifiers pass through untouched for
  strict loading to reject, and `depends_on` proposals from explicit spec
  cross-references are surfaced in the summary; no tool path ratifies or
  upgrades a draft. The runner now stamps `metadata.extension_version` into
  assessments before ledgering (through the engine's own `aee.ledger`, so
  the ledger SHA-256 covers the stamped file) and reports the post-append
  chain verification as `ledger_verification` in the assess summary
  (`null` under `--no-ledger`).
- Wire the engine's epistemic-ledger ports into the assess flow: the runner's
  `assess` gains `--policy` (per-claim ACCEPT / CHALLENGE / ABSTAIN verdicts,
  with `--min-independent-sources` / `--contested-threshold` overrides) and
  `--reliability <table.json>` (measured per-source reliability blended into
  scoring); a new `speckit.aee.review` command diffs two assessments into a
  materiality-filtered review queue via the runner's `review` subcommand.
- Require `applied-epistemic-engineering>=1.4.0,<2` (dev pin 1.4.0): the CLI
  surface for the gates, reliability, and review landed in engine 1.4.0, on
  top of the 1.1.0-1.3.0 library ports.

## 1.1.0 - Released as part of 1.2.0 (no separate tag)

- Integrate the token-economy policy into AEE core: declare optional `rtk`,
  `headroom`, `token-router`, and `ollama` tools; add `speckit.aee.route-evidence`
  (local triage to raw slices; assess gates reason over slices only, never over
  router prose) and `speckit.aee.report-savings` (measured-only, RTK and Headroom
  reported separately, never estimated or double-counted). The tools stay external
  runtimes; AEE cores the policy and degrades gracefully when a tool is absent.
- Add `scripts/python/aee_token_economy.py` (tool status, evidence routing with
  deterministic fallback, measured savings aggregation, shell telemetry wrapper)
  with fail-closed secret-file refusal and path safety mirroring `run_aee.py`.
- Document headroom integration points for long-horizon sessions
  (`docs/token-economy.md`): proxy/wrap/SharedContext hook-in points and the hard
  rule that gates see raw slices, never compressed summaries.
- Fix the branch's own checks to match the surface it ships: manifest tests and
  `check_install.py` now assert eight commands and the required/optional tool
  split (they still asserted the 1.0.1 surface and failed).
- Token-router discovery anchors on `--project-root`, not the caller's working
  directory; the `shell` wrapper validates `--telemetry` before running the
  wrapped command instead of raising after its side effects.

## 1.0.1 - 2026-09-23

- Declare Python, AEE engine 1.0.2 (needed for `gaps`), and Evaluator Contract dependencies using Spec Kit's documented tool metadata.
- Replace the unsupported `requires.commands` field with explicit installation guidance; dependencies are informational and are not auto-installed by Spec Kit.
- Add newcomer setup, configuration limitations, troubleshooting, and a link to the benchmark's measured results and failures.
- Install the actual engine in hash-locked CI, validate with Spec Kit's own manifest parser, and exercise every adapter operation without silently skipping missing-engine integration tests.
- Document the exact AEE claim field vocabulary in `speckit.aee.assess` so agents emit schema-valid claims on the first attempt.
- Trim the extension description to under 100 characters per the Spec Kit extension publishing guide.
- Add deterministic `extension.yml` and documentation compliance tests.

## 1.0.0 - 2026-09-09

- Add six Spec Kit AEE commands and five optional lifecycle hooks.
- Integrate `applied-epistemic-engineering` 1.x with Evaluator Contract 1.0.
- Add path-safe execution, structured claim template, ledger verification, and CI validation.
- Add the `speckit.aee.gaps` command and `after_verify` hook to generate and maintain the gap register from a verification matrix and test evidence.
- Add dependency review, Dependabot, OpenSSF Scorecard, and hash-locked CI installs.
- Document the private disclosure process and response timeline.
