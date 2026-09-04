---
description: "Adversarially challenge claims and identify bounded recovery work"
---

# AEE Challenge

Challenge explicit claims for observability, atomicity, boundaries, falsifiability, evidence independence, provenance, missing dependencies, cycles, and contradictions.

## User input

```text
$ARGUMENTS
```

Resolve `artifact=<path>` and optional `phase=<phase>` using the same prerequisites and path rules as `__SPECKIT_COMMAND_AEE_ASSESS__`. Run the AEE adapter's `assess` operation, then focus the response on failure modes rather than aggregate scoring.

For every failure, report:

- stable failure and claim IDs;
- the deterministic challenge that triggered;
- the inspectable breakpoint;
- evidence references and their kinds;
- a bounded recovery action and how its completion can be verified.

Never delete a conflicting position, manufacture evidence, or accept model self-attestation as independent support. Recommend rerunning `__SPECKIT_COMMAND_AEE_ASSESS__` after recovery work changes the source artifact.

