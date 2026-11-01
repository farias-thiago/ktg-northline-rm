"""Raw files -> typed, cleaned lines with one flag per rule -> R&M by branch and month.

Layers: raw_* (text, as in the files) -> a_lines / b_lines (typed + flags) -> rm_by_branch.
Anything that cannot be parsed or mapped stops the run; nothing is dropped silently.
"""
import duckdb
import openpyxl
import pandas as pd

from . import rules_config as R


class DataError(Exception):
    pass


def _check_none(con, sql, what):
    bad = con.execute(sql).fetchdf()
    if len(bad):
        raise DataError(f"{what} ({len(bad)} rows):\n{bad.head(10).to_string()}")


def _load(con):
    for name, table in [("erp_a_sro_transactions.csv", "raw_a"), ("fx_cad_usd.csv", "raw_fx"),
                        ("account_map_lakeshore.csv", "raw_map"), ("accounting_je_register_sep_close.csv", "raw_je"),
                        ("accounting_close_summary.csv", "raw_close")]:
        con.execute(f"""CREATE OR REPLACE TABLE {table} AS
            SELECT row_number() OVER () + 1 AS file_row, *
            FROM read_csv('{R.RAW / name}', all_varchar = true, header = true)""")

    # Excel: keep every cell as the text it holds. Numbers keep their shortest exact
    # repr; numbers stored as text ('4,581.93') stay text and are flagged.
    ws = openpyxl.load_workbook(R.RAW / "erp_b_lakeshore_gl_detail.xlsx", read_only=True).worksheets[0]
    rows = list(ws.iter_rows(values_only=True))
    gl = pd.DataFrame(rows[1:], columns=rows[0])
    gl["AmountWasText"] = gl.AmountCAD.map(lambda v: isinstance(v, str))
    for c in rows[0]:
        gl[c] = gl[c].map(lambda v: None if v is None else str(v))
    gl.insert(0, "file_row", range(2, len(gl) + 2))
    con.register("gl", gl)
    con.execute("CREATE OR REPLACE TABLE raw_b AS SELECT * FROM gl")
    con.unregister("gl")
    con.register("whse", pd.DataFrame(list(R.WHSE.items()), columns=["key", "branch"]))
    con.execute("CREATE OR REPLACE TABLE whse_map AS SELECT * FROM whse")
    con.unregister("whse")


def _erp_a(con):
    start, end = R.PERIOD
    con.execute(r"""
    CREATE OR REPLACE TABLE a_typed AS
    SELECT r.file_row, r.SRO AS sro, CAST(r.Line AS INT) AS line, CAST(r.Oper AS INT) AS oper,
           r.Whse AS whse_raw, w.branch,
           r.TransDate AS date_raw,
           CAST(coalesce(try_strptime(r.TransDate, '%Y-%m-%d'), try_strptime(r.TransDate, '%m/%d/%Y')) AS DATE) AS trans_date,
           r.Acct AS acct_raw, TRY_CAST(regexp_replace(trim(r.Acct), '\.0+$', '') AS INT) AS acct,
           r.TransType AS trans_type, r.Item AS item,
           CAST(r.Qty AS DECIMAL(18,4)) AS qty, CAST(r.UnitCost AS DECIMAL(18,4)) AS unit_cost,
           CAST(r.ExtCost AS DECIMAL(18,2)) AS usd, r.ExtCost AS usd_raw,
           nullif(trim(r.CustNum), '') AS cust_num, CAST(r.ExportedAt AS TIMESTAMP) AS exported_at
    FROM raw_a r LEFT JOIN whse_map w ON w.key = upper(trim(r.Whse))""")
    _check_none(con, "SELECT * FROM a_typed WHERE branch IS NULL", "Unknown Whse spelling")
    _check_none(con, "SELECT * FROM a_typed WHERE trans_date IS NULL", "Unparsed TransDate")
    _check_none(con, "SELECT * FROM a_typed WHERE acct IS NULL", "Unparsed Acct")
    _check_none(con, "SELECT * FROM a_typed WHERE CAST(usd_raw AS DECIMAL(18,6)) <> usd", "ExtCost with more than 2 decimals")
    _check_none(con, "SELECT * FROM a_typed WHERE qty * unit_cost <> usd", "ExtCost <> Qty x UnitCost")

    con.execute(f"""
    CREATE OR REPLACE TABLE a_lines AS
    WITH d AS (
        SELECT *, row_number() OVER (PARTITION BY sro, line ORDER BY exported_at DESC) > 1 AS is_reexport_copy
        FROM a_typed
    ), p AS (
        SELECT sro, line, row_number() OVER (
               PARTITION BY sro, oper, trans_date, acct, item, qty, unit_cost ORDER BY line) > 1 AS is_double_post
        FROM d WHERE NOT is_reexport_copy
    )
    -- p is keyed on (sro, line), which a re-export copy shares: flag only the live copy.
    SELECT d.*, coalesce(p.is_double_post AND NOT d.is_reexport_copy, false) AS is_double_post,
        trans_date BETWEEN DATE '{start}' AND DATE '{end}'            AS r3_in_q3,
        acct IN ({",".join(map(str, R.RM_ACCOUNTS))})                 AS r1_rm_account,
        oper IN ({",".join(map(str, R.CAPEX_OPERATIONS))})            AS r2_capex,
        CASE WHEN branch = 'ELM' AND trans_date >= DATE '{R.ELM_CLOSED_FROM}'
             THEN '{R.ELM_REPORTS_UNDER}' ELSE branch END             AS report_branch,
        strftime(trans_date, '%Y-%m')                                 AS month
    FROM d LEFT JOIN p USING (sro, line)""")
    # Copies of the same (SRO, Line) must agree on every value we use, or the dedup is unsafe.
    _check_none(con, """SELECT sro, line FROM a_lines GROUP BY ALL
        HAVING count(DISTINCT (branch, trans_date, acct, oper, usd)) > 1""", "Re-exported line copies disagree")
    drop_dbl = "AND NOT is_double_post" if R.DROP_SUSPECTED_DOUBLE_POSTS else ""
    con.execute(f"""ALTER TABLE a_lines ADD COLUMN included BOOLEAN;
        UPDATE a_lines SET included = NOT is_reexport_copy AND r3_in_q3 AND r1_rm_account AND NOT r2_capex {drop_dbl}""")


