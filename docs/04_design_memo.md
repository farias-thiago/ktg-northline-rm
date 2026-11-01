# Part 4 — Design memo: group R&M on one governed platform

**Recommendation:** Microsoft Fabric on a small capacity. The Finance rules live as tested code plus reference tables that Finance owns. One semantic model feeds both Power BI and the AI tools.

**Why Fabric.** Northline already runs on Microsoft 365 and Power BI. Fabric puts storage, pipelines, the semantic model, reports and AI Q&A in the same tenant, under the same Entra ID security. The volume is small: a few tens of thousands of rows a week, under 1 GB a year. That does not justify Spark clusters or a second vendor. The hard part is trust, not scale.

**Getting the data out**

- **Main ERP:** never queried live. IT restores the nightly backup to a staging copy, and a Fabric pipeline reads that copy through the on-premises gateway once the restore is done. One day of latency is fine for month-end reporting.
- **Other three ERPs:** a scheduled export or API per system, whichever is reliable.
- **Landing:** every file lands unchanged with its load time and source name, so any reported number traces back to a file and row.
- **Duplicates:** each run reloads a rolling window (current and prior month) and upserts on the source key. That removes duplicate exports like the 24-Aug re-run by design.

**Layers.** Raw (immutable) → Clean (one transaction schema for the 4 ERPs: typed dates and amounts, branch codes, group account, currency) → Reporting (R&M by entity, branch and month in USD, the DQ log, the ledger reconciliation). Unknown branch spellings, accounts or date formats stop the load and alert the owner. Nothing is dropped silently.

**Where the rules live, and who owns them**

- **Reference tables, owned by the Group Controller:** account maps per ERP, branch aliases and closures, capitalized operations, FX rates and rate policy. They are edited in an approved SharePoint list and read on every run. The Lakeshore map missing 7345-RM-WELD is exactly the gap this closes: an unmapped account in an R&M range raises an alert instead of disappearing.
- **Rule logic, owned by the data team:** SQL in Git with one test per rule, deployed through Fabric's Git integration. Any rule change is a reviewed pull request that Finance signs off.
- **Close control:** after each close, the reporting number is bridged to the ledger item by item, as in Part 3. A period is only marked "published" when the bridge closes.

**AI on governed numbers.** Copilot and a Fabric data agent answer only from the semantic model, never from raw tables. They use the same measures as the reports and respect row-level security. Before rollout they are tested against a fixed set of questions with known answers.

**Rough monthly cost** (list prices, to confirm for the region):

| Item | USD / month |
|---|---|
| Fabric F2 capacity, 1-year reserved (F4 if AI load needs it) | ~160–320 |
| OneLake storage, < 50 GB | < 5 |
| Power BI Pro per author; viewers also need Pro below F64 (included in M365 E5) | 14 / user |
| **Platform total, excluding licences already owned** | **~200–450** |

**First 30 days**

- **Week 1:** Inventory the 6 entities and 4 ERPs (owner, extract method, chart of accounts). Agree the restore window with IT. Land ERP-A and ERP-B raw data.
- **Week 2:** Rebuild this exercise in Fabric with the rules, tests and DQ log. Finance signs off the reference tables.
- **Week 3:** Land the other two ERPs. Publish the semantic model and the R&M report for Q3 and October.
- **Week 4:** Reconcile the October close to the cent. Pilot the data agent with Finance on 20 test questions. Hand over a run book with a named support owner.
