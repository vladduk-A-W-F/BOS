# Next functional scope — UXD02 monitor in-place drilldown

This is an author proposal for the sole integrator, based on exact product commit `fa7e4c77aed75a54d9067e0709a8b37229755c59`. It is not an assignment, implementation, test result or acceptance.

The proposed scope advances a real part of UXD-02: from three monitor metrics to the exact existing snapshot records counted by each metric, then to one existing record inspector and back to the unchanged monitor context. The three metrics are open orders, open production jobs and quality lots. Current source already computes their predicates from the access-filtered snapshot; current monitor discards that context by navigating only to `section/sub`.

The card would reuse the current snapshot and existing inspector. It must preserve the exact metric predicates, retain policy/read-only guards and use a bounded back trail that clears on stale, denied or changed context. It adds no API, data model, role, route, action, branch filter or calendar-period behavior.

Tasks and receivables are deliberately excluded. Tasks currently leave the inspector for HR routing, and receivables need an exact invoice/currency/credit reconciliation before a list can equal the displayed metric. Including either would create a false functional claim.

Source and allowlist details, future review requirements, caps and risks are in the JSON. No product edits, tests, builds, CLI, HTTP, browser, database or runtime actions were performed.
