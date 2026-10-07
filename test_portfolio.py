import datetime
import csv
import shutil
import tempfile
import unittest
from pathlib import Path
from portfolio import ROOT, generate, normalize_device, run


class PortfolioTests(unittest.TestCase):
    def test_numeric_identifiers_preserved_and_invalid_cast_rolls_back(self):
        import duckdb
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            tables = {
                'customers.csv': [['customer_id', 'plan'], ['001', 'basic']],
                'plan_history.csv': [['history_id', 'customer_id', 'plan', 'valid_from', 'valid_to'], [1, '001', 'basic', '2026-01-01', None]],
                'usage_events.csv': [['source_row', 'event_id', 'customer_id', 'occurred_at', 'received_at', 'megabytes', 'device_code'], [1, '0001', '001', '2026-10-01', '2026-10-02', 10, 'device:A001']],
            }
            for name, rows in tables.items():
                with (folder / name).open('w', newline='', encoding='utf-8') as file:
                    csv.writer(file).writerows(rows)
            db = folder / 'test.duckdb'
            self.assertEqual(run(db, folder)[0], [(datetime.date(2026, 10, 1), '001', 'basic', 1, 10, 0)])
            with duckdb.connect(str(db)) as connection:
                self.assertEqual(connection.execute('SELECT event_id FROM classified').fetchone()[0], '0001')
            tables['usage_events.csv'][1][5] = 'not-a-number'
            with (folder / 'usage_events.csv').open('w', newline='', encoding='utf-8') as file:
                csv.writer(file).writerows(tables['usage_events.csv'])
            with self.assertRaises(duckdb.ConversionException):
                run(db, folder)
            with duckdb.connect(str(db)) as connection:
                self.assertEqual(connection.execute('SELECT total_mb FROM daily_usage').fetchone()[0], 10)

    def test_temporal_join_boundaries_gaps_overlaps(self):
        generate()
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            shutil.copy(ROOT / 'data' / 'customers.csv', folder)
            with (folder / 'plan_history.csv').open('w', newline='', encoding='utf-8') as file:
                csv.writer(file).writerows([
                    ['history_id', 'customer_id', 'plan', 'valid_from', 'valid_to'],
                    [1, 'C001', 'basic', '2026-10-01 00:00:00', '2026-10-01 12:00:00'],
                    [2, 'C001', 'premium', '2026-10-01 12:00:00', None],
                    [3, 'C002', 'premium', '2026-10-01', None],
                    [4, 'C002', 'premium', '2026-10-01 12:00:00', None],
                ])
            with (folder / 'usage_events.csv').open('w', newline='', encoding='utf-8') as file:
                writer = csv.writer(file)
                writer.writerow(['source_row', 'event_id', 'customer_id', 'occurred_at', 'received_at', 'megabytes', 'device_code'])
                for index, customer, timestamp in [
                    (1, 'C001', '2026-09-30 23:59:59'),
                    (2, 'C001', '2026-10-01 00:00:00'),
                    (3, 'C001', '2026-10-01 11:59:59'),
                    (4, 'C001', '2026-10-01 12:00:00'),
                    (5, 'C001', '2026-10-02 12:00:00'),
                    (6, 'C002', '2026-10-01 12:00:00'),
                ]:
                    writer.writerow([index, str(index), customer, timestamp, '2026-10-03', 10, 'device:A001'])
            db = folder / 'test.duckdb'
            result, counts = run(db, folder)
            self.assertEqual(result, [
                (datetime.date(2026, 10, 1), 'C001', 'basic', 2, 20, 10),
                (datetime.date(2026, 10, 1), 'C001', 'premium', 1, 10, 10),
                (datetime.date(2026, 10, 2), 'C001', 'premium', 1, 10, 10),
            ])
            self.assertEqual(counts['classified'], counts['deduplicated'])
            self.assertEqual(counts['rejected_events'], 2)
            import duckdb
            with duckdb.connect(str(db)) as connection:
                self.assertEqual(connection.execute('SELECT event_id, rejection_reason, plan_match_count FROM rejected_events ORDER BY event_id').fetchall(),
                                 [('1', 'no_matching_plan', 0), ('6', 'ambiguous_plan', 2)])
            self.assertEqual(run(db, folder), (result, counts))

    def test_boundaries_rejections_and_tie_break(self):
        generate()
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            shutil.copy(ROOT / 'data' / 'customers.csv', folder)
            with (folder / 'plan_history.csv').open('w', newline='', encoding='utf-8') as file:
                csv.writer(file).writerows([['history_id','customer_id','plan','valid_from','valid_to'], [1,'C001','basic','2026-01-01',None]])
            rows = [
                (1, 'A', 'C001', '2026-10-01 08:59:59', '2026-10-02', 1, 'device:A001'),
                (2, 'B', 'C001', '2026-10-01 09:00:00', '2026-10-02', 2, 'device:A001'),
                (3, 'C', 'C001', '2026-10-01 17:59:59', '2026-10-02', 3, 'device:A001'),
                (4, 'D', 'C001', '2026-10-01 18:00:00', '2026-10-02', 4, 'device:A001'),
                (5, 'D', 'C001', '2026-10-01 18:00:00', '2026-10-02', 5, 'device:A001'),
                (6, None, 'C001', '2026-10-01', '2026-10-02', 1, 'device:A001'),
                (7, None, 'C001', '2026-10-01', '2026-10-02', 1, 'device:A001'),
                (8, 'E', 'C001', None, '2026-10-02', 1, 'device:A001'),
                (9, 'F', 'C001', '2026-10-01', '2026-10-02', -1, 'device:A001'),
                (10, 'G', 'C001', '2026-10-02', '2026-10-02', 0, 'device:A001'),
            ]
            with (folder / 'usage_events.csv').open('w', newline='', encoding='utf-8') as file:
                writer = csv.writer(file)
                writer.writerow(['source_row', 'event_id', 'customer_id', 'occurred_at', 'received_at', 'megabytes', 'device_code'])
                writer.writerows(rows)
            db = folder / 'test.duckdb'
            result, counts = run(db, folder)
            self.assertEqual(result, [
                (datetime.date(2026, 10, 1), 'C001', 'basic', 4, 11, 5),
                (datetime.date(2026, 10, 2), 'C001', 'basic', 1, 0, 0),
            ])
            self.assertEqual(counts['deduplicated'], 9)
            self.assertEqual(counts['rejected_events'], 4)
            import duckdb
            with duckdb.connect(str(db)) as connection:
                reasons = dict(connection.execute('SELECT rejection_reason, count(*) FROM rejected_events GROUP BY 1').fetchall())
            self.assertEqual(reasons, {'missing_event_id': 2, 'missing_timestamp': 1, 'negative_volume': 1})
            # A failed reload must preserve the successful previous database.
            with (folder / 'customers.csv').open('a', encoding='utf-8') as file:
                file.write('C001,basic\n')
            with self.assertRaises(duckdb.ConstraintException):
                run(db, folder)
            with duckdb.connect(str(db)) as connection:
                self.assertEqual(connection.execute('SELECT sum(total_mb) FROM daily_usage').fetchone()[0], 11)

    def test_udf_contract(self):
        cases = [('device:a001', 'A001'), ('{"device_id":"a002"}', 'A002'),
                 (None, None), ('{"device_id":12}', None), ('{broken', None),
                 ('invalid', None), ('device:A001junk', None),
                 ('device:A１２３', None), ('{"device_id":"A１２３"}', None)]
        for value, expected in cases:
            with self.subTest(value=value):
                self.assertEqual(normalize_device(value), expected)

    def test_exact_totals_quality_and_rerun(self):
        generate()
        with tempfile.TemporaryDirectory() as temp:
            db = Path(temp) / 'test.duckdb'
            first = run(db)
            second = run(db)
        self.assertEqual(first, second)
        result, counts = first
        self.assertEqual(result, [
            (datetime.date(2026, 10, 1), 'C001', 'basic', 8, 90, 90),
            (datetime.date(2026, 10, 1), 'C002', 'premium', 8, 80, 80),
        ])
        self.assertEqual(counts, {'usage_events': 20, 'deduplicated': 19,
                                  'classified': 19, 'rejected_events': 3})


if __name__ == '__main__':
    unittest.main()
