# Static design oracle scope

`static-design-oracle.cjs` reads only candidate files. It creates no files,
processes, browser, server, database, or network request. It verifies the
design stylesheet injection into the compiled HTML, local runtime assets,
retained product navigation/API component hooks, and selected light-design
regression guards that can be established from text.

It does not validate interaction behavior or browser rendering. Those remain
the separate, pending offline Playwright visual run.

```powershell
node .\static-design-oracle.cjs C:\Users\user\.codex\worktrees\bos3-product-design\repo
```
