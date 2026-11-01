"""Charts for the docs, drawn from the same tables as the CSVs, so they change when a rule changes."""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

INK, MUTED, GRID, SURFACE = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
BLUE, GRAY, ORANGE = "#2a78d6", "#b9b8b3", "#eb6834"

plt.rcParams.update({
    "font.family": "sans-serif", "font.size": 10, "text.color": INK,
    "axes.edgecolor": GRID, "axes.labelcolor": MUTED, "xtick.color": MUTED, "ytick.color": MUTED,
    "axes.spines.top": False, "axes.spines.right": False, "figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
})


def _save(fig, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    # No software/date metadata, so two runs give byte-identical files.
    fig.savefig(path, dpi=160, bbox_inches="tight", metadata={"Software": None})
    plt.close(fig)


def bridge_chart(finance, accounting, items, path):
    """Waterfall of the gap between Finance and Accounting, from a zero baseline."""
    fig, ax = plt.subplots(figsize=(8, 3.8))
    labels, run = [], 0
    for i, (item, usd, *_rest) in enumerate(items):
        usd = float(usd)
        ax.bar(i, usd, bottom=run, color=BLUE, width=0.55)
        ax.text(i, run + max(usd, 0), f"+{usd:,.2f}" if usd >= 0 else f"{usd:,.2f}", ha="center", va="bottom", fontsize=9)
        if i:
            ax.plot([i - 1 + 0.275, i - 0.275], [run, run], color=MUTED, lw=0.8, ls=":")
        labels.append(_short(item))
        run += usd
    n = len(items)
    gap = float(accounting - finance)
    ax.plot([n - 1 + 0.275, n - 0.275], [run, run], color=MUTED, lw=0.8, ls=":")
    ax.bar(n, gap, color=MUTED, width=0.55)
    ax.text(n, gap, f"{gap:,.2f}\nresidual {gap - run:.2f}", ha="center", va="bottom", fontsize=9)
    labels.append("Accounting − Finance\n\n")
    ax.set_xticks(range(n + 1), labels, fontsize=9)
    ax.set_ylim(0, gap * 1.25)
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:,.0f}"))
    ax.set_ylabel("USD")
    ax.grid(axis="y", color=GRID, lw=0.6)
    ax.set_axisbelow(True)
    word = {1: "One item explains", 2: "Two items explain", 3: "Three items explain"}.get(n, f"{n} items explain")
    fig.suptitle(f"{word} the gap; residual {gap - run:.2f}", x=0.125, ha="left", fontsize=12.5, y=1.04)
    ax.set_title(f"Finance {float(finance):,.2f}  →  Accounting {float(accounting):,.2f}", loc="left", fontsize=10, color=MUTED, pad=12)
    _save(fig, path)


def _money(unit, v):
    return f"{unit} {v / 1e6:,.2f}M" if abs(v) >= 1e6 else f"{unit} {v / 1e3:,.1f}K"


def _short(item):
    """Bar label: what the item is, then who is right (full reasoning is in the table below the chart)."""
    if item.startswith("JE-"):
        return f"{item.split(':')[0]} accrual\nposted after the export\ntiming: both right"
    if item.startswith("Lakeshore FX"):
        return "Lakeshore FX\nclose month at month-end\nFinance right: policy = average"
    if item.startswith("Suspected double posts"):
        return "Suspected double posts\nin the ledger\nopen: ask ERP-A owner"
    return item[:28]


A_STEPS = [
    ("Re-export copies (24-Aug re-ran 22-Aug)", "is_reexport_copy"),
    ("Outside Q3 (rule 3)", "NOT is_reexport_copy AND NOT r3_in_q3"),
    ("Not an R&M account (rule 1)", "NOT is_reexport_copy AND r3_in_q3 AND NOT r1_rm_account"),
    ("Capex operation 75/100 (rule 2)", "NOT is_reexport_copy AND r3_in_q3 AND r1_rm_account AND r2_capex"),
    ("Suspected double posts (dropped by toggle)", "NOT is_reexport_copy AND r3_in_q3 AND r1_rm_account AND NOT r2_capex AND NOT included"),
    ("Included in Q3 R&M", "included"),
]
# Subtotal rows repeat their detail, so they are noted in the title rather than drawn as money.
B_STEPS = [
    ("Outside Q3 (rule 3)", "NOT is_subtotal AND NOT r3_in_q3"),
    ("Not a 73xx-RM account (rule 6)", "NOT is_subtotal AND r3_in_q3 AND NOT r6_rm_account"),
    ("Included in Q3 R&M", "included"),
]
# Lines that stay in the number but were changed on the way in (DQ log IDs in brackets).
TREATED = [
    ("[A4] US dates MM/DD read correctly", "a", "included AND date_raw LIKE '%/%'"),
    ("[A2] Branch spelling normalised", "a", "included AND whse_raw <> branch"),
    ("[A7] Elmwood after 31-Jul moved to OAK", "a", "included AND branch = 'ELM' AND report_branch = 'OAK'"),
    ("[A3] Account '6100.0' / ' 6100' cleaned", "a", "included AND acct_raw <> CAST(acct AS VARCHAR)"),
    ("[A10] Suspected double posts, kept + flagged", "a", "included AND is_double_post"),
    ("[B4] 7345-RM-WELD, missing from the map", "b", "b.included AND b.local_account NOT IN (SELECT LocalAccount FROM raw_map)"),
    ("[B2] Amount stored as text ('2,992.80')", "b", "b.included AND b.amount_was_text"),
]


