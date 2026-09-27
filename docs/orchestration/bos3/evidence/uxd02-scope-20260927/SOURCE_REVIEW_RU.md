# UXD02: source-bound scope before implementation

Independent read-only explorer bos3_control_pin_diagnosis checked observer
proposal f31160db683ecde300e9e26cf0c344f0c88ea5168b3c38390ed757740f46967e
and text5ccb3f49b094e46fd3bc0969ed667e305651d948bfa1e6ea2050134e1b58c4ca.
Productfa7e4c7, installed8114097 have exact sourceblob29bf3efc2900f334c2637af557692edecae170f7.
Current next applicable canonical61d9edd changes only control tools from811;
four UI blobs remain identical. Runtime is not the author workspace.

The original UXD02 increment is feasible without backend/API/policy/DB change:
orders (source5267) require any related line with b03Positive(b03OpenLine(line));
jobs (5276) status !== done; qualitylots (5266) quantity>0 and unapproved or missingdocs.
One shared monitorRows(data, key) must supply both displayedcount and exactlist.
Generic kind:list orders at5003 uses confirmedstatus and is NOT equivalent.
Existing server Policy filters snapshot orders/lines/jobs/lots (erp/views16,
queries83). Inspector record kinds are orders/jobs/lots; current snapshot
visibility is checked by homeSelectionVisible5151.

Required implementation bounds:
- Only three named metrics; tasks/receivable retain existing generic navigation.
- Dedicated monitor-list kind restricted to those keys, record IDs from current
  snapshot; monitorOrigin carried inside selection, not durable independentstore.
- Record close returns same exactfilteredlist, list close returns monitor.
- Refresh5221/contextchange5210/stale/denied/unavailable/sessionend clear selection
  and origin; ready guard5309 remains. Source reread terminates the trail.
- Existing readOnly inspector omits normal actions, but nested DocViewer3733
  still exposes manual-review write for write-capable users. Add default-false
  readOnly prop there and pass inspector readOnly through; suppress that control
  only in readOnly mode. Existing non-readOnly behavior unchanged.
- OrderTrace4774 already performs a guarded trace GET; source click4790 invokes
  traceSelect5256, clears selection/marksstale. No newAPI; never promise retained
  return context after this source reread. Do not pass inspector onNavigate in
  monitor mode, disabling linked-task escape4801.

Allowlist: frontend/boss_app_source.html only BosGlobalMonitor/BoSHome/
homeSelectionVisible/monitorRows/BoSInspector and DocViewer readOnly gate;
related compact CSS if required, two generatedoutputs, docs/design/evidence-uxd02-drilldown-20260927/.
No backend/registry/version/PDF/learning/waiting/controltool/rights mutations.
Independent assignment reviewer must accept bounds before existing design author
starts. One necessary generation of newsource allowed later; QA is separately
classified NEW/SAME-PROBLEM and independently reviewed, no browser/DB allowance.
FullUXD02, cross-role acceptance and readiness remain unproven.
