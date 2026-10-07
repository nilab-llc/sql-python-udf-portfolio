"""Synthetic telecom data demo. All identifiers and rules are fictional."""
import argparse
import csv
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def normalize_device(value):
    """Accept legacy device:A001 or JSON {device_id: A001}; invalid -> NULL.

    Demonstrates a Python JSON parser, not a claim that SQL cannot parse JSON.
    No network calls or side effects; fixed input always yields fixed output.
    """
    if value is None:
        return None
    try:
        if value.strip().startswith('{'):
            payload = json.loads(value)
            code = payload.get('device_id') if isinstance(payload, dict) else None
        else:
            match = re.fullmatch(r'device:\s*([A-Za-z][0-9]{3})', value.strip())
            code = match.group(1) if match else None
        if not isinstance(code, str):
            return None
        code = code.strip().upper()
        return code if re.fullmatch(r'[A-Z][0-9]{3}', code) else None
    except (ValueError, TypeError):
        return None


def generate():
    data = ROOT / 'data'
    data.mkdir(exist_ok=True)
    customers = [('C001', 'basic'), ('C002', 'premium')]
    events = []
    for i in range(1, 17):
        customer = 'C001' if i <= 8 else 'C002'
        device = 'device:A001' if i <= 8 else '{"device_id":"a002"}'
        events.append((i, f'E{i:03}', customer, '2026-10-01 10:00:00',
                       f'2026-10-01 10:01:{i:02}', 10, device))
    # Newer duplicate replaces E001 (10 -> 20), not counted twice.
    events += [
        (17, 'E001', 'C001', '2026-10-01 10:00:00', '2026-10-01 11:00:00', 20, 'device:A001'),
        (18, 'E018', 'C001', '2026-10-01 10:00:00', '2026-10-01 11:00:00', None, 'device:A001'),
        (19, 'E019', 'C999', '2026-10-01 10:00:00', '2026-10-01 11:00:00', 10, 'device:A001'),
        (20, 'E020', 'C002', '2026-10-01 10:00:00', '2026-10-01 11:00:00', 10, 'invalid'),
    ]
    for filename, headers, rows in [
        ('customers.csv', ['customer_id', 'plan'], customers),
        ('plan_history.csv', ['history_id', 'customer_id', 'plan', 'valid_from', 'valid_to'],
         [(1, 'C001', 'basic', '2026-01-01', '2026-10-01 12:00:00'),
          (2, 'C001', 'premium', '2026-10-01 12:00:00', None),
          (3, 'C002', 'premium', '2026-01-01', None)]),
        ('usage_events.csv', ['source_row', 'event_id', 'customer_id', 'occurred_at', 'received_at', 'megabytes', 'device_code'], events),
        ('expected_daily_usage.csv', ['usage_date', 'customer_id', 'plan', 'event_count', 'total_mb', 'daytime_mb'],
         [('2026-10-01', 'C001', 'basic', 8, 90, 90), ('2026-10-01', 'C002', 'premium', 8, 80, 80)]),
    ]:
        with (data / filename).open('w', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            writer.writerow(headers)
            writer.writerows(rows)


def run(database, data_dir=None):
    import duckdb
    data_dir = Path(data_dir) if data_dir is not None else ROOT / "data"
    connection = duckdb.connect(str(database))
    try:
        connection.execute('BEGIN TRANSACTION')
        connection.create_function('normalize_device', normalize_device, ['VARCHAR'],
                                   'VARCHAR', null_handling='special')
        connection.execute('CREATE OR REPLACE TABLE customers (customer_id VARCHAR PRIMARY KEY, plan VARCHAR NOT NULL)')
        connection.execute('CREATE OR REPLACE TABLE usage_events (source_row INTEGER PRIMARY KEY, event_id VARCHAR, customer_id VARCHAR, occurred_at TIMESTAMP, received_at TIMESTAMP, megabytes BIGINT, device_code VARCHAR)')
        connection.execute('CREATE OR REPLACE TABLE plan_history (history_id INTEGER PRIMARY KEY, customer_id VARCHAR NOT NULL, plan VARCHAR NOT NULL, valid_from TIMESTAMP NOT NULL, valid_to TIMESTAMP, CHECK(valid_to IS NULL OR valid_to > valid_from))')
        for table in ('customers', 'plan_history', 'usage_events'):
            # Preserve leading zeros in identifiers; typed target columns handle casts.
            connection.execute(f"INSERT INTO {table} SELECT * FROM read_csv(?, header=true, all_varchar=true)", [str(data_dir / f'{table}.csv')])
        connection.execute((ROOT / 'sql' / 'pipeline.sql').read_text(encoding='utf-8'))
        result = connection.execute('SELECT * FROM daily_usage ORDER BY usage_date, customer_id, plan').fetchall()
        counts = {table: connection.execute(f'SELECT count(*) FROM {table}').fetchone()[0]
                  for table in ('usage_events', 'deduplicated', 'classified', 'rejected_events')}
        connection.execute('COMMIT')
    finally:
        connection.close()
    return result, counts


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--generate-only', action='store_true')
    args = parser.parse_args()
    generate()
    if not args.generate_only:
        artifacts = ROOT / 'artifacts'
        artifacts.mkdir(exist_ok=True)
        result, counts = run(artifacts / 'demo.duckdb')
        print('Daily usage:', result)
        print('Quality counts:', counts)
