# SQL + Python UDF Portfolio

架空の通信利用ログを顧客別・日別に集計する、小さなデータ処理ポートフォリオです。
自主制作であり、実務経験や通信会社の本番仕様を示すものではありません。
顧客・ログ・端末識別子はすべて合成データです。外部データや個人情報は使用しません。

## 示す技術

- SQL: LEFT JOIN、CASE、日付関数、GROUP BY、ROW_NUMBER、段階的なテーブル加工
- Python UDF: 端末コードの旧形式とJSON形式を正規化し、SQLから呼び出す
- 品質検証: 重複排除、NULL、不正形式、マスターにない顧客の隔離
- 再現性: 固定20件、手計算可能な期待値、DB全再構築による再実行の安全性

## 実行

Python 3.10以上を想定します。

```sh
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements.txt
python portfolio.py
python -m unittest -v
```

`python portfolio.py --generate-only` はPython標準ライブラリのみでCSVを生成します。
DBは `artifacts/demo.duckdb` に作成され、Gitには含めません。
Python UDFの登録は接続ごとに実施するため、SQLだけを別の接続で実行しても利用できません。

## 処理と期待値

1. 顧客マスターの主キーでJOINによる意図しない多重化を防ぐ。
2. 同じイベントIDは受信日時、同日時なら入力行番号で最新行を採用。
3. イベントID・日時の欠損、負の通信量も隔離する。
4. 正常データを顧客・日付・プランで集計、不正データを理由付きで隔離。

入力20行 → 重複排除後19行 → 正常16行 / 不正3行。
C001は8イベント・90MB、C002は8イベント・80MB。
E001の更新を10MBから20MBに置き換えるので、重複分は加算しません。
すべて昼間のデータのため、昼間通信量は合計通信量と一致します。
複数の不正条件がある場合はCASEの上から最初の理由を採用します。

## なぜPython UDFか

独自形式とJSONを同じ関数で扱い、型・形式のチェックをPython側にまとめる例です。
DuckDBの標準SQLでもJSON解析は可能です。Pythonが必須という主張ではありません。
SQL標準機能で簡潔に書ける処理はSQLを優先し、UDFは製品の制約や性能を確認して選びます。
関数は外部アクセス・副作用を持たず、NULLや不正入力はNULLを返します。

昼間は09:00以上18:00未満、日時は架空の同一ローカル時間として扱います。
全再構築はトランザクション内で行い、失敗時は前回のDBを維持します。

## 範囲・制約

これはバッチ処理のデモです。ストリーミング、性能チューニング、遅延到着の増分更新、
料金計算、契約履歴、本番運用は実装していません。
再実行は全テーブルを置換する方式で、増分処理の冪等性とは区別します。
SQLエンジンはDuckDB、Python UDFの仕様は公式資料を参照しています。
https://duckdb.org/docs/stable/clients/python/function

## 検証状態

Pythonのみのデータ生成・UDF検証と、DuckDBを使った統合検証は別々に記録します。
実行環境での検証結果は `VERIFICATION.md` に記載します。
