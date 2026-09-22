# Original migration history fixtures

These three Python files are immutable, byte-for-byte source fixtures from the
accepted local commit `646d3b80597e087a1ada14221024ec40588996f0` and pinned PR2
commit `abb8845f6563bafa806029ddc1e7c2cace09907c`. They are not business modules,
an installed Django app, or migration discovery packages; do not add
`__init__.py` files here.

`erp.test_network_migration_composition` explicitly verifies SHA-256 before
loading each original Migration class. The synthetic history test constructs
the actual original local or network history before applying the composition.
It does not fake migration receipts. The ordinary application loader continues
to use `erp/migrations` only.

| Fixture | SHA-256 |
| --- | --- |
| `local646/erp/migrations/0006_branch_links.py` | `77f54cffecd28e0188fcff937295c0e6ccc5ba9be191f9f193a1ab268c74a8c3` |
| `pr2abb8845/erp/migrations/0006_network_operations.py` | `040e15b35fd2d87840e9eecad494b192ccfd4625c2ff94a2ca89c9c22a72a1ef` |
| `pr2abb8845/erp/migrations/0007_request_timing.py` | `529a8f24cc8ad817806a0ec990222936be336c256baea6c1a831110dfe433060` |

The default fixture path is portable inside the checkout. An explicit
`BOS_COMPOSITION_ORIGINALS` override may point at an equivalent fixture root;
the same hashes are mandatory. Preserve bytes and line endings.
