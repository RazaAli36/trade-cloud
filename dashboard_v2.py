"""trade-cloud dashboard v2: static page, all charts are fixed-ratio inline SVG drawn here in Python.
No canvas, no iframes, no external scripts, so nothing can grow, stretch or fail to load on a phone."""
import html
import time
from datetime import datetime, timezone

import core

CSS = """
:root{--bg:#070b12;--card:#0e141d;--line:#1b2432;--tx:#d3dbe6;--mu:#7a8797;--gr:#22c55e;--rd:#ff4d5e;--am:#fbbf24;--bl:#4da3ff}
*{box-sizing:border-box}
html{background:var(--bg);color-scheme:dark}
body{margin:0;padding:14px 12px 40px;color:var(--tx);font:14px/1.45 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
 max-width:760px;margin-inline:auto;-webkit-text-size-adjust:100%}
h1{font-size:17px;margin:4px 0 8px;letter-spacing:.5px}
h2{font-size:11px;font-weight:600;color:var(--mu);letter-spacing:1.5px;text-transform:uppercase;margin:0 0 10px}
.badge{display:inline-block;padding:3px 8px;border:1px solid #6b5313;background:#2a2108;color:var(--am);border-radius:6px;font-size:11px;font-weight:700}
.sub{color:var(--mu);font-size:12px;margin:6px 0 12px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px;margin:0 0 12px;overflow:hidden}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.k{color:var(--mu);font-size:11px;letter-spacing:1px;text-transform:uppercase}
.v{font-size:22px;font-weight:700;margin-top:2px}
.big{font-size:34px}
.gr{color:var(--gr)}.rd{color:var(--rd)}.am{color:var(--am)}.mu{color:var(--mu)}
svg{display:block;width:100%;height:auto}
.tabs{display:flex;gap:6px;margin:0 0 10px;flex-wrap:wrap}
.tab{background:#0a0f17;border:1px solid var(--line);color:var(--mu);border-radius:8px;padding:6px 12px;font:inherit;font-size:12px}
.tab.on{border-color:var(--bl);color:var(--tx);background:#10213a}
.pane{display:none}.pane.on{display:block}
.scroll{overflow-x:auto;-webkit-overflow-scrolling:touch}
table{border-collapse:collapse;width:100%;font-size:12px;white-space:nowrap}
th{color:var(--mu);font-weight:500;text-align:left;padding:5px 8px;border-bottom:1px solid var(--line)}
td{padding:6px 8px;border-bottom:1px solid #121a26}
.strat{border:1px solid var(--line);border-radius:10px;padding:10px;margin:0 0 8px;background:#0a0f17}
.strat.ok{border-color:#14452c;background:#0a1a14}.strat.no{border-color:#4a1d25;background:#1a0d11}
.pill{font-size:10px;letter-spacing:1px;color:var(--mu)}
.flow{display:flex;flex-direction:column;gap:6px}
.step{border:1px solid var(--line);border-radius:10px;padding:9px 11px;background:#0a0f17;display:flex;justify-content:space-between;gap:10px}
.arrow{text-align:center;color:var(--mu);line-height:1;font-size:12px}
.log div{padding:3px 0;border-bottom:1px solid #121a26;font-size:12px;word-break:break-word}
.note{color:var(--mu);font-size:11px;line-height:1.5}
"""

JS = """
document.querySelectorAll('[data-tabs]').forEach(function(box){
 var tabs=box.querySelectorAll('.tab'),panes=box.querySelectorAll('.pane');
 tabs.forEach(function(t,i){t.addEventListener('click',function(){
  tabs.forEach(function(x){x.classList.remove('on')});panes.forEach(function(x){x.classList.remove('on')});
  t.classList.add('on');panes[i].classList.add('on');});});});
"""


def esc(x):
    return html.escape(str(x))


def fp(x):
    x = float(x)
    if abs(x) >= 1000:
        return f"{x:,.2f}"
    if abs(x) >= 1:
        return f"{x:.4f}".rstrip("0").rstrip(".")
    return f"{x:.6f}".rstrip("0").rstrip(".")


