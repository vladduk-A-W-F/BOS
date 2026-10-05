"""Map columns of a connected table to the fields BoS shows in «Моніторинг». Pure functions, no I/O.

A mapping is {field: source column name}. Values are normalized when read: exact decimals as strings
(never floats), ISO dates, known currencies only. A row that cannot be read is rejected with a reason,
never guessed.
"""
import re
from datetime import datetime
from decimal import Decimal

# dataset -> ((field, label, required, kind), ...)
FIELDS = {
    'orders': (('code', 'Номер замовлення', True, 'text'), ('customer', 'Клієнт', True, 'text'),
               ('due_date', 'Строк', False, 'date'), ('amount', 'Сума', False, 'money'),
               ('currency', 'Валюта', False, 'currency'), ('status', 'Стан', False, 'text'),
               ('branch', 'Філія', False, 'text')),
    'payments': (('reference', 'Документ оплати', True, 'text'), ('counterparty', 'Контрагент', True, 'text'),
                 ('amount', 'Сума', True, 'money'), ('currency', 'Валюта', False, 'currency'),
                 ('paid_at', 'Дата оплати', False, 'date'), ('direction', 'Напрям', False, 'direction')),
    'stock': (('item', 'Номенклатура', True, 'text'), ('quantity', 'Кількість', True, 'quantity'),
              ('unit', 'Одиниця', False, 'text'), ('location', 'Склад', False, 'text')),
    'calls': (('started_at', 'Час дзвінка', True, 'datetime'), ('contact', 'Контакт', True, 'text'),
              ('direction', 'Напрям', False, 'direction'), ('duration_s', 'Тривалість, с', False, 'quantity'),
              ('result', 'Результат', False, 'text')),
}

# Header words in Ukrainian, Russian and English that suggest a field. Compared case-insensitively.
SYNONYMS = {
    'code': ('номер', '№', 'код', 'замовлення', 'заказ', 'order', 'number', 'id'),
    'customer': ('клієнт', 'клиент', 'покупець', 'покупатель', 'замовник', 'customer', 'client', 'buyer'),
    'due_date': ('строк', 'срок', 'дата відвантаження', 'дата поставки', 'due', 'deadline', 'дата'),
    'amount': ('сума', 'сумма', 'вартість', 'стоимость', 'amount', 'total', 'sum'),
    'currency': ('валюта', 'currency'),
    'status': ('стан', 'статус', 'status', 'state'),
    'branch': ('філія', 'филиал', 'branch', 'відділення'),
    'reference': ('документ', 'номер платежу', 'платіж', 'платеж', 'reference', 'ref', 'номер'),
    'counterparty': ('контрагент', 'платник', 'плательщик', 'отримувач', 'counterparty', 'payer', 'клієнт'),
    'paid_at': ('дата оплати', 'дата оплаты', 'дата', 'date', 'paid'),
    'direction': ('напрям', 'направление', 'тип', 'direction', 'type'),
    'item': ('номенклатура', 'товар', 'артикул', 'назва', 'название', 'item', 'product', 'sku'),
    'quantity': ('кількість', 'количество', 'залишок', 'остаток', 'qty', 'quantity'),
    'unit': ('одиниця', 'единица', 'од.', 'unit'),
    'location': ('склад', 'місце', 'место', 'location', 'warehouse'),
    'started_at': ('час', 'дата', 'время', 'start', 'time', 'date'),
    'contact': ('контакт', 'телефон', 'номер', 'клієнт', 'phone', 'contact', 'caller'),
    'duration_s': ('тривалість', 'длительность', 'duration', 'сек'),
    'result': ('результат', 'статус', 'result', 'status', 'outcome'),
}
CURRENCIES = {'UAH': 'UAH', 'ГРН': 'UAH', 'ГРН.': 'UAH', '₴': 'UAH', 'EUR': 'EUR', '€': 'EUR', 'USD': 'USD', '$': 'USD'}
DIRECTIONS = {'in': 'in', 'вхідний': 'in', 'вхідна': 'in', 'входящий': 'in', 'надходження': 'in', 'прихід': 'in',
              'out': 'out', 'вихідний': 'out', 'вихідна': 'out', 'исходящий': 'out', 'списання': 'out', 'видаток': 'out'}
MAX_MONEY = Decimal('999999999999.99')


class MappingError(ValueError):
    pass


def fields(dataset):
    return [{'field': f, 'label': label, 'required': required} for f, label, required, _ in FIELDS.get(dataset, ())]


def suggest(dataset, columns):
    """Best guess {field: column}; each column used once, required fields first, exact words before parts."""
    taken, out = set(), {}
    order = sorted(FIELDS.get(dataset, ()), key=lambda f: not f[2])
    for exact in (True, False):
        for field, _, _, _ in order:
            if field in out:
                continue
            for column in columns:
                if column in taken:
                    continue
                name = column.strip().lower()
                words = SYNONYMS.get(field, ())
                if (name in words) if exact else any(w in name for w in words):
                    out[field] = column
                    taken.add(column)
                    break
    return out


