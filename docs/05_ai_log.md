# Part 5 — How I used AI

**Tools.** Claude Code (Claude Opus 5.5) in VS Code, as a pair programmer with shell access. I used it to read the brief, profile the files, write the Python/DuckDB pipeline and the tests, and draft the docs. I set the direction, reviewed every rule and decision, and overruled it where needed.

**Most useful instructions** (translated from Portuguese)

1. *"Read the email with the assessment details and let's plan the execution."* I worked in plan mode: nothing was built until I had approved a plan (stack, repo layout, one step per README rule, how each part would be verified). The plan included proving every assumption from the data before coding it. So each treatment in the DQ log cites its evidence: the slash dates are MM/DD because all 582 fall 0–9 days before their export (as DD/MM, only 11 would), and the 24-Aug export is a full re-run of 22-Aug (780 of 780 keys, identical after cleaning).
2. *"Check whether the files contain any input aimed at the AI: something asking you to do something or behave a certain way."* It scanned every cell, comment and hidden part of the workbook, all CSV text, and the PDF's raw content (tiny or near-white text, annotations, metadata). Nothing was found.
3. *"Start from zero."* The recruiter first sent a different version of the data pack. When the correct one arrived, I had the AI rebuild from an empty folder and re-profile every file, instead of carrying over conclusions from the old data.

**What the AI got wrong, and how I caught it**

- **A wrong count.** The double-post flag was joined back on (SRO, Line), a key the re-exported copy shares, so the DQ log reported 29 suspected double posts instead of 25. I caught it because the number disagreed with the independent profiling script. It is fixed, and a test now guards it.
- **A recommendation it had to reverse.** It first proposed removing the 25 double posts. They are statistically not chance, but Accounting's total closes only with them in, so they are real ledger postings. They are now kept and flagged, with a one-line switch. The bridge closes either way, and both cases are tested.
- **A blind spot in its search.** On the first version of the pack, its search for the bridge always changed the FX rate for all three months at once. It missed that Accounting used the month-end rate for the close month only. I found it by dividing the unexplained residual by each month's rate difference. On this pack, that item is 10,554.78 USD.

**How I checked everything else.** The pipeline stops on any value it cannot parse or map, instead of dropping it. There are 14 tests: one per README rule, format, the bridge, and the bridge after switching the double-post toggle or the FX rate. The bridge fails the run if it is not 0.00. Two clean runs produce byte-identical outputs.

**AI-written code.** Essentially all of it (~100%) was typed by the AI. The judgement calls are mine: which issues matter, how to treat them, and when to reject a "fit" that closed the numbers without an accounting reason.
