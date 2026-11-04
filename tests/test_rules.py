"""One test per README rule, plus cleaning, output-format and bridge checks (also after a config change)."""
import csv
import re
from decimal import Decimal

import pytest

from rm.outputs import bridge, write_rm
from rm.pipeline import build


@pytest.fixture(scope="module")
def con():
    return build()


def one(con, sql):
    return con.execute(sql).fetchone()[0]


def test_rule1_rm_accounts_only_and_custnum_ignored(con):
    assert one(con, "SELECT count(*) FROM a_lines WHERE included AND acct NOT IN (6100, 6150, 6200)") == 0
    assert one(con, "SELECT count(*) FROM a_lines WHERE included AND cust_num IS NOT NULL") > 0


def test_rule2_capex_operations_excluded(con):
    assert one(con, "SELECT count(*) FROM a_lines WHERE included AND oper IN (75, 100)") == 0


def test_rule3_q3_only_and_reversal_stays_in_its_own_month(con):
    for t in ("a_lines", "b_lines"):
        assert one(con, f"SELECT count(*) FROM {t} WHERE included AND month NOT IN ('2026-07','2026-08','2026-09')") == 0
    # S042509/5 (1-Aug) reverses a 26-Jul line: it must count in August
    assert one(con, "SELECT month FROM a_lines WHERE sro = 'S042509' AND line = 5 AND included") == "2026-08"


def test_rule4_elmwood_from_august_reports_under_oakdale(con):
    assert one(con, "SELECT count(*) FROM a_lines WHERE included AND report_branch = 'ELM' AND month > '2026-07'") == 0
    assert one(con, "SELECT count(*) FROM a_lines WHERE included AND branch = 'ELM' AND report_branch = 'OAK'") > 0


def test_rule5_lakeshore_month_total_at_average_rate(con):
    cad = one(con, "SELECT sum(cad) FROM b_lines WHERE included AND month = '2026-09'")
    usd = one(con, "SELECT rm_usd FROM rm_by_branch WHERE branch = 'LKS' AND month = '2026-09'")
    assert usd == (cad * Decimal("0.7236")).quantize(Decimal("0.01"))


def test_rule6_every_73xx_rm_account_even_if_unmapped(con):
    assert one(con, "SELECT count(*) FROM b_lines WHERE included AND local_account = '7345-RM-WELD'") == 23
    assert one(con, "SELECT count(*) FROM raw_map WHERE LocalAccount = '7345-RM-WELD'") == 0


def test_rule7_manual_jes_are_reconciling_items_not_inputs(con):
    _, _, items, _, _ = bridge(con)
    assert any(i[0].startswith("JE-1026") for i in items)


def test_reexport_removed_once(con):
    assert one(con, "SELECT count(*) FROM a_lines WHERE is_reexport_copy") == 780
    assert one(con, "SELECT count(*) FROM (SELECT sro, line FROM a_lines WHERE NOT is_reexport_copy GROUP BY ALL HAVING count(*) > 1)") == 0


def test_double_posts_flag_live_copies_only(con):
    assert one(con, "SELECT count(*) FROM a_lines WHERE is_double_post") == 25
    assert one(con, "SELECT count(*) FROM a_lines WHERE is_double_post AND is_reexport_copy") == 0


def test_lakeshore_subtotals_and_text_amounts(con):
    assert one(con, "SELECT count(*) FROM b_lines WHERE included AND is_subtotal") == 0
    assert one(con, "SELECT count(*) FROM b_lines WHERE amount_was_text") == 18


def test_output_file_format(con, tmp_path):
    p = tmp_path / "rm.csv"
    total = write_rm(con, p)
    rows = list(csv.reader(open(p, encoding="utf-8")))
    assert rows[0] == ["Branch", "Month", "RM_USD"]
    assert len(rows) == 1 + 13  # RIV/OAK/PIN x 3 months, ELM July, LKS x 3 months
    for b, m, v in rows[1:]:
        assert b in {"RIV", "OAK", "PIN", "ELM", "LKS"} and re.fullmatch(r"2026-0[789]", m)
        assert re.fullmatch(r"-?\d+\.\d{2}", v)
    assert total == Decimal("14154722.25")


def test_bridge_closes_to_the_cent(con):
    finance, accounting, items, _, residual = bridge(con)
    assert residual == 0 and accounting == Decimal("14186652.03")
    assert finance + sum(i[1] for i in items) == accounting


@pytest.mark.parametrize("setting, value, finance, extra_items", [
    ("DROP_SUSPECTED_DOUBLE_POSTS", True, "14102594.47", {"52127.78"}),
    ("LKS_RATE", "MonthEndRate_CADtoUSD", "14162275.77", {"3001.26"}),
])
def test_bridge_still_closes_after_a_config_change(monkeypatch, setting, value, finance, extra_items):
    from rm import rules_config as R
    monkeypatch.setattr(R, setting, value)
    f, accounting, items, _, residual = bridge(build())
    assert residual == 0 and f == Decimal(finance)
    assert extra_items <= {str(i[1]) for i in items}
