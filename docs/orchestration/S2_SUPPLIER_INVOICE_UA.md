# S2 · реєстрація рахунку постачальника

## Межа

`erp_register_supplier_invoice` реєструє лише підтриманий synthetic one-line
рахунок, який сервер наново витягнув із verified original та повністю звірив з
явно обраними supplier, Purchase, item і receipt/return facts. Це не customer
Invoice, оплата, кредиторська проводка, загальний ledger, рух складу або зміна
статусу первинного Document.

## Ідентичність і незмінність

На одну Purchase дозволена рівно одна реєстрація. Окрема supplier invoice
identity також унікальна між Purchase: SHA-256 від supplier, дати та ключа
номера. Ключ номера — NFKC, trim, згортання будь-якого whitespace до одного
пробілу і uppercase; витягнутий номер зберігається дослівно. Тому інший
proposal або нове завантаження того самого бізнес-рахунку не створить другу
відповідальність. Зміна номера, дати або суми для вже зареєстрованої Purchase
є пояснюваною відмовою і потребує окремої future correction command. Рядок
зберігає verified source SHA, current Document, receipt/return IDs та context
SHA. Proposal fingerprint включає точну identity incoming Document; semantic
context окремо порівнює SHA bytes, PO, receipt/return і extracted facts для
safe duplicate upload під незалежним document code. Обидва incoming і original
accepted source повторно перевіряються з current Policy перед replay. Якщо
current Document або current context зміниться після прийняття, read
projection показує `requires_revalidation`; історичний рядок не переписується.

## Preview / confirm / replay

Клієнт передає тільки selection та очікуваний source SHA. Preview і confirm
поновлюють extraction/match з original bytes і current Policy. Confirm виконує
перевірку також до replay, тримає ERP write mutex, порівнює fingerprint та
строк proposal, CAS-claim, а потім в одній транзакції створює domain row, Event
і receipt. Зіставлений повтор того самого source/context повертає stable ID;
інша source/context версія того самого business identity відхиляється.

`TECHNICAL_READY=false`; `PILOT_ALLOWED=false`. UI, payment eligibility,
settlement, AP posting та persistable exception workflow залишаються окремими
картками.