def money(x, sign=False):
    return f"{'+' if sign and x > 0 else ''}{'-' if x < 0 else ''}${abs(x):,.2f}"


def cls(x):
    return "gr" if x > 0 else "rd" if x < 0 else "mu"


def ts(t, fmt="%d %b %H:%M"):
    return datetime.fromtimestamp(t, timezone.utc).strftime(fmt)


def svg_wrap(w, h, body):
    return f'<svg viewBox="0 0 {w} {h}" preserveAspectRatio="xMidYMid meet" role="img">{body}</svg>'


def empty_chart(msg, h=120):
    return svg_wrap(360, h, f'<text x="180" y="{h // 2}" fill="#7a8797" font-size="11" text-anchor="middle">{esc(msg)}</text>')


def candle_chart(c, trades):
    c = c[-60:]
    if len(c) < 5:
        return empty_chart("no candles yet", 160)
    W, H, L, R, T, B = 360, 230, 4, 304, 8, 18
    hi = max(x[2] for x in c)
    lo = min(x[3] for x in c)
    for t in trades:
        for k in ("sl", "tp"):
            hi, lo = max(hi, t[k]), min(lo, t[k])
    pad = (hi - lo) * 0.05 or hi * 0.01
    hi, lo = hi + pad, lo - pad
    y = lambda p: T + (hi - p) / (hi - lo) * (H - T - B)
    step = (R - L) / len(c)
    o = []
    for i in range(5):
        p = lo + (hi - lo) * i / 4
        o.append(f'<line x1="{L}" x2="{R}" y1="{y(p):.1f}" y2="{y(p):.1f}" stroke="#16202d" stroke-width="1"/>'
                 f'<text x="{R + 4}" y="{y(p) + 3:.1f}" fill="#7a8797" font-size="9">{fp(p)}</text>')
    for i, (t0, op, h, l, cl) in enumerate(c):
        col = "#22c55e" if cl >= op else "#ff4d5e"
        x = L + step * (i + 0.5)
        top, bot = y(max(op, cl)), y(min(op, cl))
        o.append(f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{y(h):.1f}" y2="{y(l):.1f}" stroke="{col}" stroke-width="1"/>'
                 f'<rect x="{x - step * 0.34:.1f}" y="{top:.1f}" width="{step * 0.68:.1f}" height="{max(bot - top, 1):.1f}" fill="{col}"/>')
    for t in trades:
        for k, col in (("entry", "#4da3ff"), ("sl", "#ff4d5e"), ("tp", "#22c55e")):
            o.append(f'<line x1="{L}" x2="{R}" y1="{y(t[k]):.1f}" y2="{y(t[k]):.1f}" stroke="{col}" stroke-dasharray="4 3" stroke-width="1"/>'
                     f'<text x="{L + 2}" y="{y(t[k]) - 2:.1f}" fill="{col}" font-size="9">{k.upper()} #{t["id"]}</text>')
    last = c[-1][4]
    o.append(f'<line x1="{L}" x2="{R}" y1="{y(last):.1f}" y2="{y(last):.1f}" stroke="#fbbf24" stroke-width="1" stroke-dasharray="1 3"/>'
             f'<rect x="{R + 1}" y="{y(last) - 7:.1f}" width="55" height="13" fill="#fbbf24"/>'
             f'<text x="{R + 4}" y="{y(last) + 3:.1f}" fill="#0b0f16" font-size="9" font-weight="700">{fp(last)}</text>')
    o.append(f'<text x="{L}" y="{H - 4}" fill="#7a8797" font-size="9">{ts(c[0][0])}</text>'
             f'<text x="{R}" y="{H - 4}" fill="#7a8797" font-size="9" text-anchor="end">{ts(c[-1][0])} UTC</text>')
    return svg_wrap(W, H, "".join(o))


