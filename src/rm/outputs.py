"""Part 1 CSV, Part 2 data quality log and Part 3 reconciliation, all computed from the pipeline tables."""
import csv
from decimal import Decimal, ROUND_HALF_UP

from . import rules_config as R

BRANCH_ORDER = ["RIV", "OAK", "PIN", "ELM", "LKS"]
CENT = Decimal("0.01")


def r2(x):
    return Decimal(x).quantize(CENT, ROUND_HALF_UP)


def _one(con, sql):
    v = con.execute(sql).fetchone()[0]
    return Decimal(0) if v is None else v


def _write(path, header, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(header)
        w.writerows(rows)


# ---------------- Part 1 ----------------

def write_rm(con, path=None):
    rows = con.execute("SELECT branch, month, rm_usd FROM rm_by_branch").fetchall()
    rows.sort(key=lambda r: (BRANCH_ORDER.index(r[0]), r[1]))
    _write(path or R.OUT / "rm_q3_by_branch.csv", ["Branch", "Month", "RM_USD"],
           [(b, m, f"{Decimal(v):.2f}") for b, m, v in rows])
    return sum(Decimal(v) for _, _, v in rows)


# ---------------- Part 2 ----------------

def _lks_usd(where):
    """USD of a Lakeshore slice, translated per month at the policy rate (rule 5)."""
    return f"""SELECT sum(u) FROM (SELECT round(sum(b.cad) * any_value(f.policy_rate), 2) u
               FROM b_lines b JOIN fx f USING (month) WHERE {where} GROUP BY b.month)"""


def dq_issues():
    live = "NOT is_reexport_copy"
    elig = f"{live} AND r3_in_q3 AND r1_rm_account AND NOT r2_capex"
    A = lambda w: f"SELECT count(*), sum(usd) FROM a_lines WHERE {w}"
    return [
        ("A1", "ERP-A", "The 2026-08-24 weekly export is a full re-run of the 2026-08-22 export (same 780 SRO/Line keys)",
         "(SRO, Line) is unique inside every export; 780 keys appear twice, all second copies in the 08-24 export, identical to the 08-22 copy after cleaning",
         "Keep one copy per (SRO, Line), from the latest export. The run stops if copies ever disagree",
         A("is_reexport_copy"), f"SELECT sum(usd) FROM a_lines WHERE is_reexport_copy AND r3_in_q3 AND r1_rm_account AND NOT r2_capex"),
        ("A2", "ERP-A", "Branch typed 14 ways: case, padding spaces and full names ('riv', 'Riverton ', ' OAK', 'Elmwood')",
         "Distinct raw Whse values", "upper(trim()) then an explicit alias table; an unknown spelling stops the run",
         A(f"{live} AND whse_raw <> branch"), f"SELECT sum(usd) FROM a_lines WHERE included AND whse_raw <> branch"),
        ("A3", "ERP-A", "Account stored as '6100.0' or ' 6100'",
         "Acct values that are not a plain 4-digit code", "Trim and strip '.0' before matching rule 1",
         A(f"{live} AND acct_raw <> CAST(acct AS VARCHAR)"), f"SELECT sum(usd) FROM a_lines WHERE included AND acct_raw <> CAST(acct AS VARCHAR)"),
        ("A4", "ERP-A", "TransDate mixes ISO (YYYY-MM-DD) and US (MM/DD/YYYY)",
         "Pattern check. MM/DD proven: all 582 slash dates fall 0-9 days before their export, the same lag as ISO dates; read as DD/MM only 11 would",
         "Parse ISO, then MM/DD/YYYY; an unparsed date stops the run",
         A(f"{live} AND date_raw LIKE '%/%'"), f"SELECT sum(usd) FROM a_lines WHERE included AND date_raw LIKE '%/%'"),
        ("A5", "ERP-A", "Rows dated outside Q3: June (in the 06-27 export) and October (in the October exports)",
         "TransDate outside 2026-07-01..2026-09-30. No Q3-dated line arrived after the 30-Sep 18:00 export",
         "Rule 3: excluded", A(f"{live} AND NOT r3_in_q3"),
         f"SELECT sum(usd) FROM a_lines WHERE {live} AND NOT r3_in_q3 AND r1_rm_account AND NOT r2_capex"),
        ("A6", "ERP-A", "Capitalized rebuild operations 75 and 100 on R&M accounts",
         "Oper in (75, 100) and Acct in (6100, 6150, 6200), Q3", "Rule 2: every line on these operations excluded",
         A(f"{live} AND r3_in_q3 AND r1_rm_account AND r2_capex"),
         f"SELECT sum(usd) FROM a_lines WHERE {live} AND r3_in_q3 AND r1_rm_account AND r2_capex"),
        ("A7", "ERP-A", "Elmwood activity after its 31-Jul closure",
         "Branch ELM with TransDate >= 2026-08-01", "Rule 4: reported under OAK (moves USD between branches, total unchanged)",
         A("included AND branch = 'ELM' AND report_branch = 'OAK'"), "SELECT 0"),
        ("A8", "ERP-A", "Customer number on R&M-account lines",
         "CustNum not empty on 6100/6150/6200", "Rule 1: the account decides; kept (listed so the choice is explicit)",
         A("included AND cust_num IS NOT NULL"), "SELECT 0"),
        ("A9", "ERP-A", "Reversals (negative quantity); 8 reverse a line from the previous month",
         "Qty < 0; all 60 matched to an original line on SRO, item, quantity and unit cost; same branch, operation and account",
         "Rule 3: each line in the month of its own date, no netting", A("included AND qty < 0"), "SELECT 0"),
        ("A10", "ERP-A", "Possible double posting: pairs in the same export identical on SRO, operation, date, account, item, quantity and unit cost, differing only by Line",
         "Group by every business field except Line. Same item in different SROs shares a unit cost only rarely, so 25 identical pairs are unlikely to be chance",
         ("Excluded (DROP_SUSPECTED_DOUBLE_POSTS = True)" if R.DROP_SUSPECTED_DOUBLE_POSTS else
          "Kept and flagged. Not a README rule, and Accounting's total includes them (the bridge closes only with them in). Ask the ERP-A owner to confirm"),
         A("is_double_post"),
         f"SELECT sum(usd) FROM a_lines WHERE is_double_post AND {elig}" if R.DROP_SUSPECTED_DOUBLE_POSTS else "SELECT 0"),
        ("B1", "ERP-B", "Subtotal rows inside the GL detail (JournalID 'SUBTOTAL', one per account and month)",
         "JournalID = 'SUBTOTAL'; each checked equal to its detail lines (31/31)", "Dropped; would double count",
         "SELECT count(*), sum(cad) FROM b_lines WHERE is_subtotal", _lks_usd("b.is_subtotal AND b.r3_in_q3 AND b.r6_rm_account")),
        ("B2", "ERP-B", "AmountCAD stored as text with a thousands separator ('2,992.80')",
         "Cell type is text, not number", "Comma removed, cast to DECIMAL; a non-number stops the run",
         "SELECT count(*), sum(cad) FROM b_lines WHERE amount_was_text", _lks_usd("b.amount_was_text AND b.included")),
        ("B3", "ERP-B", "PostingDate is DD/MM/YYYY text (ERP-A is ISO or MM/DD)",
         "First part reaches 31, second never exceeds 10: day-first is certain", "Parse DD/MM/YYYY; an unparsed date stops the run",
         "SELECT count(*), sum(cad) FROM b_lines WHERE NOT is_subtotal", "SELECT 0"),
        ("B4", "ERP-B", "Account 7345-RM-WELD (welding repairs, September only) is missing from account_map_lakeshore.csv",
         "GL accounts left-joined to the map; rule 6 says every 73xx-RM account is R&M",
         "Included by rule 6. Accounting should add it to the map",
         "SELECT count(*), sum(cad) FROM b_lines WHERE included AND local_account NOT IN (SELECT LocalAccount FROM raw_map)",
         _lks_usd("b.included AND b.local_account NOT IN (SELECT LocalAccount FROM raw_map)")),
        ("B5", "ERP-B", "GL rows posted outside Q3 (June and October)", "PostingDate outside 2026-07-01..2026-09-30",
         "Rule 3: excluded", "SELECT count(*), sum(cad) FROM b_lines WHERE NOT is_subtotal AND NOT r3_in_q3", "SELECT 0"),
    ]


def write_dq_log(con, path=None):
    out = []
    for iid, src, issue, how, rule, rows_sql, impact_sql in dq_issues():
        n, amount = con.execute(rows_sql).fetchone()
        cur = "CAD" if src == "ERP-B" else "USD"
        out.append((iid, src, issue, how, rule, n, f"{r2(amount or 0):.2f} {cur}", f"{r2(_one(con, impact_sql)):.2f}"))
    _write(path or R.OUT / "dq_log.csv",
           ["ID", "Source", "Issue", "How detected", "Rule applied", "Rows", "Amount of affected rows",
            "Error in Q3 R&M if untreated (USD)"], out)
    return out


# ---------------- Part 3 ----------------

def bridge(con):
    finance = Decimal(_one(con, "SELECT sum(rm_usd) FROM rm_by_branch"))
    accounting = Decimal(_one(con, "SELECT CAST(USD AS DECIMAL(18,2)) FROM raw_close"))
    end = f"TIMESTAMP '{R.PERIOD[1]} 23:59:59'"
    is_rm = f"(account IN ({','.join(f'{a!r}' for a in map(str, R.RM_ACCOUNTS))}) OR regexp_matches(account, '{R.LKS_RM_ACCOUNT}'))"
    items = []

    for je_id, posted, branch, acct, amt, desc in con.execute(
            f"SELECT je_id, posted_at, branch, account, amount, description FROM je WHERE {is_rm} AND posted_at <= {end} ORDER BY je_id").fetchall():
        in_erp = _one(con, f"SELECT count(*) FROM a_lines WHERE abs(usd) = {abs(amt)}")
        items.append((f"{je_id}: manual accrual posted by Accounting, not in ERP-A", r2(amt),
                      "Both, for different purposes: Accounting may accrue a September service whose invoice is pending; Finance's number is ERP-only by rule 7",
                      f"JE register {je_id}: {branch} account {acct}, {amt} USD, posted {posted:%Y-%m-%d %H:%M} ('{desc}'), "
                      f"after the last ERP-A export (30-Sep 18:00). ERP-A lines with this amount in any export: {in_erp}",
                      "Keep as a known reconciling item. Reverse the accrual when the vendor invoice posts in ERP-A, or Q4 will count the work twice"))

    # Accounting's method, found by factoring the residual: average rate, except the close
    # month at month-end. The item is Accounting's translation minus Finance's (policy rate),
    # month by month, so it stays right if rule 5's rate is changed in rules_config.
    close_month = f"{R.PERIOD[1]:%Y-%m}"
    fx, parts = Decimal(0), []
    for month, cad, avg, me, policy in con.execute("""SELECT b.month, sum(b.cad), any_value(f.avg_rate),
            any_value(f.month_end_rate), any_value(f.policy_rate)
            FROM b_lines b JOIN fx f USING (month) WHERE b.included GROUP BY b.month ORDER BY b.month""").fetchall():
        acct_rate = me if month == close_month else avg
        d = r2(cad * acct_rate) - r2(cad * policy)
        fx += d
        if d:
            parts.append(f"{month}: CAD {cad:,.2f} x (Accounting {acct_rate:.4f} - Finance {policy:.4f}) = {d:,.2f}")
    items.append((f"Lakeshore FX: Accounting translated {close_month} at the month-end rate and the other months at the average; Finance uses {R.LKS_RATE}", fx,
                  "Finance: group policy for P&L is the monthly average (rule 5); month-end is a balance-sheet rate",
                  "; ".join(parts) + ". With this item the bridge closes exactly",
                  "Accounting: translate the close month's P&L at the average rate in the consolidation; check the close template's FX lookup for the close month"))

    if R.DROP_SUSPECTED_DOUBLE_POSTS:
        dbl = _one(con, "SELECT sum(usd) FROM a_lines WHERE is_double_post AND NOT is_reexport_copy AND r3_in_q3 AND r1_rm_account AND NOT r2_capex")
        items.append(("Suspected double posts (DQ A10), still in Accounting's ledger", r2(dbl), "Open: confirm with the ERP-A owner",
                      "DQ log A10", "Reverse the duplicate lines in ERP-A if confirmed"))

    residual = accounting - finance - sum(i[1] for i in items)
    if residual != 0:
        raise AssertionError(f"Bridge does not close, residual {residual}")

    checked = []
    for je_id, posted, acct, amt, desc in con.execute(
            f"SELECT je_id, posted_at, account, amount, description FROM je WHERE NOT ({is_rm} AND posted_at <= {end}) ORDER BY je_id").fetchall():
        why = "posted after 30-Sep, outside Q3" if posted > posted.replace(month=9, day=30, hour=23, minute=59) else f"account {acct} is not R&M"
        checked.append((f"{je_id} ({desc})", f"{amt} on {acct}, posted {posted:%Y-%m-%d %H:%M}: {why}"))
    weld = _one(con, "SELECT sum(cad) FROM b_lines WHERE included AND local_account NOT IN (SELECT LocalAccount FROM raw_map)")
    checked.append(("7345-RM-WELD missing from the Lakeshore account map",
                    f"CAD {weld:,.2f}; in both numbers (the bridge closes only with it in). Accounting should add it to the map"))
    checked.append(("Suspected double posts (DQ A10)", "In both numbers (the bridge closes only with them in)"))
    return finance, accounting, items, checked, residual


def write_reconciliation(con, path=None):
    finance, accounting, items, checked, residual = bridge(con)
    rows, running = [("0", "Finance Q3 R&M (rm_q3_by_branch.csv)", f"{finance:.2f}", f"{finance:.2f}", "", "", "")], finance
    for n, (item, usd, who, evidence, action) in enumerate(items, 1):
        running += usd
        rows.append((n, item, f"{usd:.2f}", f"{running:.2f}", who, evidence, action))
    rows += [("=", "Accounting reported Q3 R&M", f"{accounting:.2f}", "", "", "accounting_close_summary.csv", ""),
             ("=", "Residual", f"{residual:.2f}", "", "", "", "")]
    rows += [("checked, 0.00", item, "0.00", "", "", why, "") for item, why in checked]
    _write(path or R.OUT / "reconciliation.csv",
           ["Step", "Item", "USD", "Running total", "Who is right", "Evidence", "What should change and where"], rows)
    return finance, accounting, residual


def _csv_to_markdown(csv_path, md_path, title, intro, image=None):
    """Readable copy of an output CSV for reviewers (the CSV stays the source)."""
    rows = list(csv.reader(open(csv_path)))
    esc = lambda s: str(s).replace("|", "\\|")
    lines = [f"# {title}", "", intro, ""] + ([f"![{title}]({image})", ""] if image else []) + [ "| " + " | ".join(rows[0]) + " |", "|" + "---|" * len(rows[0])]
    lines += ["| " + " | ".join(esc(c) for c in r) + " |" for r in rows[1:]]
    md_path.write_text("\n".join(lines) + "\n")


def main():
    from .pipeline import build
    con = build()
    total = write_rm(con)
    write_dq_log(con)
    try:
        finance, accounting, residual = write_reconciliation(con)
    except AssertionError as e:
        # Part 1 is already written; the reconciliation is left as it was.
        raise SystemExit(f"Finance Q3 R&M {total:,.2f} written to output/. {e}: "
                         "the changed rule is not one Accounting applied, so add a reconciling item for it in outputs.bridge().")
    docs = R.ROOT / "docs"
    from .charts import bridge_chart, funnel_chart
    funnel_chart(con, docs / "img" / "funnel.png")
    _, _, items, _, _ = bridge(con)
    bridge_chart(finance, accounting, items, docs / "img" / "bridge.png")
    _csv_to_markdown(R.OUT / "dq_log.csv", docs / "02_data_quality_log.md", "Part 2 — Data quality log",
                     "Generated by `make run` from output/dq_log.csv. ERP-B amounts are CAD; the last column is the USD error in Q3 R&M if the issue were not treated. The chart shows where every raw line goes; each line is in exactly one bar.",
                     image="img/funnel.png")
    _csv_to_markdown(R.OUT / "reconciliation.csv", docs / "03_reconciliation.md", "Part 3 — Reconciliation to Accounting",
                     "Generated by `make run` from output/reconciliation.csv. Every amount is computed from the data; the run fails if the residual is not 0.00.",
                     image="img/bridge.png")
    print(f"Finance Q3 R&M {total:,.2f} | Accounting {accounting:,.2f} | bridge residual {residual:.2f}")


if __name__ == "__main__":
    main()
