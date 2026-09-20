"""Persistent network commands, executed inside the existing ERP mutex/approval path."""
from copy import deepcopy
from decimal import Decimal as D, InvalidOperation
import re
from django.utils import timezone
from branches.models import Branch
from operations.models import Invoice
from .models import Location, Lot, StockTransfer, PaymentRetention, SalesOrder, Purchase
from .balances import exact, invoice_settlement, settlement_strings

SCHEMAS={
    'order_network':('order_id reason','fulfillment_location_id destination_country'),
    'purchase_network':('purchase_id reason','destination_id origin_country'),
    'location_update':('location_id reason','branch_id address lat lng'),
    'transfer_dispatch':('lot_id quantity location_id code reason','due_date'),
    'transfer_receive':('transfer_id code reason',''),
    'hold_payment':('invoice_id amount code reason',''),
    'release_payment':('retention_id reason',''),
}
MODELS=(StockTransfer,PaymentRetention)


def clean_metadata(action,data):
    d=dict(data)
    if action in SCHEMAS and (not isinstance(d.get('reason'),str) or not d['reason'].strip()):
        raise ValueError('Потрібна змістовна підстава дії.')
    for name in ('origin_country','destination_country'):
        if name in d and (not isinstance(d[name],str) or (d[name] and not re.fullmatch('[A-Z]{2}',d[name]))):
            raise ValueError('Країна: дволітерний код великими латинськими літерами або порожнє значення.')
    if 'address' in d and (not isinstance(d['address'],str) or len(d['address'])>300):
        raise ValueError('Адреса: текст до 300 символів.')
    if ('lat' in d)!=('lng' in d):raise ValueError('Широта й довгота задаються разом.')
    if 'lat' in d:
        if (d['lat'] is None)!=(d['lng'] is None):raise ValueError('Координати задаються або очищаються разом.')
        for name,limit in (('lat',90),('lng',180)):
            if d[name] is None:continue
            if isinstance(d[name],bool):raise ValueError('Некоректні координати.')
            try:value=D(str(d[name]))
            except (InvalidOperation,ValueError):raise ValueError('Некоректні координати.')
            if not value.is_finite() or abs(value)>limit or value.as_tuple().exponent < -6:
                raise ValueError('Координати поза межами або точніші за 6 знаків.')
            d[name]=format(value,'f')
    if action=='location_update' and not set(d).intersection({'branch_id','address','lat','lng'}):
        raise ValueError('Вкажіть метадані точки для зміни.')
    metadata={'order_network':{'fulfillment_location_id','destination_country'},'purchase_network':{'destination_id','origin_country'}}
    if action in metadata and not set(d).intersection(metadata[action]):raise ValueError('Вкажіть метадані замовлення для зміни.')
    return d


def check_location_metadata(data):
    if data.get('branch_id') is not None:Branch.objects.get(pk=data['branch_id'])


@exact
def apply(action,d,role):
    from .service import free,usable,move,newlot
    if action in ('location_update','order_network','purchase_network','hold_payment','release_payment') and role!='ceo':
        raise PermissionError('Цю зміну погоджує керівник.')
    if action in ('order_network','purchase_network'):
        sale=action=='order_network';model=SalesOrder if sale else Purchase
        row=model.objects.get(pk=d['order_id' if sale else 'purchase_id'])
        location='fulfillment_location_id' if sale else 'destination_id';country='destination_country' if sale else 'origin_country'
        if location in d and d[location]!=getattr(row,location):
            if (sale and row.lines.filter(shipped__gt=0).exists()) or (not sale and row.received>0):raise ValueError('Точку виконаних рухів не можна перепризначати; потрібне окреме погоджене коригування.')
            if d[location] is not None:Location.objects.get(pk=d[location])
        fields=[name for name in (location,country) if name in d]
        for name in fields:setattr(row,name,d[name])
        row.save(update_fields=fields)
        return {'order_id' if sale else 'purchase_id':row.pk,'updated_fields':fields}
    if action=='location_update':
        row=Location.objects.get(pk=d['location_id']);check_location_metadata(d)
        fields=[name for name in ('branch_id','address','lat','lng') if name in d]
        for name in fields:setattr(row,name,d[name])
        row.save(update_fields=fields)
        return {'location_id':row.pk,'code':row.code,'updated_fields':fields}
    if action=='transfer_dispatch':
        lot=Lot.objects.select_related('item','location').get(pk=d['lot_id'])
        destination=Location.objects.get(pk=d['location_id']);qty=D(d['quantity'])
        if destination.pk==lot.location_id:raise ValueError('Потрібна інша точка призначення.')
        if not usable(lot) or qty>free(lot):raise ValueError('Недостатньо придатного вільного залишку для відправлення.')
        if StockTransfer.objects.filter(code=d['code']).exists():raise ValueError('Код переміщення вже використано.')
        movement=move(lot,-qty,'transfer_dispatch',d['code'],d['reason'])
        row=StockTransfer.objects.create(code=d['code'],source_lot=lot,source_location=lot.location,destination=destination,
            item=lot.item,quantity=qty,revision=lot.revision,documents=deepcopy(lot.documents),unit_cost=lot.unit_cost,
            total_cost=movement.cost,currency=lot.currency,dispatch_movement=movement,reason=d['reason'],due_date=d.get('due_date'))
        return {'transfer_id':row.pk,'lot_id':lot.pk,'source_location_id':row.source_location_id,
            'destination_id':destination.pk,'quantity':str(qty),'status':row.status,'currency':row.currency}
    if action=='transfer_receive':
        row=StockTransfer.objects.select_related('item','destination').get(pk=d['transfer_id'])
        if row.status!='in_transit':raise ValueError('Це переміщення вже прийнято.')
        lot=newlot(d['code'],row.item,row.destination,row.quantity,row.unit_cost,row.currency,row.revision,
            deepcopy(row.documents),'transfer_receive',row.code,reason=d['reason'],_source_cost=row.total_cost)
        # Arrival is not a quality approval. The normal inspection command must release the lot.
        row.received_lot=lot;row.receipt_movement=lot.movements.get(kind='transfer_receive')
        row.status='received';row.received_at=timezone.now()
        row.save(update_fields=['received_lot','receipt_movement','status','received_at'])
        return {'transfer_id':row.pk,'lot_id':lot.pk,'destination_id':row.destination_id,'quantity':str(row.quantity),
            'status':row.status,'quality':lot.quality,'currency':row.currency}
    if action=='hold_payment':
        invoice=Invoice.objects.get(pk=d['invoice_id']);amount=D(d['amount'])
        if amount>invoice_settlement(invoice)['collectible']:raise ValueError('Утримання перевищує вільну до оплати суму рахунку.')
        row=PaymentRetention.objects.create(code=d['code'],invoice=invoice,amount=amount,currency=invoice.currency,reason=d['reason'])
        return {'retention_id':row.pk,'invoice_id':invoice.pk,'amount':str(amount),'status':row.status,'settlement':settlement_strings(invoice)}
    if action=='release_payment':
        row=PaymentRetention.objects.select_related('invoice').get(pk=d['retention_id'])
        if row.status!='held':raise ValueError('Це утримання вже знято.')
        row.status='released';row.release_reason=d['reason'];row.released_at=timezone.now()
        row.save(update_fields=['status','release_reason','released_at'])
        return {'retention_id':row.pk,'invoice_id':row.invoice_id,'status':row.status,'settlement':settlement_strings(row.invoice)}
    raise ValueError('Невідома мережева дія.')
