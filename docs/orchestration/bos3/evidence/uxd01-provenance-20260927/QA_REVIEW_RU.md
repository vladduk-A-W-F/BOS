# UXD01: independent AST result review

Reviewer start_overview_review, 2026-09-27.
Verdict ACCEPT_SCOPED_AST_PRESENTATION_DISCLOSURE.

Run1 FAIL/exit1 retained: confirmed oracle collector defect, not a UI defect.
Run2 focused attempt2/3: native exit0, four AST assertions groups PASS,
byte-empty stderr. Receipt804e6325722252132ba0e8a9072d23386bf641290663e921ed321cde19567c83,
stdoutbc5a02997eebf603274c52d8545bdbeca3c0ff73bfae0e0456dd5860db40f09b.
Exact source0338cc026a91f1aadc0f41ebf6cff812f72d7086, SHA256
cc97bee6d680df1bc4aedd6a3a6892b3283a17434867b268c11d38010b1732e7.

Reviewed v2 oracle/scope, command and pins agree with the actual receipt.
Assertions cover five metric provenance descriptors, ready-only disclosure,
time caveats and guarded navigation. The raw category NEW_AST_PRESENTATION_DISCLOSURE
identifies the original problem; attempt2 is the same problem, not a new cap.

No browser, application mount, policy/API, DB, learning, runtime or full
acceptance. No further run authorized. Prior historical QA caps unchanged.
