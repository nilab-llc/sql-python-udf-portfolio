import datetime
import csv
import shutil
import tempfile
import unittest
from pathlib import Path
from portfolio import ROOT, generate, normalize_device, run


class PortfolioTests(unittest.TestCase):
    def test_boundaries_rejections_and_tie_break(self):
        generate()
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            shutil.copy(ROOT / 'data' / 'customers.csv', folder)
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
                 ('invalid', None), ('device:A001junk', None)]
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
