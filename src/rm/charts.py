"""Charts for the docs, drawn from the same tables as the CSVs, so they change when a rule changes."""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

INK, MUTED, GRID, SURFACE = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
BLUE, GRAY = "#2a78d6", "#b9b8b3"

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
        labels.append(item.split(":")[0] if item.startswith("JE-") else _short(item))
        run += usd
    n = len(items)
    gap = float(accounting - finance)
    ax.plot([n - 1 + 0.275, n - 0.275], [run, run], color=MUTED, lw=0.8, ls=":")
    ax.bar(n, gap, color=MUTED, width=0.55)
    ax.text(n, gap, f"{gap:,.2f}\nresidual {gap - run:.2f}", ha="center", va="bottom", fontsize=9)
    labels.append("Accounting − Finance")
    ax.set_xticks(range(n + 1), labels, fontsize=9)
    ax.set_ylim(0, gap * 1.25)
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:,.0f}"))
    ax.set_ylabel("USD")
    ax.grid(axis="y", color=GRID, lw=0.6)
    ax.set_axisbelow(True)
    ax.set_title(f"Finance {float(finance):,.2f}  →  Accounting {float(accounting):,.2f}", loc="left", fontsize=11, pad=12)
    _save(fig, path)


def _short(item):
    if item.startswith("Lakeshore FX"):
        return "Lakeshore FX\n(close month at month-end)"
    if item.startswith("Suspected double posts"):
        return "Suspected\ndouble posts"
    return item[:28]


A_STEPS = [
    ("Re-export copies (24-Aug re-ran 22-Aug)", "is_reexport_copy"),
    ("Outside Q3 (rule 3)", "NOT is_reexport_copy AND NOT r3_in_q3"),
    ("Not an R&M account (rule 1)", "NOT is_reexport_copy AND r3_in_q3 AND NOT r1_rm_account"),
    ("Capex operation 75/100 (rule 2)", "NOT is_reexport_copy AND r3_in_q3 AND r1_rm_account AND r2_capex"),
    ("Suspected double posts (dropped by toggle)", "NOT is_reexport_copy AND r3_in_q3 AND r1_rm_account AND NOT r2_capex AND NOT included"),
    ("Included in Q3 R&M", "included"),
]
B_STEPS = [
    ("SUBTOTAL rows (repeat their detail)", "is_subtotal"),
    ("Outside Q3 (rule 3)", "NOT is_subtotal AND NOT r3_in_q3"),
    ("Not a 73xx-RM account (rule 6)", "NOT is_subtotal AND r3_in_q3 AND NOT r6_rm_account"),
    ("Included in Q3 R&M", "included"),
]


def funnel_chart(con, path):
    """Where every raw line goes: each line lands in exactly one bar, and the run checks that."""
    panels = []
    for table, amount, unit, steps, title in [
            ("a_lines", "usd", "USD", A_STEPS, "ERP-A (US branches)"),
            ("b_lines", "cad", "CAD", B_STEPS, "ERP-B (Lakeshore)")]:
        total_n, total_amt = con.execute(f"SELECT count(*), sum({amount}) FROM {table}").fetchone()
        rows = [(label, *con.execute(f"SELECT count(*), coalesce(sum({amount}), 0) FROM {table} WHERE {cond}").fetchone())
                for label, cond in steps]
        rows = [r for r in rows if r[1]]
        if sum(r[1] for r in rows) != total_n or sum(r[2] for r in rows) != total_amt:
            raise AssertionError(f"Funnel for {table} does not account for every raw line")
        panels.append((title, unit, total_n, total_amt, rows))

    heights = [len(p[4]) for p in panels]
    fig, axes = plt.subplots(2, 1, figsize=(8, 0.55 * sum(heights) + 1.6), gridspec_kw={"height_ratios": heights})
    for ax, (title, unit, total_n, total_amt, rows) in zip(axes, panels):
        y = range(len(rows))[::-1]
        for yi, (label, n, amt) in zip(y, rows):
            inc = label.startswith("Included")
            ax.barh(yi, float(amt), color=BLUE if inc else GRAY, height=0.6)
            ax.text(float(amt) + float(total_amt) * 0.01, yi, f"{n:,} rows · {unit} {float(amt) / 1e6:,.2f}M",
                    va="center", fontsize=9, color=INK if inc else MUTED)
        ax.set_yticks(list(y), [r[0] for r in rows], fontsize=9)
        ax.set_xlim(0, float(max(r[2] for r in rows)) * 1.45)
        ax.set_xticks([])
        ax.spines["bottom"].set_visible(False)
        ax.tick_params(axis="y", length=0)
        ax.set_title(f"{title}: {total_n:,} raw lines, {unit} {float(total_amt) / 1e6:,.2f}M", loc="left", fontsize=10.5)
    fig.tight_layout(h_pad=1.5)
    _save(fig, path)