def validate(dataset, columns, mapping):
    """Return a clean mapping or raise MappingError with a plain-Ukrainian reason."""
    if dataset not in FIELDS:
        if mapping:
            raise MappingError('Для набору «Інше» відповідність колонок не задається.')
        return {}
    if not isinstance(mapping, dict):
        raise MappingError('Відповідність колонок має бути об’єктом «поле → колонка».')
    known = {f: (label, required) for f, label, required, _ in FIELDS[dataset]}
    clean = {}
    for field, column in mapping.items():
        if column in (None, ''):
            continue
        if field not in known:
            raise MappingError(f'Невідоме поле «{field}».')
        if column not in columns:
            raise MappingError(f'У таблиці немає колонки «{column}».')
        clean[field] = column
    used = list(clean.values())
    if len(used) != len(set(used)):
        raise MappingError('Одна колонка може відповідати лише одному полю.')
    missing = [label for field, (label, required) in known.items() if required and field not in clean]
    if missing:
        raise MappingError('Оберіть колонки для обов’язкових полів: ' + ', '.join(missing) + '.')
    return clean


# Accepted number shapes, checked on the whole cell. Anything else (mixed or broken grouping, exponents,
# letters) is rejected, never reinterpreted as another number.
_GAP = '[   ]'
_NUMBER = (
    (re.compile(r'-?\d+(?:[.,]\d+)?'), None),                                    # 1234 · 1234,50 · 1234.50
    (re.compile(r'-?\d{1,3}(?:' + _GAP + r'\d{3})+(?:[.,]\d+)?'), _GAP),        # 1 234 567,50
    (re.compile(r'-?\d{1,3}(?:,\d{3})+(?:\.\d+)?'), ','),                         # 1,234,567.50
    (re.compile(r'-?\d{1,3}(?:\.\d{3})+(?:,\d+)?'), r'\.'),                       # 1.234.567,50
)
_CURRENCY_MARK = re.compile(r'(?is)(?:₴\s*)?(.*?)(?:\s*(?:грн\.?|₴|uah))?')


def _decimal(text, places):
    # DOTALL fullmatch always matches; a cell with an embedded newline then fails every number shape.
    mark = _CURRENCY_MARK.fullmatch(text.strip())
    if not mark:
        raise ValueError('не число')
    raw = mark.group(1).strip()
    if len(raw) > 40:
        raise ValueError('не число')
    for shape, grouping in _NUMBER:
        if shape.fullmatch(raw):
            plain = re.sub(grouping, '', raw) if grouping else raw
            break
    else:
        raise ValueError('не число')
    value = Decimal(plain.replace(',', '.'))
    if abs(value) > MAX_MONEY:
        raise ValueError('число поза межами')
    exponent = value.as_tuple().exponent
    if -exponent > places:
        raise ValueError(f'більше {places} знаків після коми')
    return format(value.quantize(Decimal(1).scaleb(-places)), 'f')


def _date(text):
    text = text.strip()
    for fmt in ('%Y-%m-%d', '%d.%m.%Y', '%d/%m/%Y', '%d.%m.%y'):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    raise ValueError('незрозуміла дата')


def _datetime(text):
    text = text.strip()
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M', '%d.%m.%Y %H:%M:%S', '%d.%m.%Y %H:%M'):
        try:
            # Seconds are kept when the source has them: a call log must not lose its exact time.
            return datetime.strptime(text, fmt).isoformat(timespec='seconds' if '%S' in fmt else 'minutes')
        except ValueError:
            continue
    return _date(text)


def _value(kind, text):
    if kind == 'text':
        return text.strip()
    if kind == 'money':
        return _decimal(text, 2)
    if kind == 'quantity':
        return _decimal(text, 3)
    if kind == 'date':
        return _date(text)
    if kind == 'datetime':
        return _datetime(text)
    if kind == 'currency':
        value = CURRENCIES.get(text.strip().upper())
        if value is None:
            raise ValueError('невідома валюта')
        return value
    if kind == 'direction':
        value = DIRECTIONS.get(text.strip().lower())
        if value is None:
            raise ValueError('незрозумілий напрям')
        return value
    raise ValueError('невідомий тип')


def normalize(dataset, columns, rows, mapping):
    """Read mapped rows. Empty optional cells become None; anything unreadable rejects the whole row."""
    spec = {f: (label, required, kind) for f, label, required, kind in FIELDS[dataset]}
    index = {column: i for i, column in enumerate(columns)}
    accepted, rejected = [], []
    for number, row in enumerate(rows, start=2):  # row 1 is the header in the source table
        record, problem = {}, None
        for field, column in mapping.items():
            label, required, kind = spec[field]
            text = row[index[column]] if index[column] < len(row) else ''
            if not str(text).strip():
                if required:
                    problem = f'порожнє поле «{label}»'
                    break
                record[field] = None
                continue
            try:
                record[field] = _value(kind, str(text))
            except ValueError as exc:
                problem = f'«{label}»: {exc}'
                break
        if problem:
            rejected.append({'row': number, 'reason': problem})
            continue
        if 'currency' in spec and record.get('currency') is None:
            record['currency'] = 'UAH'
        accepted.append(record)
    return {'rows': accepted, 'rejected': rejected[:50], 'accepted': len(accepted), 'total': len(rows)}
