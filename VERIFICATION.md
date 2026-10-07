# 検証結果

2026-10-07、Windows / Python 3.12 / DuckDB 1.4.3 / NumPy 2.2.6で実行。

- `python portfolio.py`: 成功、ローカルDB作成。
- `python -m unittest -v`: 2テスト成功。
- 入力20行、重複排除後19行、不正3行、正常16行。
- C001: 8イベント・90MB。C002: 8イベント・80MB。
- 同じDBに対する2回の実行結果が一致。
- UDFの旧形式、JSON、NULL、不正JSON、非文字列ID、不正形式を検証。

性能・ストリーミング・実際の通信仕様は未検証です。