def funnel_chart(con, path):
    """Where every raw line goes (each line lands in exactly one bar, and the run checks that),
    plus the lines that stay in the number but were treated on the way in."""
    from .outputs import _lks_usd
    lks_usd = float(con.execute("SELECT sum(rm_usd) FROM rm_by_branch WHERE branch = 'LKS'").fetchone()[0])
    sub_n = con.execute("SELECT count(*) FROM b_lines WHERE is_subtotal").fetchone()[0]
    panels = []
    for table, amount, unit, steps, where, title in [
            ("a_lines", "usd", "USD", A_STEPS, "true", "ERP-A (US branches): {n:,} raw lines, USD {amt:.2f}M"),
            ("b_lines", "cad", "CAD", B_STEPS, "NOT is_subtotal",
             f"ERP-B (Lakeshore): {{n:,}} detail lines, CAD {{amt:.2f}}M  (+ {sub_n} SUBTOTAL rows, ignored: they repeat the detail)")]:
        total_n, total_amt = con.execute(f"SELECT count(*), sum({amount}) FROM {table} WHERE {where}").fetchone()
        rows = [(label, *con.execute(f"SELECT count(*), coalesce(sum({amount}), 0) FROM {table} WHERE {cond}").fetchone())
                for label, cond in steps]
        rows = [r for r in rows if r[1]]
        if sum(r[1] for r in rows) != total_n or sum(r[2] for r in rows) != total_amt:
            raise AssertionError(f"Funnel for {table} does not account for every line")
        bars = [(label, n, float(amt), f"{n:,} rows · {_money(unit, float(amt))}"
                 + (f"  (= {_money('USD', lks_usd)})" if unit == "CAD" and label.startswith("Included") else ""),
                 BLUE if label.startswith("Included") else GRAY) for label, n, amt in rows]
        panels.append((title.format(n=total_n, amt=float(total_amt) / 1e6), bars))

    treated = []
    for label, src, cond in TREATED:
        if src == "a":
            n, usd = con.execute(f"SELECT count(*), coalesce(sum(usd), 0) FROM a_lines WHERE {cond}").fetchone()
        else:
            n = con.execute(f"SELECT count(*) FROM b_lines b WHERE {cond}").fetchone()[0]
            usd = con.execute(_lks_usd(cond)).fetchone()[0] or 0
        if n:
            treated.append((label, n, float(usd), f"{n:,} rows · {_money('USD', float(usd))}", ORANGE))
    treated.sort(key=lambda t: -t[2])
    panels.append(("Kept in the number, but treated on the way in (USD of the lines affected)", treated))

    heights = [len(p[1]) for p in panels]
    fig, axes = plt.subplots(len(panels), 1, figsize=(8.6, 0.5 * sum(heights) + 2.4), gridspec_kw={"height_ratios": heights})
    for ax, (title, bars) in zip(axes, panels):
        y = range(len(bars))[::-1]
        top = max(b[2] for b in bars)
        for yi, (label, n, amt, text, color) in zip(y, bars):
            ax.barh(yi, amt, color=color, height=0.6)
            ax.text(amt + top * 0.015, yi, text, va="center", fontsize=9, color=INK if color != GRAY else MUTED)
        ax.set_yticks(list(y), [b[0] for b in bars], fontsize=9)
        ax.set_xlim(0, top * 1.6)
        ax.set_xticks([])
        ax.spines["bottom"].set_visible(False)
        ax.tick_params(axis="y", length=0)
        ax.set_title(title, loc="left", fontsize=10, wrap=True)
    fig.tight_layout(h_pad=1.6)
    _save(fig, path)