def equity_chart(curve, start):
    pts = [p for p in curve if len(p) == 2]
    if len(pts) < 2:
        return empty_chart("equity curve starts after the second data point")
    if len(pts) > 160:
        k = len(pts) / 160
        pts = [pts[int(i * k)] for i in range(160)] + [pts[-1]]
    W, H, L, R, T, B = 360, 170, 4, 308, 10, 18
    t0, t1 = pts[0][0], pts[-1][0]
    vals = [p[1] for p in pts] + [start]
    lo, hi = min(vals), max(vals)
    pad = max((hi - lo) * 0.1, hi * 0.002, 0.5)
    lo, hi = lo - pad, hi + pad
    x = lambda t: L + ((t - t0) / (t1 - t0) if t1 > t0 else 0) * (R - L)
    y = lambda v: T + (hi - v) / (hi - lo) * (H - T - B)
    line = " ".join(f"{x(t):.1f},{y(v):.1f}" for t, v in pts)
    up = pts[-1][1] >= start
    col = "#22c55e" if up else "#ff4d5e"
    area = f"{x(t0):.1f},{H - B} {line} {x(t1):.1f},{H - B}"
    o = [f'<polygon points="{area}" fill="{col}" fill-opacity=".12"/>',
         f'<line x1="{L}" x2="{R}" y1="{y(start):.1f}" y2="{y(start):.1f}" stroke="#2a3647" stroke-dasharray="4 3"/>',
         f'<polyline points="{line}" fill="none" stroke="{col}" stroke-width="1.6" stroke-linejoin="round"/>',
         f'<text x="{R + 3}" y="{y(pts[-1][1]) + 3:.1f}" fill="{col}" font-size="9">{pts[-1][1]:,.2f}</text>',
         f'<text x="{R + 3}" y="{y(start) + 3:.1f}" fill="#7a8797" font-size="9">start</text>',
         f'<text x="{L}" y="{H - 4}" fill="#7a8797" font-size="9">{ts(t0)}</text>',
         f'<text x="{R}" y="{H - 4}" fill="#7a8797" font-size="9" text-anchor="end">{ts(t1)}</text>']
    return svg_wrap(W, H, "".join(o))


def r_bars(closed):
    rs = [t.get("r", 0) for t in closed[-40:]]
    if not rs:
        return empty_chart("no closed trades yet")
    W, H, L, R, T, B = 360, 140, 4, 356, 8, 8
    m = max(1.0, max(abs(r) for r in rs))
    mid = (T + H - B) / 2
    k = (H - T - B) / 2 / m
    step = (R - L) / max(len(rs), 12)
    o = [f'<line x1="{L}" x2="{R}" y1="{mid}" y2="{mid}" stroke="#2a3647"/>']
    for i, r in enumerate(rs):
        h = abs(r) * k
        o.append(f'<rect x="{L + step * i + 1:.1f}" y="{(mid - h if r > 0 else mid):.1f}" width="{max(step - 2, 2):.1f}" '
                 f'height="{max(h, 1):.1f}" fill="{"#22c55e" if r > 0 else "#ff4d5e"}" rx="1"/>')
    o.append(f'<text x="{R}" y="{T + 8}" fill="#7a8797" font-size="9" text-anchor="end">+{m:.1f}R</text>'
             f'<text x="{R}" y="{H - 10}" fill="#7a8797" font-size="9" text-anchor="end">-{m:.1f}R</text>')
    return svg_wrap(W, H, "".join(o))


def table(head, rows, empty):
    if not rows:
        return f'<div class="mu">{esc(empty)}</div>'
    th = "".join(f"<th>{esc(h)}</th>" for h in head)
    return f'<div class="scroll"><table><tr>{th}</tr>{"".join(rows)}</table></div>'


