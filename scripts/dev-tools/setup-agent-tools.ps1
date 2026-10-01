# Встановлення інструментів розробки для Codex на ПК власника. Запускає лише власник.
# Не змінює продукт, БД, права чи секрети BoS.
#   powershell -ExecutionPolicy Bypass -File scripts\dev-tools\setup-agent-tools.ps1
#   ... -EnablePlaywright   # браузерний MCP: лише рішенням власника (A11 діє)
#   ... -Ponytail           # скіл ponytail закріпленої версії, без хуків
param([switch]$EnablePlaywright, [switch]$Ponytail)
$ErrorActionPreference = 'Stop'

function Need($cmd, $hint) {
    if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) { throw "Немає '$cmd'. Встановіть: $hint" }
}
Need codex 'npm i -g @openai/codex'
Need node  'winget install OpenJS.NodeJS.LTS'
Need git   'winget install Git.Git'
$ghLocal = 'D:\3\BOSDev\dev-tools\gh-2.102.0\bin'
if (-not (Get-Command gh -ErrorAction SilentlyContinue) -and (Test-Path $ghLocal)) { $env:PATH = "$ghLocal;$env:PATH" }
Need gh    'winget install GitHub.cli'
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { winget install --id astral-sh.uv -e; throw 'uv встановлено: відкрийте нове вікно PowerShell і запустіть скрипт ще раз.' }

# 1. SkillSpector: сканер скілів (статично, без LLM і платних API).
uv tool install --upgrade git+https://github.com/NVIDIA/skillspector.git

# 2. ponytail (лише з -Ponytail): тільки SKILL.md закріпленої версії, без плагіна й хуків.
#    Хуки плагіна додають правила в кожну сесію й субагентів (ролі BoS) — їх не ставимо.
#    Сканується й копіюється рівно той файл, SHA-256 якого звірено нижче.
if ($Ponytail) {
    $commit = 'e3ba2aa6f1e6f0bc4d69eb09c9f0d0a93af56156'
    $sha = '1316a2f3f95741d2300b116fe0c2d81ce4a9568656ed0a62643f54aaf09957f2'
    $tmp = Join-Path $env:TEMP 'ponytail-pinned'
    if (Test-Path $tmp) { Remove-Item -Recurse -Force $tmp }
    git -c core.autocrlf=false init -q $tmp
    git -C $tmp -c core.autocrlf=false fetch -q --depth 1 https://github.com/DietrichGebert/ponytail $commit
    git -C $tmp -c core.autocrlf=false checkout -q FETCH_HEAD -- skills/ponytail/SKILL.md
    $skill = Join-Path $tmp 'skills\ponytail'
    if ((Get-FileHash (Join-Path $skill 'SKILL.md') -Algorithm SHA256).Hash -ne $sha) { throw 'SHA SKILL.md не збігся; встановлення скасовано.' }
    skillspector scan $skill --no-llm
    if ((Read-Host 'Звіт лише для SKILL.md вище. Встановити як скіл Codex? (y/n)') -eq 'y') {
        $codexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $env:USERPROFILE '.codex' }
        $dest = Join-Path $codexHome 'skills\ponytail'
        New-Item -ItemType Directory -Force $dest | Out-Null
        Copy-Item (Join-Path $skill 'SKILL.md') $dest -Force
        Write-Host "ponytail встановлено: $dest. Перезапустіть Codex і перевірте /skills."
    } else { Write-Host 'ponytail пропущено.' }
}

# 3. MCP для Codex.
if (-not (codex mcp list | Select-String -Quiet 'context7')) { codex mcp add context7 -- npx -y '@upstash/context7-mcp' }
if ($EnablePlaywright -and -not (codex mcp list | Select-String -Quiet 'playwright')) {
    codex mcp add playwright -- npx -y '@playwright/mcp@latest' --headless --isolated
} else { Write-Host 'Playwright MCP пропущено (запустіть з -EnablePlaywright).' }

# 4. GitHub: канал власник/Claude <-> Codex через коментарі PR.
gh auth status 2>$null; if ($LASTEXITCODE -ne 0) { gh auth login --hostname github.com --git-protocol https --web }

codex mcp list
Write-Host 'Готово. Перезапустіть Codex.'
