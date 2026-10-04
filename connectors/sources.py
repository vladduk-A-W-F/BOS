"""Read tabular data from a company's own services. Read-only, size-limited, no secrets."""
import csv
import hashlib
import io
import json
import re
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, build_opener, HTTPRedirectHandler

MAX_BYTES = 5 * 1024 * 1024
MAX_ROWS = 5000
MAX_COLUMNS = 50
MAX_CELL = 500
FETCH_TIMEOUT = 10
SHEET_ID = re.compile(r'^/spreadsheets/d/([A-Za-z0-9_-]{20,100})')

# Universal catalog: what a company can connect. Only 'available' kinds work today.
CATALOG = (
    {'kind': 'csv', 'title': 'Excel / CSV', 'group': 'Таблиці', 'state': 'available',
     'gives': 'Будь-яка таблиця: замовлення, оплати, залишки'},
    {'kind': 'google_sheets', 'title': 'Google Таблиці', 'group': 'Таблиці', 'state': 'available',
     'gives': 'Опублікована таблиця, оновлюється за посиланням'},
    {'kind': 'monobank', 'title': 'Monobank', 'group': 'Банк', 'state': 'planned',
     'gives': 'Виписки та надходження'},
    {'kind': 'privatbank', 'title': 'ПриватБанк', 'group': 'Банк', 'state': 'planned',
     'gives': 'Виписки та надходження'},
    {'kind': 'nova_poshta', 'title': 'Нова Пошта', 'group': 'Доставка', 'state': 'planned',
     'gives': 'Статуси відправлень'},
    {'kind': 'checkbox', 'title': 'Checkbox', 'group': 'Каси (ПРРО)', 'state': 'planned',
     'gives': 'Чеки та зміни'},
    {'kind': 'binotel', 'title': 'Binotel', 'group': 'Телефонія', 'state': 'planned',
     'gives': 'Журнал дзвінків'},
    {'kind': 'ringostat', 'title': 'Ringostat', 'group': 'Телефонія', 'state': 'planned',
     'gives': 'Журнал дзвінків'},
    {'kind': 'bas', 'title': 'BAS', 'group': 'Облік', 'state': 'planned',
     'gives': 'Замовлення, залишки, рахунки'},
    {'kind': 'dilovod', 'title': 'Dilovod', 'group': 'Облік', 'state': 'planned',
     'gives': 'Замовлення, залишки, рахунки'},
)


class SourceError(ValueError):
    pass


def _decode(raw):
    for encoding in ('utf-8-sig', 'cp1251'):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise SourceError('Не вдалося прочитати кодування файлу. Збережіть його як CSV UTF-8.')


def _table(rows):
    rows = [[('' if cell is None else str(cell)).strip()[:MAX_CELL] for cell in row] for row in rows]
    rows = [row for row in rows if any(row)]
    if not rows:
        raise SourceError('Таблиця порожня.')
    header, body = list(rows[0]), rows[1:]
    while header and not header[-1]:
        header.pop()
    if len(header) > MAX_COLUMNS:
        raise SourceError(f'Забагато колонок: максимум {MAX_COLUMNS}.')
    if len(body) > MAX_ROWS:
        raise SourceError(f'Забагато рядків: максимум {MAX_ROWS}.')
    columns = [name or f'Колонка {index + 1}' for index, name in enumerate(header)]
    if len(set(columns)) != len(columns):
        raise SourceError('Назви колонок у першому рядку мають бути різними.')
    width = len(columns)
    body = [(row + [''] * width)[:width] for row in body]
    digest = hashlib.sha256(json.dumps([columns, body], ensure_ascii=False).encode()).hexdigest()
    return {'columns': columns, 'rows': body, 'row_count': len(body), 'sha256': digest}


def parse_csv(raw):
    if len(raw) > MAX_BYTES:
        raise SourceError('Файл більший за 5 МБ.')
    text = _decode(raw)
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=',;\t')
    except csv.Error:
        dialect = csv.excel
    return _table(csv.reader(io.StringIO(text), dialect))


def parse_xlsx(raw):
    if len(raw) > MAX_BYTES:
        raise SourceError('Файл більший за 5 МБ.')
    from openpyxl import load_workbook
    try:
        book = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    except Exception as exc:
        raise SourceError('Не вдалося відкрити Excel-файл.') from exc
    try:
        sheet = book.worksheets[0]
        return _table(sheet.iter_rows(values_only=True, max_row=MAX_ROWS + 2, max_col=MAX_COLUMNS + 1))
    finally:
        book.close()


def parse_upload(name, raw):
    lower = (name or '').lower()
    if lower.endswith('.xlsx'):
        return parse_xlsx(raw)
    if lower.endswith(('.csv', '.txt')):
        return parse_csv(raw)
    raise SourceError('Підтримуються файли .xlsx та .csv.')


def sheet_export_url(url):
    """Only public Google Sheets on docs.google.com; anything else is refused (no SSRF)."""
    parts = urlparse(url or '')
    match = SHEET_ID.match(parts.path or '')
    if parts.scheme != 'https' or parts.hostname != 'docs.google.com' or parts.port or not match:
        raise SourceError('Потрібне посилання https://docs.google.com/spreadsheets/d/…')
    gid = parse_qs(parts.query).get('gid', [''])[0] or parse_qs(parts.fragment).get('gid', [''])[0]
    gid = gid if gid.isdigit() else '0'
    return f'https://docs.google.com/spreadsheets/d/{match.group(1)}/export?format=csv&gid={gid}'


class _SameHostRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        host = urlparse(newurl).hostname or ''
        if urlparse(newurl).scheme != 'https' or not (host == 'docs.google.com'
                                                      or host.endswith('.googleusercontent.com')):
            raise SourceError('Google перенаправив на неочікувану адресу.')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_sheet(url, opener=None):
    export = sheet_export_url(url)
    opener = opener or build_opener(_SameHostRedirect)
    try:
        with opener.open(Request(export, headers={'User-Agent': 'BoS-connector'}),
                         timeout=FETCH_TIMEOUT) as response:
            raw = response.read(MAX_BYTES + 1)
    except SourceError:
        raise
    except Exception as exc:
        raise SourceError('Таблиця недоступна. Перевірте, що її опубліковано: Файл → Поділитися → '
                          'Опублікувати в інтернеті → CSV.') from exc
    if raw.lstrip()[:15].lower().startswith(b'<!doctype html') or raw.lstrip()[:5].lower() == b'<html':
        raise SourceError('Таблиця не опублікована або закрита доступом.')
    return parse_csv(raw)
