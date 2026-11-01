"""The Finance rules from the data pack README, as parameters (rule numbers match the README).

Change a rule here and rerun `make`; nothing else needs editing.
"""
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "output"

RM_ACCOUNTS = (6100, 6150, 6200)            # rule 1 (the account decides; CustNum ignored)
CAPEX_OPERATIONS = (75, 100)                # rule 2
PERIOD = (date(2026, 7, 1), date(2026, 9, 30))  # rule 3
ELM_CLOSED_FROM, ELM_REPORTS_UNDER = date(2026, 8, 1), "OAK"  # rule 4
LKS_RATE = "AvgRate_CADtoUSD"               # rule 5 (alternative: "MonthEndRate_CADtoUSD")
LKS_RM_ACCOUNT = r"^73\d{2}-RM"             # rule 6

# ERP-A Whse as typed -> branch. An unknown spelling stops the run.
WHSE = {"RIV": "RIV", "RIVERTON": "RIV", "OAK": "OAK", "OAKDALE": "OAK",
        "PIN": "PIN", "PINECREST": "PIN", "ELM": "ELM", "ELMWOOD": "ELM"}

# Not a README rule: same-export line pairs identical except the Line number.
# Kept by default (see DQ log A10); True drops the second line of each pair.
DROP_SUSPECTED_DOUBLE_POSTS = False