def render(st, path, data):
    closed, opened = st.get("closed", []), st.get("open", [])
    equity, start = float(st.get("equity", 0)), float(st.get("start_equity", st.get("equity", 0)))
    pnl = equity - start
    n = len(closed)
    wins = sum(1 for t in closed if t.get("r", 0) > 0)
    avg_r = sum(t.get("r", 0) for t in closed) / n if n else 0.0
    scan = st.get("scan", {})
    last_run = st.get("last_run") or time.time()

    stats = (f'<div class="card"><div class="k">Net P&amp;L (simulated)</div>'
             f'<div class="v big {cls(pnl)}">{money(pnl, True)}</div>'
             f'<div class="sub">{n} closed trades · last scan {ts(max([s.get("t", 0) for s in scan.values()] or [last_run]), "%H:%M")} UTC</div>'
             f'<div class="grid"><div><div class="k">Equity</div><div class="v">${equity:,.2f}</div></div>'
             f'<div><div class="k">Win rate</div><div class="v">{(100 * wins / n if n else 0):.0f}%</div></div>'
             f'<div><div class="k">Avg / trade</div><div class="v {cls(avg_r)}">{avg_r:+.2f}R</div></div>'
             f'<div><div class="k">Open</div><div class="v">{len(opened)}</div></div></div></div>')

    # live charts with tabs
    syms = [s for s in data if data[s]] or list(data)
    tabs = "".join(f'<button class="tab{" on" if i == 0 else ""}">{esc(s)}</button>' for i, s in enumerate(syms))
    panes = "".join(
        f'<div class="pane{" on" if i == 0 else ""}">'
        f'{candle_chart(data[s], [t for t in opened if t.get("symbol") == s])}</div>' for i, s in enumerate(syms))
    live = (f'<div class="card" data-tabs><h2>Live chart · {core.TF_MIN}m candles</h2>'
            f'<div class="tabs">{tabs}</div>{panes}</div>')

    # market heat
    heat = []
    per_day = max(1, 1440 // core.TF_MIN)
    for s in syms:
        c = data.get(s) or []
        if len(c) > per_day:
            ch = 100 * (c[-1][4] / c[-per_day - 1][4] - 1)
            chs = f'<span class="{cls(ch)}">{ch:+.2f}%</span>'
        else:
            chs = '<span class="mu">n/a</span>'
        sc = scan.get(s, {})
        tr = sc.get("trend", "")
        heat.append(f'<div class="strat"><div class="k">{esc(s)}</div><div class="v" style="font-size:17px">'
                    f'{fp(c[-1][4]) if c else "-"}</div><div>24h {chs}</div>'
                    f'<div class="mu" style="font-size:11px">trend {esc(tr or "-")} · ATR {sc.get("atr_pct", "-")}%</div></div>')
    heat_card = f'<div class="card"><h2>Market heat (24h)</h2><div class="grid">{"".join(heat)}</div></div>'

    # strategies
    bt, blocked = st.get("bt", {}), st.get("blocked", {})
    srows = []
    for name in core.STRATS:
        b = bt.get(name, {})
        lv = [t.get("r", 0) for t in closed if t.get("strategy") == name]
        is_b = name in blocked
        srows.append(
            f'<div class="strat {"no" if is_b else "ok"}"><b>{esc(name.replace("_", " "))}</b> '
            f'<span class="pill">{"BLOCKED" if is_b else "ACTIVE"}</span>'
            f'<div class="mu" style="font-size:12px">backtest: {b.get("n", 0)} trades · win {b.get("win_rate", 0)}% · '
            f'avg <span class="{cls(b.get("avg_r", 0))}">{b.get("avg_r", 0):+}R</span><br>'
            f'live paper: {len(lv)} trades · total {sum(lv):+.2f}R'
            f'{"<br>" + esc(blocked[name]) if is_b else ""}</div></div>')
    strat_card = f'<div class="card"><h2>Strategies (backtest vs live paper)</h2>{"".join(srows)}</div>'

    # pipeline (simple vertical flow, no drawing)
    active = len(core.STRATS) - len(blocked)
    steps = [("1 · Market data", f"{len(syms)} symbols · Kraken / Coinbase"),
             ("2 · Strategies", f"{active} active · {len(blocked)} blocked"),
             ("3 · Filters", "news blackout · daily loss limit · max open"),
             ("4 · Paper trade", f"{len(opened)} open · {n} closed")]
    flow = '<div class="arrow">▼</div>'.join(
        f'<div class="step"><b>{esc(a)}</b><span class="mu">{esc(b)}</span></div>' for a, b in steps)
    pipe = f'<div class="card"><h2>Signal pipeline</h2><div class="flow">{flow}</div></div>'

    rcard = f'<div class="card"><h2>Closed trades (R multiple)</h2>{r_bars(closed)}</div>'
    ecard = f'<div class="card"><h2>Equity curve</h2>{equity_chart(st.get("curve", []), start)}</div>'

    # tables
    orows = []
    for t in opened:
        now = scan.get(t.get("symbol"), {}).get("price")
        risk = abs(t["entry"] - t["sl"]) or 1
        ur = (now - t["entry"]) / risk * (1 if t.get("side") == "BUY" else -1) if now else None
        orows.append(f'<tr><td>#{t.get("id")}</td><td>{esc(t.get("symbol"))}</td><td>{esc(t.get("side"))}</td>'
                     f'<td>{esc(str(t.get("strategy", "")).replace("_", " "))}</td><td>{fp(t["entry"])}</td>'
                     f'<td class="rd">{fp(t["sl"])}</td><td class="gr">{fp(t["tp"])}</td>'
                     f'<td>{fp(now) if now else "-"}</td><td class="{cls(ur or 0)}">{f"{ur:+.2f}R" if ur is not None else "-"}</td></tr>')
    open_card = (f'<div class="card"><h2>Open positions</h2>'
                 f'{table(["ID", "Sym", "Side", "Strategy", "Entry", "SL", "TP", "Now", "R"], orows, "none (bot waits for clean setups)")}</div>')
    crows = [f'<tr><td>#{t.get("id")}</td><td>{esc(t.get("symbol"))}</td><td>{esc(t.get("side"))}</td>'
             f'<td>{esc(str(t.get("strategy", "")).replace("_", " "))}</td><td class="{cls(t.get("r", 0))}">{t.get("r", 0):+.2f}R</td>'
             f'<td class="{cls(t.get("pnl", 0))}">{t.get("pnl", 0):+.2f}</td><td>{esc(t.get("status", ""))}</td></tr>'
             for t in reversed(closed[-20:])]
    closed_card = (f'<div class="card"><h2>Last 20 closed</h2>'
                   f'{table(["ID", "Sym", "Side", "Strategy", "R", "USD", "Exit"], crows, "no closed trades yet")}</div>')

    # event log
    ev = []
    for t in closed[-15:]:
        ev.append((t.get("closed", 0), f'<span class="{cls(t.get("r", 0))}">{esc(str(t.get("status", "")).upper())}</span> '
                   f'#{t.get("id")} {esc(t.get("side"))} {esc(t.get("symbol"))} [{esc(t.get("strategy"))}] {t.get("r", 0):+.2f}R'))
    for t in opened:
        ev.append((t.get("opened", 0), f'<span class="am">OPEN</span> #{t.get("id")} {esc(t.get("side"))} {esc(t.get("symbol"))} [{esc(t.get("strategy"))}]'))
    for name, why in blocked.items():
        ev.append((st.get("bt_ts", 0), f'<span class="rd">BLOCKED</span> {esc(name)}: {esc(why)}'))
    ev.sort(key=lambda e: -e[0])
    log = "".join(f'<div><span class="mu">{ts(a)}</span> {b}</div>' for a, b in ev[:12]) or '<div class="mu">no events yet</div>'
    log_card = f'<div class="card"><h2>Event log</h2><div class="log">{log}</div></div>'

    foot = ('<div class="note">Backtests use limited recent data and are noisy; blocked strategies lost money in testing. '
            'Past results do not predict profit. Simulated trades only.</div>')

    page = (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<meta http-equiv="refresh" content="300"><title>TRADE-CLOUD</title><style>{CSS}</style></head><body>'
            f'<h1>TRADE-CLOUD // AI TRADER</h1><span class="badge">PAPER: SIMULATED MONEY, REAL PRICES</span>'
            f'<div class="sub">Updated {ts(last_run, "%Y-%m-%d %H:%M")} UTC · refreshes every 15 min on GitHub</div>'
            f'{stats}{live}{ecard}{open_card}{closed_card}{rcard}{heat_card}{strat_card}{pipe}{log_card}{foot}'
            f'<script>{JS}</script></body></html>')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(page, encoding="utf-8")
