"""Single local AR payment writer shared by manual and statement confirmations."""
from decimal import Decimal as D
from operations.models import Invoice
from .models import Event
from .balances import exact,invoice_settlement

@exact
def post_payment(invoice_id,amount,reference,*,role,log=False):
    invoice=Invoice.objects.get(pk=invoice_id);amount=D(str(amount))
    if not amount.is_finite() or amount<=0 or amount>invoice_settlement(invoice)['collectible']:raise ValueError('Оплата перевищує доступну суму з урахуванням утримань.')
    if not isinstance(reference,str) or not reference.strip() or Event.objects.filter(action='erp_payment',payload__reference=reference).exists():raise ValueError('Це посилання оплати вже зареєстровано.')
    invoice.paid+=amount;invoice.save()
    result={'invoice_id':invoice.id,'paid':str(invoice.paid),'note':'Локальний обліковий запис; банківська операція не виконується.'}
    if log:
        event=Event.objects.create(action='erp_payment',payload={'action':'erp_payment','invoice_id':invoice_id,'amount':str(amount),'reference':reference},result=result,role=role)
        result['erp_event_id']=event.pk
    return result