def _erp_b(con):
    start, end = R.PERIOD
    con.execute(f"""
    CREATE OR REPLACE TABLE b_lines AS
    SELECT file_row, JournalID AS journal_id, JournalID = 'SUBTOTAL' AS is_subtotal,
           PostingDate AS date_raw, CAST(try_strptime(PostingDate, '%d/%m/%Y') AS DATE) AS posting_date,
           LocalAccount AS local_account, Description AS description, Source AS source,
           AmountCAD AS amount_raw, AmountWasText AS amount_was_text,
           TRY_CAST(replace(AmountCAD, ',', '') AS DECIMAL(18,2)) AS cad
    FROM raw_b""")
    _check_none(con, "SELECT * FROM b_lines WHERE posting_date IS NULL", "Unparsed PostingDate")
    _check_none(con, "SELECT * FROM b_lines WHERE cad IS NULL OR CAST(replace(amount_raw, ',', '') AS DECIMAL(18,6)) <> cad",
                "AmountCAD not a 2-decimal number")
    con.execute(f"""
    ALTER TABLE b_lines ADD COLUMN r3_in_q3 BOOLEAN; ALTER TABLE b_lines ADD COLUMN r6_rm_account BOOLEAN;
    ALTER TABLE b_lines ADD COLUMN month VARCHAR; ALTER TABLE b_lines ADD COLUMN included BOOLEAN;
    UPDATE b_lines SET r3_in_q3 = posting_date BETWEEN DATE '{start}' AND DATE '{end}',
                       r6_rm_account = regexp_matches(local_account, '{R.LKS_RM_ACCOUNT}'),
                       month = strftime(posting_date, '%Y-%m');
    UPDATE b_lines SET included = NOT is_subtotal AND r3_in_q3 AND r6_rm_account;""")
    # Each subtotal row must equal its detail lines; otherwise the GL extract itself is suspect.
    _check_none(con, """
        SELECT s.local_account, s.month, s.cad, d.cad AS detail FROM b_lines s
        LEFT JOIN (SELECT local_account, month, sum(cad) cad FROM b_lines WHERE NOT is_subtotal GROUP BY ALL) d
          ON d.local_account = s.local_account AND d.month = s.month
        WHERE s.is_subtotal AND s.cad IS DISTINCT FROM d.cad""", "Subtotal row does not match its detail")


def _reference(con):
    con.execute(f"""CREATE OR REPLACE TABLE fx AS SELECT Month AS month,
        CAST(AvgRate_CADtoUSD AS DECIMAL(10,6)) AS avg_rate, CAST(MonthEndRate_CADtoUSD AS DECIMAL(10,6)) AS month_end_rate,
        CAST({R.LKS_RATE} AS DECIMAL(10,6)) AS policy_rate FROM raw_fx""")
    con.execute("""CREATE OR REPLACE TABLE je AS SELECT JE_ID AS je_id, CAST(PostedAt AS TIMESTAMP) AS posted_at,
        Entity AS entity, Branch AS branch, Account AS account, CAST(Amount AS DECIMAL(18,2)) AS amount,
        Description AS description FROM raw_je""")


def _output(con):
    # Rules 5 and 8: ERP-A summed per branch-month; Lakeshore CAD summed per month,
    # translated at the policy rate, then rounded to cents.
    con.execute("""
    CREATE OR REPLACE TABLE rm_by_branch AS
    SELECT report_branch AS branch, month, round(sum(usd), 2) AS rm_usd
    FROM a_lines WHERE included GROUP BY ALL
    UNION ALL
    SELECT 'LKS', b.month, round(sum(b.cad) * any_value(f.policy_rate), 2)
    FROM b_lines b JOIN fx f USING (month) WHERE b.included GROUP BY b.month""")
    _check_none(con, "SELECT DISTINCT month FROM b_lines WHERE included AND month NOT IN (SELECT month FROM fx)",
                "Lakeshore month without an FX rate")


def build(db=":memory:"):
    con = duckdb.connect(db)
    _load(con)
    _reference(con)
    _erp_a(con)
    _erp_b(con)
    _output(con)
    return con
