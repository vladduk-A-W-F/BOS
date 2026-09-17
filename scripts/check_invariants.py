"""Five mandatory invariants on reproducible random operation sequences."""
import argparse
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal as D
import json
import os
from pathlib import Path
import random
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ['DJANGO_SETTINGS_MODULE'] = 'demo_settings'
os.environ['BOS_DATA_MODE'] = 'demo'
import django
from django.conf import settings
from check_support import configure, prove_database
configure(settings)
django.setup()
from django.contrib.auth.models import User, Group
from django.core.management import call_command
from django.db import connection, transaction
from django.db.models import Sum
from django.test import Client
from employees.models import Employee
from finance.models import Salary, Transaction
from erp.models import Item, Location, Lot, Movement, Production, Reservation, Event
from erp import service as erp


def post(client, path, payload):
    return client.post(path, payload, content_type='application/json',
                       HTTP_X_CSRFTOKEN=client.cookies['csrftoken'].value)


def client():
    value = Client(enforce_csrf_checks=True)
    value.get('/api/operations/status/')
    return value


def role_client(role):
    user = User.objects.create_user(username='inv-' + role, password='synthetic-local-only')
    user.groups.add(Group.objects.get_or_create(name=role)[0])
    value = client()
    assert value.login(username=user.username, password='synthetic-local-only')
    value.get('/api/operations/status/')
    return value


def discloses(value, forbidden, markers):
    if isinstance(value, dict):
        return bool(set(value) & forbidden) or any(discloses(x, forbidden, markers) for x in value.values())
    if isinstance(value, list):
        return any(discloses(x, forbidden, markers) for x in value)
    return isinstance(value, str) and any(marker in value for marker in markers)


