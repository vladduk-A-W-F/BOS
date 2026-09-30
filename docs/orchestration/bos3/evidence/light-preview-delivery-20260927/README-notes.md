# B30-PREVIEW-DELIVERY-PREP

Статична підготовка окремого maintenance runner для light-preview BoS 3.0.
Цей scratch-пакет не є дозволом на запуск maintenance, capture, apply, stop,
start, HTTP, browser, збірку, тести або роботу з runtime.

## Зафіксовані refs

- Frozen runtime baseline: `33d7d387aa582c04339a91ae94361948ea67904c`.
- Reviewed UI parent: `aee8d0ee41afd5cba256a0b4a4deddadf7af6e4e`.
- Exact delivery candidate: `f55a15de4006d10c0d7c65f8a2ca8499fbb99819`.

## Exact product allowlist

Він походить з read-only `git diff --name-status 33d7... f55a...`:

- `README.md`
- `README_UA.md`
- `assets/app.js`
- `assets/bos3-fasteners-entry.png`
- `boss_project/refinement_views.py`
- `boss_project/version.py`
- `docs/BoS_3_0_Start_UA.manifest.json`
- `docs/BoS_3_0_Start_UA.pdf`
- `frontend/bos3_content.json`
- `frontend/boss_app_html.html`
- `frontend/boss_app_source.html`
- `scripts/build_bos3_brochure.py`

`docs/orchestration/**` залишається окремо дозволеним provenance/evidence
контентом і не є product allowlist. Будь-який інший product path має
відхилити runner до source switch.

## Незмінні запобіжники runner

- exact old baseline, immutable candidate SHA, ancestry і clean source;
- blob-level PNG signature check на candidate commit;
- prepared source/digest/port/database binding;
- receipt PID, creation ticks, image, command tokens та лише loopback listener;
- confirmed stopped state до apply;
- fail-closed hash binding `data`, `media` і private credential files без
  друку чи копіювання їхнього вмісту;
- atomic update тільки `prepared.source_sha256`; runner не викликає init,
  migrate, seed, reset, rollback, stop або start.

## Межа рішення

Потрібен окремий прямий дозвіл власника на одне maintenance-вікно та незалежний
review цього scratch diff. Підготовлений candidate не означає приймання runtime,
browser, availability або release readiness. Історичні ліміти спроб не змінені.
