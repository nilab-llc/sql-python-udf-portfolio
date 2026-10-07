import datetime
import tempfile
import unittest
from pathlib import Path
from portfolio import generate, normalize_device, run


class PortfolioTests(unittest.TestCase):
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
