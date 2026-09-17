"""Two bounded N01 regressions from independent A07 writer review.

Separate from the unchanged initial 15 methods. Import only their helpers via
the module object, so unittest does not discover inherited/imported test cases.
Run only on a NEW verification database.
"""
import json
from django.core.exceptions import ValidationError
from django.db import transaction
from erp.test_concurrency import ERPConcurrencyBase as _FixtureBase
from finance.commands import save_transaction
import erp.test_value_boundaries as _boundaries


class ExtremeDecimalBoundaryTests(_FixtureBase):
    post_json = _boundaries.A07BoundaryTests.post_json
    assert_same_physical = _boundaries.A07BoundaryTests.assert_same_physical
    reject = _boundaries.A07BoundaryTests.reject

    def test_finite_huge_exponent_is_domain_refusal_in_erp_writers(self):
        for action, field in (('opening', 'quantity'), ('opening', 'unit_cost'), ('payment', 'amount')):
            fixture, original = self.prepare(action, 'EUR')
            for value in ('1e9999999', '-1e9999999'):
                self.reject({**original, field: value}, 'N01/extreme/' + field + '/' + value)

    def test_finite_huge_exponent_is_finance_validation_error_with_zero_effect(self):
        for currency in ('EUR', 'USD', 'UAH'):
            for value in ('1e9999999', '-1e9999999'):
                with self.subTest(currency=currency, amount=value):
                    with transaction.atomic():
                        try:
                            before = _boundaries.physical_state()
                            error = None
                            try:
                                save_transaction(changes={
                                    'direction': 'out', 'amount': value, 'currency': currency,
                                    'date': '2026-09-11', 'description': 'Синтетичне значення A07',
                                    'category': 'other'}, actor=self.user,
                                    operation_id='a07-extreme-' + currency)
                            except Exception as exc:
                                error = exc
                            after = _boundaries.physical_state()
                            print('A07_EXTREME_FINANCE ' + json.dumps({
                                'currency': currency, 'amount': value,
                                'exception': type(error).__name__ if error else None,
                                'changed_tables': [key for key in before if before[key] != after[key]],
                            }))
                            with self.subTest(check='domain_refusal'):
                                self.assertIsInstance(error, ValidationError)
                            with self.subTest(check='zero_effect'):
                                self.assert_same_physical(before, after, 'Invalid amount changed financial history/intent')
                        finally:
                            transaction.set_rollback(True)