def balances():
    # Independent oracle: aggregate persisted movements, not dispatch results.
    lots = list(Lot.objects.all())
    for lot in lots:
        total = lot.movements.aggregate(n=Sum('quantity'))['n'] or D(0)
        assert lot.quantity == total, ('movement_balance', lot.code, str(lot.quantity), str(total))
        assert lot.quantity >= 0, ('negative_lot', lot.code, str(lot.quantity))
        assert 0 <= erp.reserved(lot) <= lot.quantity, ('reserve_bounds', lot.code)
    for item in Item.objects.all():
        total = Movement.objects.filter(lot__item=item).aggregate(n=Sum('quantity'))['n'] or D(0)
        quantity = Lot.objects.filter(item=item).aggregate(n=Sum('quantity'))['n'] or D(0)
        assert quantity == total, ('item_balance', item.code)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runs', type=int, default=1000)
    parser.add_argument('--seed', type=int, default=20260911)
    args = parser.parse_args()
    if args.runs < 1000 or not __debug__:
        raise ValueError('Кожний інваріант потребує щонайменше 1000 прогонів без -O.')
    prove_database(); call_command('migrate', verbosity=0)
    rng = random.Random(args.seed)
    owner = Employee.objects.create(full_name='Синтетичний оператор інваріантів',
                                    phone='+000000000', email='synthetic@example.invalid')
    area = Location.objects.create(code='INV-AREA', name='Тестова дільниця', kind='production')
    other = Location.objects.create(code='INV-OTHER', name='Тестова комірка')
    raw = Item.objects.create(code='INV-RAW', name='Синтетичний матеріал', kind='material')
    product = Item.objects.create(code='INV-PRODUCT', name='Синтетичний виріб', method='make')
    counts = Counter(); outcomes = Counter(); rows = []
    for run in range(args.runs):
        with transaction.atomic():
            job = Production.objects.create(code='INV-JOB', item=product, quantity=10,
                revision='A', bom=[{'item_id': raw.id, 'quantity': '1'}], routing=[],
                location=area, owner=owner, due_date='2026-09-30', status='running')
            lot = erp.newlot('INV-RAW-LOT', raw, area, D(rng.randint(10, 50)),
                             D(rng.randint(1, 1000)) / 100, 'EUR', 'A', {}, 'opening', 'INV-OPEN')
            lot.quality = 'approved'; lot.save(update_fields=['quality'])
            # Include the original class of defect in every random sequence.
            for amount in (5, 5):
                erp.dispatch({'action': 'erp_reserve', 'lot_id': lot.id,
                              'production_id': job.id, 'quantity': str(amount)})
            balances()
            for step in range(rng.randint(8, 16)):
                action = rng.choice(('reserve', 'release', 'finish', 'adjust', 'transfer', 'quality'))
                lot = rng.choice(list(Lot.objects.filter(item=raw)))
                quantity = str(rng.randint(1, 12))
                if action == 'reserve':
                    payload = {'lot_id': lot.id, 'production_id': job.id, 'quantity': quantity}
                elif action == 'release':
                    reservation = rng.choice(list(Reservation.objects.filter(production=job)))
                    payload = {'reservation_id': reservation.id, 'quantity': quantity}
                elif action == 'finish':
                    payload = {'production_id': job.id, 'quantity': quantity, 'code': f'INV-OUT-{step}',
                               'location_id': area.id, 'labor_cost': str(rng.randint(0, 100))}
                elif action == 'adjust':
                    payload = {'lot_id': lot.id, 'delta': str(rng.randint(-60, 20)), 'reason': 'Синтетична перевірка'}
                elif action == 'transfer':
                    payload = {'lot_id': lot.id, 'quantity': quantity, 'code': f'INV-MOVE-{step}',
                               'location_id': other.id if lot.location_id == area.id else area.id,
                               'reason': 'Синтетичне переміщення'}
                else:
                    payload = {'lot_id': lot.id, 'result': rng.choice(('approved', 'blocked')),
                               'inspector_id': owner.id, 'note': 'Синтетична перевірка'}
                before = erp.fingerprint()
                try:
                    erp.dispatch({'action': 'erp_' + action, **payload}, role='ceo')
                    outcomes[action + ':applied'] += 1
                except ValueError:
                    assert erp.fingerprint() == before, ('partial_write_on_rejection', run, step, action)
                    outcomes[action + ':rejected'] += 1
                balances(); counts['stock_steps'] += 1
            transaction.set_rollback(True)
        counts['movement_balance'] += 1; counts['nonnegative_stock'] += 1
        if (run + 1) % 250 == 0:
            print(f'Склад: {run + 1}/{args.runs}', flush=True)
    for run in range(args.runs):
        with transaction.atomic():
            amount = D(rng.randint(1, 1000000)) / 100
            currency = rng.choice(('EUR', 'USD', 'UAH'))
            salary = Salary.objects.create(employee=owner, amount=amount, currency=currency,
                                            period_year=2026, period_month=rng.randint(1, 12))
            stale = Salary.objects.get(pk=salary.id)
            tx_ids = []
            for _ in range(rng.randint(2, 5)):
                paid, tx = rng.choice((salary, stale)).mark_paid('2026-09-11')
                tx_ids.append(tx.id)
                assert tx.amount == amount and tx.currency == currency and tx.salary_record.id == salary.id
                assert tx.direction == 'out' and tx.category == 'salary'
                assert Transaction.objects.count() == 1 and paid.transaction_id == tx.id
            assert len(set(tx_ids)) == 1
            transaction.set_rollback(True)
        counts['one_salary_expense'] += 1
    print(f'Виплати: {args.runs}/{args.runs}', flush=True)
    ceo = role_client('ceo')
    for run in range(args.runs):
        with transaction.atomic():
            payload = {'action': 'erp_opening', 'code': 'INV-REPLAY', 'item_id': raw.id,
                'location_id': area.id, 'quantity': str(rng.randint(1, 100)),
                'unit_cost': str(D(rng.randint(1, 10000)) / 100),
                'currency': rng.choice(('EUR', 'USD', 'UAH')), 'revision': 'A'}
            preview = post(ceo, '/api/erp/preview/', payload)
            assert preview.status_code == 200, ('preview', preview.status_code)
            confirmation = {'proposal_id': preview.json()['id'], 'confirmed': True}
            first = post(ceo, '/api/operations/confirm/', confirmation)
            assert first.status_code == 200, ('confirm', first.status_code)
            receipt = first.json(); before = (erp.fingerprint(), Event.objects.count())
            # Interleave another accepted action before replay of the old ID.
            erp.dispatch({'action': 'erp_adjust', 'lot_id': receipt['lot_id'],
                          'delta': str(rng.randint(0, 10)), 'reason': 'Наступна синтетична дія'}, role='ceo')
            before = (erp.fingerprint(), Event.objects.count())
            for _ in range(rng.randint(1, 4)):
                again = post(ceo, '/api/operations/confirm/', confirmation)
                assert again.status_code == 200 and again.json() == receipt
                assert (erp.fingerprint(), Event.objects.count()) == before
                counts['replay_requests'] += 1
            transaction.set_rollback(True)
        counts['proposal_replay'] += 1
    print(f'Повторні погодження: {args.runs}/{args.runs}', flush=True)
    # Policy accepted in ACCESS_AUDIT_UA: salaries only CEO; personnel fields
    # absent from the minimal manager/observer directory. Never fake this gate.
    salary = Salary.objects.create(employee=owner, amount='100.00', currency='UAH', period_year=2026,
                                    period_month=1, notes='INV-SALARY-PRIVATE-MARKER')
    contexts = {'anonymous': client()}
    for role in ('manager', 'observer'):
        contexts[role] = role_client(role)
    paths = ('/api/salaries/', f'/api/salaries/{salary.id}/', '/api/salaries.json', f'/api/employees/{owner.id}/')
    control = ceo.get('/api/salaries/')
    assert control.status_code == 200 and b'100.00' in control.content, 'Позитивний контроль справжніх синтетичних даних'
    failures = 0; samples = []; role_coverage = Counter()
    for run in range(args.runs):
        role = rng.choice(tuple(contexts)); order = rng.sample(paths, len(paths))
        bad = []
        for path in order:
            response = contexts[role].get(path)
            role_coverage[role + ':' + path] += 1
            denied = response.status_code in (401, 403)
            forbidden = ({'birthday', 'phone', 'email'} if '/employees/' in path else
                         {'amount', 'salary', 'salary_amount', 'payment_date', 'period_year', 'period_month', 'transaction'})
            content = json.loads(response.content) if response.get('Content-Type', '').startswith('application/json') else response.content.decode('utf-8', errors='replace')
            leaked = discloses(content, forbidden, ('INV-SALARY-PRIVATE-MARKER', 'synthetic@example.invalid', '+000000000'))
            if '/employees/' in path and role != 'anonymous' and response.status_code == 200:
                denied = not leaked
            if not denied or leaked:
                bad.append({'path': path, 'status': response.status_code})
        if bad:
            failures += 1
            if len(samples) < 6: samples.append({'run': run, 'role': role, 'forbidden_responses': bad})
        counts['role_access'] += 1
    for key in ('movement_balance', 'nonnegative_stock', 'one_salary_expense', 'proposal_replay', 'role_access'):
        rows.append({'invariant': key, 'runs': counts[key],
                     'status': 'ПОМИЛКА' if key == 'role_access' and failures else 'ПРОЙДЕНО'})
    report = {'gate': 3, 'date': datetime.now(timezone.utc).isoformat(), 'backend': connection.vendor,
              'seed': args.seed, 'minimum_runs': 1000, 'results': rows, 'counts': dict(counts),
              'operation_outcomes': dict(outcomes), 'role_failed_sequences': failures,
              'role_samples': samples, 'role_coverage': dict(role_coverage),
              'complete': all(x['status'] == 'ПРОЙДЕНО' and x['runs'] >= 1000 for x in rows),
              'scope': 'Синтетичні випадкові складські/зарплатні/HTTP-послідовності. Повний обхід маршрутів — окремий критерій 4. A03/A04 перевіряються реальними обліковими записами й поточними правами.'}
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
    return 0 if report['complete'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
