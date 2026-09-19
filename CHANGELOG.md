# Changelog

All notable changes follow Semantic Versioning.

## Unreleased

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
