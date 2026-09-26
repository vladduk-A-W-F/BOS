"""Additional isolated audit: rollback, repeat reservations and migration limits."""
import contextlib, io, json, hashlib
from pathlib import Path

with contextlib.redirect_stdout(io.StringIO()):
    import plan_data_races as b
from erp import service as s
from erp.models import Production, Reservation, OperatorEntry, Lot, Movement, Event, SalesLine
from operations.models import ActionProposal, Configuration, Invoice
from operations import service as approvals
from django.utils import timezone
from django.db.models import Sum
from datetime import timedelta
from types import SimpleNamespace

out = {}
b.fresh('finish_repeat_lot')
material = b.initial_lot(b.raw, b.dest, 'RAW-LOT')
job = Production.objects.create(code='MO', item=b.fg, quantity='10', revision='A', bom=[{'item_id': b.raw.pk, 'quantity': '1'}], routing=[{'name': 'Виготовлення'}], location=b.dest, owner=b.emp, due_date='2026-09-20', status='planned')
for _ in range(2):
    s.dispatch({'action': 'erp_reserve', 'lot_id': material.pk, 'production_id': job.pk, 'quantity': '5'}, role='ceo')
s.dispatch({'action': 'erp_start', 'production_id': job.pk}, role='ceo')
s.dispatch({'action': 'erp_operator', 'production_id': job.pk, 'operation': 'Виготовлення', 'operator_id': b.emp.pk, 'result': 'done', 'minutes': 1, 'defects': '0'}, role='ceo')
result = s.dispatch({'action': 'erp_finish', 'production_id': job.pk, 'quantity': '10', 'code': 'OUTPUT', 'location_id': b.loc.pk, 'labor_cost': '0'}, role='ceo')
material.refresh_from_db();job.refresh_from_db()
out['finish_same_lot_two_reservations'] = {'status': 'succeeded', 'source_quantity': str(material.quantity), 'source_movement_total': str(material.movements.aggregate(n=Sum('quantity'))['n']), 'source_reserved': str(s.reserved(material)), 'produced': str(job.produced), 'integrity_errors': b.integrity()}
assert material.quantity == 5 and material.movements.aggregate(n=Sum('quantity'))['n'] == 0

b.fresh('rollback_after_move')
lot = b.initial_lot()
payload = {'action': 'erp_transfer', 'lot_id': lot.pk, 'quantity': '7', 'location_id': b.dest.pk, 'code': lot.code, 'reason': 'Тест відкоту'}
class Session(dict):
    session_key = 'audit-session'
request = SimpleNamespace(session=Session(bos_role='ceo'))
p = ActionProposal.objects.create(session_key=request.session.session_key, role='ceo', payload=payload, fingerprint=s.fingerprint(), expires_at=timezone.now()+timedelta(minutes=5))
before = {'fingerprint': s.fingerprint(), 'events': Event.objects.count(), 'movements': Movement.objects.count(), 'mutex': Configuration.objects.get(key='erp_write').value}
try:
    approvals.execute(request, p.pk)
    raise AssertionError('Expected IntegrityError on duplicate destination lot code')
except Exception as e:
    assert type(e).__name__ == 'IntegrityError', (type(e).__name__, str(e))
    p.refresh_from_db()
    after = {'fingerprint': s.fingerprint(), 'events': Event.objects.count(), 'movements': Movement.objects.count(), 'mutex': Configuration.objects.get(key='erp_write').value}
    out['rollback_after_move'] = {'exception': type(e).__name__, 'before_equals_after': before == after, 'proposal_receipt': p.receipt, 'integrity_errors': b.integrity()}
    assert before == after and p.receipt is None

# SCHEMAS allows <=60-char erp_invoice codes; actual Invoice column is varchar(30).
b.fresh('invoice_code_31')
line = b.order_line();line.shipped = 10;line.save()
result = s.dispatch({'action': 'erp_invoice', 'order_id': line.order_id, 'code': 'I'*31, 'due_date': '2026-10-01'}, role='ceo')
invoice = Invoice.objects.get(pk=result['invoice_id'])
out['sqlite_invoice_code_over_model_limit'] = {'status': 'succeeded', 'stored_length': len(invoice.code), 'model_max_length': Invoice._meta.get_field('code').max_length}
assert len(invoice.code) == 31

out['original_db_unchanged'] = b.before_hash == hashlib.sha256((b.ROOT / 'db.sqlite3').read_bytes()).hexdigest()
print(json.dumps(out, ensure_ascii=False, indent=2))
