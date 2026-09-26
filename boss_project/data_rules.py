"""Portable value checks before SQL; historical data is never rewritten."""
import json
import math
from decimal import Decimal, InvalidOperation

from django.db import models


def text_value(value, *, path='value', maximum=None):
    if not isinstance(value, str):
        raise ValueError(f'{path}: потрібен текст.')
    if '\x00' in value or any(0xD800 <= ord(char) <= 0xDFFF for char in value):
        raise ValueError(f'{path}: нульовий символ або некоректна Unicode-послідовність.')
    if maximum is not None and len(value) > maximum:
        raise ValueError(f'{path}: максимум {maximum} символів.')
    return value


def portable_tree(value, *, path='value'):
    """Check decoded JSON/text without altering values, order or whitespace."""
    if isinstance(value, str):
        text_value(value, path=path)
    elif isinstance(value, dict):
        for key, item in value.items():
            text_value(key, path=path + '.key')
            portable_tree(item, path=path + '.' + key)
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            portable_tree(item, path=f'{path}[{index}]')
    elif isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f'{path}: число має бути скінченним.')
    return value


def strict_json_loads(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('JSON містить повторний ключ.')
            result[key] = value
        return result
    def constant(value):
        raise ValueError('JSON містить нескінченне або невизначене число.')
    return portable_tree(json.loads(raw, object_pairs_hook=pairs,
                                    parse_constant=constant))


def decimal_value(value, *, digits, places, path='value'):
    try:
        amount = Decimal(str(value))
    except (ValueError, TypeError, InvalidOperation):
        raise ValueError(f'{path}: потрібне число.')
    if not amount.is_finite():
        raise ValueError(f'{path}: число має бути скінченним.')
    # Compare exact Decimal values; no quantize/round operation can repair input.
    if amount.copy_abs() >= Decimal(10) ** (digits - places):
        raise ValueError(f'{path}: сума або кількість перевищує місткість поля.')
    if amount != amount.quantize(Decimal(1).scaleb(-places)):
        raise ValueError(f'{path}: дозволено до {places} знаків після коми.')
    return amount


def field_values(model, values):
    for field in model._meta.concrete_fields:
        key = field.attname
        if key not in values or values[key] is None:
            continue
        value = values[key]
        path = model._meta.label_lower + '.' + field.name
        if isinstance(field, (models.CharField, models.TextField)):
            text_value(value, path=path, maximum=field.max_length)
        elif isinstance(field, models.DecimalField):
            decimal_value(value, digits=field.max_digits,
                          places=field.decimal_places, path=path)
        elif isinstance(field, models.JSONField):
            portable_tree(value, path=path)
            try:
                json.dumps(value, allow_nan=False)
            except (TypeError, ValueError):
                raise ValueError(f'{path}: потрібне коректне JSON-значення.')
    return values
