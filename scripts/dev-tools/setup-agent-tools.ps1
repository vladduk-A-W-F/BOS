# Встановлення інструментів розробки для Codex на ПК власника. Запускає лише власник.
# Не змінює продукт, БД, права чи секрети BoS.
#   powershell -ExecutionPolicy Bypass -File scripts\dev-tools\setup-agent-tools.ps1
#   ... -EnablePlaywright   # браузерний MCP: лише рішенням власника (A11 діє)
param([switch]$EnablePlaywright)
$ErrorActionPreference = 'Stop'

function Need($cmd, $hint) {
    if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) { throw "Немає '$cmd'. Встановіть: $hint" }
}
Need codex 'npm i -g @openai/codex'
Need node  'winget install OpenJS.NodeJS.LTS'
Need git   'winget install Git.Git'
Need gh    'winget install GitHub.cli'
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { winget install --id astral-sh.uv -e; throw 'uv встановлено: відкрийте нове вікно PowerShell і запустіть скрипт ще раз.' }

# 1. SkillSpector: сканер скілів (статично, без LLM і платних API).
uv tool install --upgrade git+https://github.com/NVIDIA/skillspector.git

# 2. ponytail: спершу сканування, потім рішення власника.
$tmp = Join-Path $env:TEMP 'ponytail-scan'
if (Test-Path $tmp) { Remove-Item -Recurse -Force $tmp }
git clone --depth 1 https://github.com/DietrichGebert/ponytail $tmp
skillspector scan $tmp --no-llm
if ((Read-Host 'Звіт вище. Встановити ponytail у Codex? (y/n)') -eq 'y') {
    codex plugin marketplace add DietrichGebert/ponytail
    codex plugin add ponytail@ponytail
    Write-Host 'Далі: codex -> /hooks -> перевірити й довірити 2 хуки -> новий тред.'
} else { Write-Host 'ponytail пропущено.' }

# 3. MCP для Codex.
codex mcp add context7 -- npx -y '@upstash/context7-mcp'
if ($EnablePlaywright) {
    codex mcp add playwright -- npx -y '@playwright/mcp@latest' --headless --isolated
} else { Write-Host 'Playwright MCP пропущено (запустіть з -EnablePlaywright).' }

# 4. GitHub: канал власник/Claude <-> Codex через коментарі PR.
gh auth status 2>$null; if ($LASTEXITCODE -ne 0) { gh auth login }

codex mcp list
Write-Host 'Готово. Перезапустіть Codex.'
