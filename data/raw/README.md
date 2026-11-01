# Northline Industrial Services — Q3 2026 Data Pack

Northline Industrial Services is a fictional company. All data in this pack is synthetic.

Northline maintains industrial equipment for its customers from five branches on two ERP systems:

| Branch | Code | Country | ERP |
|---|---|---|---|
| Riverton | RIV | US | ERP-A |
| Oakdale | OAK | US | ERP-A |
| Pinecrest | PIN | US | ERP-A |
| Elmwood | ELM | US | ERP-A (closed 31-Jul-2026) |
| Lakeshore | LKS | Canada | ERP-B (books in CAD) |

## Files

| File | What it is |
|---|---|
| `erp_a_sro_transactions.csv` | ERP-A service repair order (SRO) transaction lines. This file is the weekly exports appended together. The last export of the quarter was pulled on 30-Sep-2026 at 18:00. |
| `erp_b_lakeshore_gl_detail.xlsx` | ERP-B general ledger detail for Lakeshore, in CAD. |
| `account_map_lakeshore.csv` | Maps Lakeshore local accounts to Northline group accounts. Maintained by Accounting. |
| `fx_cad_usd.csv` | CAD to USD rates by month: monthly average and month-end. |
| `accounting_close_summary.csv` | Total Q3 R&M as reported by Accounting in the close. |
| `accounting_je_register_sep_close.csv` | Manual journal entries posted by Accounting during the September close. |

## ERP-A columns

| Column | Meaning |
|---|---|
| SRO | Service repair order number |
| Line | Line number within the SRO |
| Oper | SRO operation code |
| Whse | Branch, as typed in the ERP |
| TransDate | Transaction date |
| TransType | Labor, Material or Misc |
| Acct | Group GL account |
| Item | Item or service description |
| Qty, UnitCost, ExtCost | Quantity, unit cost (USD) and extended cost (USD) |
| CustNum | Customer, when the work is for a customer |
| ExportedAt | When the export containing this line was pulled |

Reversals in ERP-A are posted as new lines with a negative quantity.

## Group accounts

| Account | Description |
|---|---|
| 5100 | Billable labor |
| 6100 | R&M parts |
| 6150 | R&M outside service |
| 6200 | R&M labor |
| 6300 | Fluids & lubricants |
| 6400 | Fuel off-road |
| 6500 | Shop supplies |

## Finance rules for R&M reporting

1. **R&M** is group accounts 6100, 6150 and 6200 only. The account decides; a customer number on the line does not change it.
2. **SRO operations 75 and 100 are capitalized rebuilds.** Every line on those operations is excluded from R&M, even when it uses an R&M account.
3. **Period** is Q3 2026 (1-Jul to 30-Sep), by transaction date in ERP-A and posting date in ERP-B. Every line, including a reversal, counts in the month of its own date.
4. **Elmwood closed on 31-Jul-2026.** Elmwood activity dated 1-Aug or later is reported under Oakdale. July stays under Elmwood.
5. **Lakeshore results are translated to USD at the monthly average rate** (group policy for P&L). Translate each month's CAD total, then round to cents.
6. **Lakeshore chart of accounts:** every local account in the 73xx-RM range is repairs and maintenance.
7. Finance's R&M is built from ERP data only (ERP-A transactions and ERP-B GL detail). Manual journal entries posted by Accounting are not an input; treat them as reconciling items.
8. Report in USD, rounded to cents at branch-month level.
