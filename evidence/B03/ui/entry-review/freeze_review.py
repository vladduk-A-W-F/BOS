from pathlib import Path
import hashlib,json,difflib
p=Path(__file__).resolve().parent;base=p.parent/'b03_ui_candidate';candidate=p.parent/'b03_ui_root_candidate';s=candidate/'frontend/boss_app_source.html';h=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
a=(base/'frontend/boss_app_source.html').read_text();b=s.read_text()
# Narrow unchanged legacy regions: parser helper changes are outside these sections.
def chunk(text,start,end):return text[text.index(start):text.index(end,text.index(start))]
regions={
'ERP_ACTIONS':('const ERP_ACTIONS={','function ERPActionDialog('),
'ERPActionDialog':('function ERPActionDialog(','const IMPORT_ENTITIES='),
'InitialImportDialog':('function InitialImportDialog(','// B03_HELPERS_BEGIN'),
}
unchanged={}
for name,(start,end) in regions.items():
 try:unchanged[name]=chunk(a,start,end)==chunk(b,start,end)
 except ValueError:unchanged[name]='delimiter_not_found'
checks=json.loads((p/'FINAL_GREEN.json').read_text());receipt=json.loads((p/'PROCUREMENT_GREEN.json').read_text());assert checks['source_sha256']==h(s)==receipt['source_sha256'];assert all(c['passed'] for c in checks['checks']) and receipt['passed']
assert all(value is True for value in unchanged.values()),unchanged
manifest={'scope':'Independent B03 root UI delta source/build/actual extracted JS review; no browser or HTTP UI acceptance','base_source_sha256':h(base/'frontend/boss_app_source.html'),'final_source_sha256':h(s),'final_app_sha256':h(candidate/'assets/app.js'),'final_html_sha256':h(candidate/'frontend/boss_app_html.html'),'legacy_regions_byte_identical':unchanged,'evidence':{name:h(p/name) for name in ['REVIEW_RED.json','UUID_GREEN.json','PROCUREMENT_RED.json','FINAL_GREEN.json','PROCUREMENT_GREEN.json','check_entry_review.cjs','check_procurement_receipt.cjs']}}
(p/'REVIEW_MANIFEST.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
(p/'ROOT_UI_DELTA.patch').write_text(''.join(difflib.unified_diff(a.splitlines(True),b.splitlines(True),fromfile='base/frontend/boss_app_source.html',tofile='candidate/frontend/boss_app_source.html')))
report=f'''# B03: незалежний огляд доповнення входу через асистента

Вердикт: у погодженій вузькій області нових блокерів після двох виправлень не лишилось. Це source/build review та виконання ізольованих фактичних JS-функцій; браузерне приймання й gate10 лишаються відкритими.

Перевірено delta між замороженим UI `340fbaf24ca3c0e75adfc18f3004034e24d7025fcb3ef7cf97bd250c2614943c` і root-кандидатом `{h(s)}`. App `{h(candidate/'assets/app.js')}` точно відповідає повторній Babel-компіляції в пам’яті. Зміни в canonical/заморожений UI/repo reviewer не вносив.

## Контракт і маршрути

Новий `b03ImportedAction` приймає шість оголошених дій, перевіряє закритий набір верхніх/вкладених полів, canonical UUID4, integer ID, XOR джерела скасування, allocation ordinal/returnID та передає десяткові рядки через чинний `b03Payload`. Дані не виконуються на етапі JSON-вводу: спочатку snapshot та форма, потім звичайний preview/confirm. Actual source/кількість/дата/право остаточно перевіряє backend.

Обидва parent entrypoints (`OperationsAssistant`, `Procurement`) тепер використовують `BoSActionDialog`, який направляє тільки B03 до `CorrectionActionDialog`; старі ERP дії й B02 залишилися незмінними. CEO-only monetary role gate дублюється у parser та dialog, а сервер перевіряє права повторно. Source imports не створюють prospective IDs як нібито збережені записи.

## Виявлені й закриті помилки

1. Наданий JSON `operation_id` спочатку зберігався тільки при mount; `change()` скидав його при редагуванні, отже preview міг мовчки створити новий намір. Actual extracted `change()` відтворив `UUID → null` у `REVIEW_RED.json`. Тепер imported `preset.operation_id` залишається незмінним при редагуванні; змінений payload із тим самим UUID перевірить сервер. Звичайна порожня форма зберігає свою попередню поведінку. Новий намір потребує явної нової форми або JSON із новим UUID.
2. Procurement після скасування PO використовував повідомлення звичайної закупівлі навіть при `effective_open=0.000`. `PROCUREMENT_RED.json` відтворив це на фактичному JSX receipt branch. Тепер гілка `erp_cancel_remaining` показує записане скасування та історичний залишок після саме цього погодження; поточний стан доступний через картку actual PO. Старий purchase текст збережено для звичайної закупівлі.

## Докази й межі

`FINAL_GREEN.json`: 13/13 вузьких перевірок, включно з actual import/change closures, manager rejection трьох грошових дій, observer rejection, зайвими/вкладеними полями, numeric quantity, string ID та invalid UUID; exact Babel match. `PROCUREMENT_GREEN.json`: known receipt-message red став green. Root окремо має свої шість actual entrypoint red→green доказів.

Snapshot у JS harness був контрольованим read-only значенням. Receipt JSX перевірено через дерево React-елементів, без DOM, CSS, pointer, keyboard чи network acceptance. Новий широкий UI sweep не проводився. Існуючі ризики async lifecycle в старих entrypoints цим вузьким оглядом не оголошуються закритими. Повний інтеграційний gate запускає root окремо.

Hashes входів/результатів — `REVIEW_MANIFEST.json`; точний scoped diff — `ROOT_UI_DELTA.patch`.
'''
(p/'REVIEW_UA.md').write_text(report)
print(json.dumps({'source':h(s),'manifest':h(p/'REVIEW_MANIFEST.json'),'report':h(p/'REVIEW_UA.md'),'legacy':unchanged},ensure_ascii=False))
