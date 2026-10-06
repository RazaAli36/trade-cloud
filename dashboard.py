"""Static dark dashboard (inline HTML/CSS/SVG, no external requests). Served by GitHub Pages from docs/."""
import html
from datetime import datetime, timezone

CSS = """:root{--bg:#0b0f14;--card:#121923;--line:#1f2a38;--tx:#d7e0ea;--mut:#7d8ca0;--g:#22c55e;--r:#ef4444}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--tx);font:14px/1.4 ui-monospace,Menlo,Consolas,monospace;padding:12px}
h1{font-size:15px;margin:0 0 4px}h2{font-size:12px;color:var(--mut);text-transform:uppercase;letter-spacing:.08em;margin:0 0 8px}
.badge{display:inline-block;background:#3b2f0b;color:#fbbf24;border:1px solid #6b540f;border-radius:6px;padding:2px 8px;font-size:11px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:8px;margin:10px 0}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px;margin-bottom:8px;overflow-x:auto}
.big{font-size:22px;font-weight:700}.g{color:var(--g)}.r{color:var(--r)}.m{color:var(--mut)}
table{width:100%;border-collapse:collapse;font-size:12px}th,td{padding:4px 6px;border-bottom:1px solid var(--line);text-align:left;white-space:nowrap}th{color:var(--mut);font-weight:400}"""


def e(x):
    return html.escape(str(x))


def cls(v):
    return "g" if v > 0 else "r" if v < 0 else ""


def curve_svg(curve):
    if len(curve) < 2:
        return '<div class="m">Equity curve appears after a few scans.</div>'
    w, h = 640, 150
    ys = [p[1] for p in curve]
    lo, hi = min(ys), max(ys)
    span = (hi - lo) or 1
    pts = [(i / (len(curve) - 1) * w, h - 8 - (y - lo) / span * (h - 16)) for i, y in enumerate(ys)]
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    col = "#22c55e" if ys[-1] >= ys[0] else "#ef4444"
    return (f'<svg viewBox="0 0 {w} {h}" width="100%" preserveAspectRatio="none"><polygon points="0,{h} {line} {w},{h}" '
            f'fill="{col}" opacity=".12"/><polyline points="{line}" fill="none" stroke="{col}" stroke-width="2"/></svg>')


def render(st, path):
    closed, eq, start = st["closed"], st["equity"], st["start_equity"]
    pnl = round(eq - start, 2)
    wins = sum(1 for t in closed if t["r"] > 0)
    n = len(closed)
    wr = f"{100 * wins / n:.0f}%" if n else "-"
    avg = f"{sum(t['r'] for t in closed) / n:+.2f}R" if n else "-"
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    def rows(items, cols):
        return "".join("<tr>" + "".join(f"<td>{c(t)}</td>" for c in cols) + "</tr>" for t in items) or '<tr><td class="m">none</td></tr>'

    open_rows = rows(st["open"], [lambda t: f"#{t['id']}", lambda t: e(t["symbol"]),
                                  lambda t: f'<span class="{"g" if t["side"] == "BUY" else "r"}">{t["side"]}</span>',
                                  lambda t: e(t["strategy"]), lambda t: f"{t['entry']:.6g}", lambda t: f"{t['sl']:.6g}",
                                  lambda t: f"{t['tp']:.6g}", lambda t: t["rr"]])
    closed_rows = rows(reversed(closed[-20:]), [lambda t: f"#{t['id']}", lambda t: e(t["symbol"]), lambda t: e(t["side"]),
                                                lambda t: e(t["strategy"]),
                                                lambda t: f'<span class="{cls(t["r"])}">{t["r"]:+.2f}R</span>',
                                                lambda t: f'<span class="{cls(t["pnl"])}">{t["pnl"]:+.2f}</span>', lambda t: e(t["status"])])
    strat_rows = ""
    for name, b in st["bt"].items():
        live = [t["r"] for t in closed if t["strategy"] == name]
        blk = st["blocked"].get(name)
        strat_rows += (f"<tr><td>{e(name)}</td><td>{b['n']}</td><td>{b['win_rate']}%</td>"
                       f"<td class=\"{cls(b['avg_r'])}\">{b['avg_r']:+.2f}R</td><td>{len(live)}</td>"
                       f"<td class=\"{'r' if blk else 'g'}\">{'BLOCKED: ' + e(blk) if blk else 'active'}</td></tr>")
    scan_rows = rows(st["scan"].items(), [lambda kv: e(kv[0]), lambda kv: f"{kv[1]['price']:.6g}",
                                          lambda kv: e(kv[1]["trend"]), lambda kv: f"{kv[1]['atr_pct']}%",
                                          lambda kv: "live" if kv[1]["fresh"] else "market closed"])
    page = f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="120"><title>Trade Cloud</title><style>{CSS}</style></head><body>
<h1>TRADE-CLOUD // AI PAPER TRADER <span class="badge">SIMULATED MONEY, REAL MARKET DATA</span></h1>
<div class="m">Updated {e(now)}. Runs on GitHub servers every 15 min, no phone needed.</div>
<div class="grid">
<div class="card"><h2>Equity</h2><div class="big">${eq:,.2f}</div></div>
<div class="card"><h2>P&amp;L</h2><div class="big {cls(pnl)}">{pnl:+,.2f}</div></div>
<div class="card"><h2>Win rate</h2><div class="big">{wr}</div><div class="m">{n} closed</div></div>
<div class="card"><h2>Avg / trade</h2><div class="big">{avg}</div></div></div>
<div class="card"><h2>Equity curve</h2>{curve_svg(st["curve"])}</div>
<div class="card"><h2>Open positions</h2><table><tr><th>ID</th><th>Sym</th><th>Side</th><th>Strategy</th><th>Entry</th><th>SL</th><th>TP</th><th>RR</th></tr>{open_rows}</table></div>
<div class="card"><h2>Last 20 closed</h2><table><tr><th>ID</th><th>Sym</th><th>Side</th><th>Strategy</th><th>R</th><th>USD</th><th>Exit</th></tr>{closed_rows}</table></div>
<div class="card"><h2>Strategies (backtest vs live paper)</h2><table><tr><th>Name</th><th>BT n</th><th>BT win</th><th>BT avg</th><th>Live n</th><th>Status</th></tr>{strat_rows}</table>
<div class="m">Backtests use only limited recent data and are noisy. Strategies with a clearly negative result are blocked automatically.</div></div>
<div class="card"><h2>Market scan</h2><table><tr><th>Sym</th><th>Price</th><th>Trend</th><th>ATR</th><th>Feed</th></tr>{scan_rows}</table></div>
<div class="m">Past results do not predict future profit. No strategy wins every trade.</div></body></html>"""
    path.parent.mkdir(exist_ok=True)
    path.write_text(page, encoding="utf-8")
