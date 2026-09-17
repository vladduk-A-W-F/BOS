"""Shared effective quantities and invoice settlement; gross history is untouched."""
from decimal import Decimal as D,localcontext,ROUND_HALF_EVEN
from fractions import Fraction
from functools import wraps
from django.db.models import Sum
from .models import OrderCancellation,SalesLine,Purchase,InvoiceAdjustment


def exact(fn):
    @wraps(fn)
    def wrapped(*args,**kwargs):
        with localcontext() as context:
            context.prec=50;context.rounding=ROUND_HALF_EVEN
            return fn(*args,**kwargs)
    return wrapped


def money(value):
    value=Fraction(value)*100;whole,remainder=divmod(value.numerator,value.denominator)
    if remainder*2>value.denominator or (remainder*2==value.denominator and whole%2):whole+=1
    return D((1 if whole<0 else 0,tuple(int(c) for c in str(abs(whole))),-2))


def quantity_text(value):return format(value,'.3f')
def money_text(value):return format(value,'.2f')


def cancelled_quantity(obj):
    field='line' if isinstance(obj,SalesLine) else 'purchase' if isinstance(obj,Purchase) else None
    if field is None:raise TypeError('Потрібна позиція продажу або закупівля.')
    return OrderCancellation.objects.filter(**{field:obj}).aggregate(value=Sum('quantity'))['value'] or D(0)


@exact
def sales_open(line):
    value=line.quantity-line.shipped-cancelled_quantity(line)
    if value<0:raise ValueError('Історія скасувань перевищує потребу продажу.')
    return value


@exact
def purchase_open(po):
    value=po.quantity-po.received-cancelled_quantity(po)
    if value<0:raise ValueError('Історія скасувань перевищує залишок закупівлі.')
    return value


@exact
def request_allocated(request):
    return sum((po.quantity-cancelled_quantity(po) for po in Purchase.objects.filter(request=request)),D(0))


def active_credits(invoice=None):
    rows=InvoiceAdjustment.objects.filter(kind='credit',reversal__isnull=True)
    return rows.filter(invoice=invoice) if invoice is not None else rows


@exact
def invoice_settlement(invoice):
    credit=sum((row.total for row in active_credits(invoice)),D(0));net=invoice.amount-credit
    if net<0:raise ValueError('Погоджені кредити перевищують первісний рахунок.')
    return {'effective_credit':credit,'net_amount':net,'receivable':max(net-invoice.paid,D(0)),'customer_credit':max(invoice.paid-net,D(0))}


def settlement_strings(invoice):return {key:money_text(value) for key,value in invoice_settlement(invoice).items()}
