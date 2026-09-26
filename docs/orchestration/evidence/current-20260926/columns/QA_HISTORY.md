# UI-COLUMN-CONTENT-01 QA history

Scope: isolated renderer/descriptor checks only. This file is an index to raw
receipts and is not a product-readiness claim.

## Candidate identity

- Git base / HEAD: `a3c0596ab611290ba5ad199f55309812093f908b`
- Node: `C:\\Users\\user\\.cache\\codex-runtimes\\codex-primary-runtime\\dependencies\\node\\bin\\node.exe`

## Focused attempt 1

- Source SHA-256: `66B8E20382B1F4E5BFEDCC2C85DEBA34E34B21E7B5C37283BE8DFE9E797240EE`
- Harness SHA-256: `18669ABC87BAE7A6FE99534E30980C0DB0EDF9B7586D2BC5102265D252D4DD6F`
- Result: exit 1, assertion actual `0`, expected `4` at harness line 43.
- Raw receipts: `module_column_content.command.txt`,
  `module_column_content.stdout-stderr.txt`.

## Focused attempt 2

- Source SHA-256: `3D2F1092C0B4E99347816CF7AADC1F7062E9DB8B2C1F5FA80FB12D0A08538FE3`
- Harness SHA-256: `A40E70EF6037535E903AC5CB856A31CEB1AEC2C150230EB67E66EC27C990B077`
- Result: exit 1, assertion actual `0`, expected `4` at harness line 43.
- Raw receipts: `module_column_content.attempt-2.command.txt`,
  `module_column_content.attempt-2.stdout-stderr.txt`.

## Focused attempt 3

- Source SHA-256: `3D2F1092C0B4E99347816CF7AADC1F7062E9DB8B2C1F5FA80FB12D0A08538FE3`
- Harness SHA-256: `8BDEA68BDA813522D7F0EE1C6CFD114AB8EB0DD5BBD14BF3FBA5023F97602682`
- Result: exit 0; four focused checks passed.
- Raw receipts: `module_column_content.attempt-3.command.txt`,
  `module_column_content.attempt-3.stdout-stderr.txt`.

The v1 harness was an untracked working-tree file and was superseded before
archival; its raw receipt and SHA-256 remain above. The author retained the v2
harness patch separately and it is copied into this evidence directory when
available. The actual common failure cause for attempts 1 and 2 was the
synthetic model missing `source.rows`, so `moduleRows` returned no cards. The
v3 fixture clones the existing CEO `orders` descriptor with `source.rows`.
The v2 lazy `useState` mock improvement was not established as the failure
cause. No test/build/browser command ran between attempt 2 and the approved
third focused attempt.
