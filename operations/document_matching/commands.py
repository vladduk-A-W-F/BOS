"""Strict client intent for the supplier-invoice registration command."""
import re
from . import contract

ACTION='erp_register_supplier_invoice'
FIELDS={'action','document_id','purchase_id','supplier_id','item_id','source_sha256'}

def clean(payload):
    if type(payload) is not dict or set(payload)!=FIELDS or payload.get('action')!=ACTION:
        raise ValueError('Некоректний намір реєстрації рахунку постачальника.')
    result=dict(payload)
    for name in ('document_id','purchase_id','supplier_id','item_id'):
        try: contract.positive_id(result[name])
        except (KeyError,contract.ContractError): raise ValueError('Некоректний вибір для реєстрації рахунку.') from None
    if type(result['source_sha256']) is not str or not re.fullmatch(r'[0-9a-f]{64}',result['source_sha256']):
        raise ValueError('Потрібна точна ідентичність перевіреного джерела.')
    return result
