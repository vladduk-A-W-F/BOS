"""Purchase source admission; called only by the existing locked ERP writer."""
from copy import deepcopy
from datetime import date, timedelta
from decimal import Decimal as D

from django.db.models import Sum

from operations.models import ProcurementRequest, SupplierQuote
from operations.private_storage import verified_document_bytes
from operations.service import as_of, newest
from .models import Purchase


def document_source(document):
    if document.status not in ('approved', 'supplier_quote') or newest(document.code).pk != document.pk:
        raise ValueError('Потрібна перевірена актуальна версія джерельного документа.')
    verified_document_bytes(document)
    return {'document_id':document.pk,'code':document.code,'revision':document.revision,
            'checksum':document.checksum}


def statement(value, label):
    if not isinstance(value, str) or not 3 <= len(value.strip()) <= 1000:
        raise ValueError(label + ': потрібне явне посилання або обґрунтування, 3–1000 символів.')
    return value.strip()


def purchase_source(data, item):
    """Bind user-entered fields to checked sources; do not infer item mapping.

The supplier confirmation is a manager's attestation, not independent external
verification. Calculated lead time cannot override that agreed date.
    """
    from .service import money_total, number
    data = dict(data)
    quote_id = data.pop('quote_id', None)
    confirmation = data.pop('supplier_confirmation', None)
    direct_reason = data.pop('direct_reason', None)
    quantity = D(data['quantity'])
    today = as_of()
    due = date.fromisoformat(data['due_date'])
    if due < today:
        raise ValueError('Погоджена дата поставки не може бути раніше дати поточного зрізу.')
    snapshot = {'source':'quote' if quote_id else 'direct', 'item_id':item.pk,
        'supplier_id':data['supplier_id'], 'unit':item.unit,
        'agreed_quantity':str(quantity), 'agreed_due_date':str(due),
        'revision':data['revision'], 'currency':data['currency'],
        'price':data['price'], 'extras':data.get('extras','0'), 'source_documents':{}}
    request = None
    if data.get('request_id'):
        request = ProcurementRequest.objects.select_related('document').get(pk=data['request_id'])
        if (item.document_id != request.document_id and item.code != request.part):
            raise ValueError('Номенклатура має явно відповідати коду або документу вимоги.')
        if item.unit != request.unit or item.revision != request.revision or data['revision'] != request.revision:
            raise ValueError('Одиниця або версія номенклатури не відповідає вимозі.')
        if data['currency'] != request.currency:
            raise ValueError('Валюта закупівлі має відповідати вимозі; автоматичної конвертації немає.')
        if due > request.required_by:
            raise ValueError('Погоджена дата поставки пізніше потрібної дати вимоги.')
        from .balances import request_allocated
        allocated = request_allocated(request)
        if quantity > D(request.quantity) - allocated:
            raise ValueError('Закупівля перевищує нерозподілену кількість вимоги.')
        snapshot.update(request_id=request.pk, request_code=request.code)
        snapshot['source_documents']['request'] = document_source(request.document)
    if quote_id:
        if direct_reason not in (None, ''):
            raise ValueError('Оберіть один шлях: пропозиція або пряма закупівля.')
        confirmation = statement(confirmation, 'Підтвердження кількості та строку постачальником')
        quote = SupplierQuote.objects.select_related('document').get(pk=quote_id)
        if request is None or quote.request_id != request.pk:
            raise ValueError('Пропозиція має належати явно зазначеній вимозі.')
        terms = quote.terms
        if not isinstance(terms, dict):
            raise ValueError('Умови пропозиції мають бути структурованими.')
        required = {'unit_price','setup','shipping','tooling','special_processes','currency','revision',
                    'lead_weeks','valid_until','moq','coating_included','material_certificate'}
        if not required.issubset(terms) or set(terms) - required - {'tax_basis'}:
            raise ValueError('Потрібні повні відомі умови пропозиції.')
        if terms.get('tax_basis', 'excluding_VAT') != 'excluding_VAT':
            raise ValueError('Підтримано лише явно погоджені суми без ПДВ; інша податкова база не реалізована.')
        if (type(terms['moq']) is not int or not 1 <= terms['moq'] <= 100000
                or quantity < terms['moq']):
            raise ValueError('Кількість менша за мінімальну партію або MOQ не підтверджено.')
        if type(terms['lead_weeks']) is not int or not 0 <= terms['lead_weeks'] <= 520:
            raise ValueError('Розрахунковий строк пропозиції некоректний.')
        if terms['coating_included'] is not True or terms['material_certificate'] is not True:
            raise ValueError('Не підтверджено обов’язкову комплектність пропозиції.')
        if not isinstance(terms['valid_until'], str) or date.fromisoformat(terms['valid_until']) < today:
            raise ValueError('Строк чинності пропозиції минув.')
        price = number(terms['unit_price'], places=2)
        extras = money_total(sum((number(terms[key], places=2)
                                 for key in ('setup','shipping','tooling','special_processes')), D('0')))
        if (quote.supplier_id != data['supplier_id'] or terms['currency'] != request.currency
                or terms['revision'] != request.revision or D(data['price']) != price
                or D(data.get('extras','0')) != extras):
            raise ValueError('Постачальник, версія, валюта або суми не відповідають вибраній пропозиції.')
        money_total(quantity * price + extras)
        snapshot.update(quote_id=quote.pk, quote_code=quote.code,
            original_terms=deepcopy(terms), supplier_confirmation=confirmation,
            confirmation_kind='manager_attestation',
            confirmation_notice='Це засвідчення менеджера; BoS не отримував незалежного підтвердження постачальника.',
            calculated_arrival=str(today + timedelta(weeks=terms['lead_weeks'])),
            checks={'original_bytes':'sha256_verified','source_terms':'server_checked'})
        snapshot['source_documents']['quote'] = document_source(quote.document)
        data['quote_id'] = quote.pk
        # Keep the stored numeric terms canonical and server-derived.
        data['price'], data['extras'] = str(price), str(extras)
        snapshot['price'], snapshot['extras'] = data['price'], data['extras']
    else:
        if confirmation not in (None, ''):
            raise ValueError('Посилання на підтвердження пропозиції потребує вибраної пропозиції.')
        snapshot['direct_reason'] = statement(direct_reason, 'Причина прямої закупівлі')
        money_total(quantity * D(data['price']) + D(data.get('extras','0')))
    data['approval_snapshot'] = snapshot
    return data


def source_document_ids(snapshot):
    """Stored source identity controls history even after mutable Quote changes."""
    if snapshot is None:
        return set()  # Historical PO without invented approval.
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get('source_documents'), dict):
        return None
    ids = set()
    for document in snapshot['source_documents'].values():
        if not isinstance(document, dict) or type(document.get('document_id')) is not int:
            return None
        ids.add(document['document_id'])
    return ids
