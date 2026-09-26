"""0.5: synthetic read-only reconciliation fixtures, never production data."""
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from scripts.reconcile_data import analyze, make_snapshot


def schema(db, erp=True):
    db.executescript('''
        CREATE TABLE finance_salary (id INTEGER PRIMARY KEY, employee_id INTEGER, amount NUMERIC,
          currency TEXT, status TEXT, transaction_id INTEGER, payment_date TEXT,
          period_year INTEGER, period_month INTEGER);
        CREATE TABLE finance_transaction (id INTEGER PRIMARY KEY, amount NUMERIC, currency TEXT,
          direction TEXT, category TEXT, date TEXT, description TEXT);
        CREATE TABLE employees_employee (id INTEGER PRIMARY KEY, full_name TEXT, phone TEXT, email TEXT);
        INSERT INTO employees_employee VALUES (1, 'PRIVATE_NAME_05', 'PRIVATE_PHONE_05', 'PRIVATE_EMAIL_05');
    ''')
    if erp:
        db.executescript('''
          CREATE TABLE erp_item (id INTEGER PRIMARY KEY, code TEXT, unit TEXT);
          INSERT INTO erp_item VALUES (1, 'SYNTHETIC', 'кг');
          CREATE TABLE erp_lot (id INTEGER PRIMARY KEY, item_id INTEGER, quantity NUMERIC, unit_cost NUMERIC, currency TEXT);
          CREATE TABLE erp_movement (id INTEGER PRIMARY KEY, lot_id INTEGER, quantity NUMERIC,
            kind TEXT, cost NUMERIC, line_id INTEGER, production_id INTEGER, purchase_id INTEGER);
          CREATE TABLE erp_reservation (id INTEGER PRIMARY KEY, lot_id INTEGER, quantity NUMERIC,
            line_id INTEGER, production_id INTEGER);
          CREATE TABLE operations_invoice (id INTEGER PRIMARY KEY, amount NUMERIC, paid NUMERIC, currency TEXT);
          CREATE TABLE erp_purchase (id INTEGER PRIMARY KEY, quantity NUMERIC, received NUMERIC);
          CREATE TABLE erp_production (id INTEGER PRIMARY KEY, quantity NUMERIC, produced NUMERIC);
        ''')
    db.commit()


class ReconciliationTests(unittest.TestCase):
    def database(self, erp=True):
        db=sqlite3.connect(':memory:'); self.addCleanup(db.close); schema(db, erp)
        return db

    def test_missing_erp_is_not_reported_as_full_reconciliation(self):
        report=analyze(self.database(False))
        self.assertFalse(report['complete'])
        self.assertTrue(any(x['classification']=='not_checked' and 'erp_' in json.dumps(x)
                            for x in report['findings']))

    def test_decimal_movements_do_not_create_binary_float_mismatch(self):
        db=self.database()
        db.executescript('''INSERT INTO erp_lot VALUES (1,1,0.3,10,'EUR');
          INSERT INTO erp_movement VALUES (1,1,0.1,'opening',1,NULL,NULL,NULL);
          INSERT INTO erp_movement VALUES (2,1,0.2,'opening',2,NULL,NULL,NULL);''')
        report=analyze(db)
        self.assertFalse(report['stop_required'])
        self.assertFalse(any(x['classification'] in ('discrepancy','confirmed_monetary') for x in report['findings']))

    def test_salary_expense_currency_mismatch_requires_human_decision(self):
        db=self.database()
        db.executescript('''INSERT INTO finance_transaction VALUES (1,100,'UAH','out','salary','2026-09-11','PRIVATE_DESCRIPTION_05');
          INSERT INTO finance_salary VALUES (1,1,100,'EUR','paid',1,'2026-09-11',2026,9);''')
        report=analyze(db)
        self.assertTrue(report['stop_required'])
        self.assertTrue(any(x['classification']=='confirmed_monetary' for x in report['findings']))
        for marker in ('PRIVATE_NAME_05','PRIVATE_PHONE_05','PRIVATE_EMAIL_05','PRIVATE_DESCRIPTION_05'):
            self.assertNotIn(marker,json.dumps(report,ensure_ascii=False))

    def test_equal_amount_date_orphans_are_candidates_not_confirmed_duplicates(self):
        db=self.database()
        db.executescript('''INSERT INTO finance_transaction VALUES (1,100,'UAH','out','salary','2026-09-11','A');
          INSERT INTO finance_transaction VALUES (2,100,'UAH','out','salary','2026-09-11','B');''')
        report=analyze(db)
        self.assertFalse(report['stop_required'])
        classes={x['classification'] for x in report['findings']}
        self.assertIn('unlinked',classes); self.assertIn('candidate',classes)
        self.assertNotIn('confirmed_monetary',classes)

    def test_stock_mismatch_with_recorded_cost_requires_human_decision(self):
        db=self.database()
        db.executescript('''INSERT INTO erp_lot VALUES (1,1,5,2,'EUR');
          INSERT INTO erp_movement VALUES (1,1,10,'opening',20,NULL,NULL,NULL);
          INSERT INTO erp_movement VALUES (2,1,-10,'consume',20,NULL,1,NULL);''')
        report=analyze(db)
        self.assertTrue(report['stop_required'])

    def test_snapshot_and_analysis_keep_source_and_copy_unchanged(self):
        with tempfile.TemporaryDirectory(prefix='bos-reconcile-test-') as folder:
            source=Path(folder)/'source.sqlite3'; dest=Path(folder)/'copy.sqlite3'
            with sqlite3.connect(source) as db: schema(db)
            before=hashlib.sha256(source.read_bytes()).hexdigest()
            make_snapshot(source,dest)
            copy_sha=hashlib.sha256(dest.read_bytes()).hexdigest()
            with sqlite3.connect(dest.as_uri()+'?mode=ro',uri=True) as copy: analyze(copy)
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(),before)
            self.assertEqual(hashlib.sha256(dest.read_bytes()).hexdigest(),copy_sha)
            with self.assertRaises((FileExistsError,ValueError)):
                make_snapshot(source,dest)

if __name__=='__main__': unittest.main()
