"""One scan cycle (run by GitHub Actions every 15 min). PAPER trading only: simulated money, real market data."""
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import core
import dashboard

ROOT = Path(__file__).parent
STATE = ROOT / "data" / "state.json"
SYMS = [s.strip().upper() for s in os.getenv("SYMBOLS", "BTC,ETH,SOL,DOGE").split(",") if s.strip()]
START_EQ = float(os.getenv("START_EQUITY", "1000"))
RISK_PCT = float(os.getenv("RISK_PCT", "1"))
MAX_OPEN = int(os.getenv("MAX_OPEN", "3"))
ALLOW_SHORT = os.getenv("ALLOW_SHORT", "1") == "1"
DAILY_LIMIT_R = -3.0
HOLD_SEC = 96 * core.TF_MIN * 60


def load():
    try:
        return json.loads(STATE.read_text())
    except Exception:
        return {"equity": START_EQ, "start_equity": START_EQ, "open": [], "closed": [], "last_signal": {},
                "curve": [], "bt": {}, "bt_ts": 0, "blocked": {}, "next_id": 1, "scan": {}}


def save(s):
    STATE.parent.mkdir(exist_ok=True)
    STATE.write_text(json.dumps(s))


def tg(text):
    tok, chat = os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
    if not (tok and chat):
        return
    try:
        import httpx
        httpx.post(f"https://api.telegram.org/bot{tok}/sendMessage", json={"chat_id": chat, "text": text[:4000]}, timeout=20)
    except Exception:
        pass


def usd_news_blackout():
    """High-impact USD news (ForexFactory mirror): block entries 30 min before to 15 min after."""
    try:
        import httpx
        ev = httpx.get("https://nfs.faireconomy.media/ff_calendar_thisweek.json", timeout=15,
                       headers={"User-Agent": "Mozilla/5.0"}).json()
        now = time.time()
        for e in ev:
            if e.get("country") == "USD" and e.get("impact") == "High":
                t = datetime.fromisoformat(e["date"]).timestamp()
                if -15 * 60 <= t - now <= 30 * 60:
                    return e.get("title", "USD news")
    except Exception:
        pass
    return None


def gemini_review(sig, S, i):
    """Optional AI second opinion (free Gemini key). Returns (approve, text). Fails open to rules-only."""
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        return True, ""
    try:
        import httpx
        c = S.c
        prompt = ("You are a strict trading risk reviewer. Approve ONLY clean, high-quality setups; reject choppy or "
                  "late entries. Reply JSON {\"approve\":bool,\"confidence\":0-100,\"reason\":\"max 20 words\"}.\n" +
                  json.dumps({"signal": sig, "last_30_closes": [round(x[4], 6) for x in c[i - 29:i + 1]],
                              "ema20": S.e20[i], "ema50": S.e50[i], "ema200": S.e200[i], "atr": S.atr[i]}))
        body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {"responseMimeType": "application/json", "temperature": 0.1, "maxOutputTokens": 1024}}
        h = {"x-goog-api-key": key}
        base = "https://generativelanguage.googleapis.com/v1beta/models"
        names = [os.getenv("GEMINI_MODEL", "gemini-3.8-flash")]
        try:
            for m in httpx.get(base, headers=h, params={"pageSize": 100}, timeout=20).json().get("models", []):
                n = m["name"].split("/")[-1]
                if "flash" in n and "generateContent" in m.get("supportedGenerationMethods", []) \
                        and not any(x in n for x in ("image", "tts", "live", "audio")) and n not in names:
                    names.append(n)
        except Exception:
            pass
        for n in names[:3]:
            r = httpx.post(f"{base}/{n}:generateContent", headers=h, json=body, timeout=60)
            if r.status_code == 200:
                txt = "".join(p.get("text", "") for p in r.json()["candidates"][0]["content"]["parts"])
                j = json.loads(txt[txt.index("{"):txt.rindex("}") + 1])
                return bool(j.get("approve")) and float(j.get("confidence", 0)) >= 60, str(j.get("reason", ""))[:150]
    except Exception:
        pass
    return True, ""


def close_trade(st, tr, status, r):
    tr.update(status=status, r=round(r, 2), pnl=round(r * tr["risk_usd"], 2), closed=int(time.time()))
    st["equity"] = round(st["equity"] + tr["pnl"], 2)
    st["closed"].append(tr)
    st["closed"] = st["closed"][-500:]
    icon = {"win": "✅", "loss": "❌"}.get(status, "⏱")
    tg(f"{icon} Paper trade #{tr['id']} {tr['symbol']} {tr['side']} closed: {status.upper()} {tr['r']:+.2f}R "
       f"({tr['pnl']:+.2f} USD). Equity {st['equity']}")


def update_open(st, data):
    keep = []
    for tr in st["open"]:
        buy, risk = tr["side"] == "BUY", abs(tr["entry"] - tr["sl"])
        cost = core.FEE_PCT / 100 * tr["entry"] / risk
        entry_t = tr["t"] + core.TF_MIN * 60
        later = [x for x in data.get(tr["symbol"], []) if x[0] >= entry_t]
        res = None
        for x in later:
            if (x[3] <= tr["sl"]) if buy else (x[2] >= tr["sl"]):
                res = ("loss", -1 - cost)
                break
            if (x[2] >= tr["tp"]) if buy else (x[3] <= tr["tp"]):
                res = ("win", tr["rr"] - cost)
                break
        if not res and later and time.time() - entry_t > HOLD_SEC:
            px = later[-1][4]
            res = ("timeout", ((px - tr["entry"]) if buy else (tr["entry"] - px)) / risk - cost)
        if res:
            close_trade(st, tr, *res)
        else:
            keep.append(tr)
    st["open"] = keep


def refresh_backtest(st, data):
    agg = {n: [] for n in core.STRATS}
    for sym, c in data.items():
        if len(c) > 300:
            for n, fn in core.STRATS.items():
                agg[n] += core.backtest(c, fn)
    st["bt"] = {n: core.summarize(rs) for n, rs in agg.items()}
    st["blocked"] = {}
    for n, b in st["bt"].items():
        if b["n"] >= 10 and b["avg_r"] <= 0:
            st["blocked"][n] = f"backtest avg {b['avg_r']}R over {b['n']} trades"
        live = [t["r"] for t in st["closed"] if t["strategy"] == n]
        if len(live) >= 10 and sum(live) / len(live) <= -0.3:
            st["blocked"][n] = f"live paper avg {sum(live) / len(live):.2f}R over {len(live)} trades"
    st["bt_ts"] = time.time()


def scan(st, data):
    news = usd_news_blackout()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    day_r = sum(t["r"] for t in st["closed"] if datetime.fromtimestamp(t["closed"], timezone.utc).strftime("%Y-%m-%d") == today)
    for sym, c in data.items():
        if len(c) < 230:
            continue
        S, i = core.Series(c), len(c) - 1
        fresh = time.time() - (c[i][0] + core.TF_MIN * 60) < 3 * core.TF_MIN * 60
        st["scan"][sym] = {"price": c[i][4], "atr_pct": round(100 * S.atr[i] / c[i][4], 2),
                           "trend": "up" if S.e50[i] > S.e200[i] else "down", "fresh": fresh, "t": c[i][0]}
        if not fresh:
            continue
        for name, fn in core.STRATS.items():
            sig = fn(S, i)
            key = f"{sym}:{name}"
            if not sig or st["last_signal"].get(key) == sig["t"] or name in st["blocked"]:
                continue
            st["last_signal"][key] = sig["t"]
            why = None
            if sig["side"] == "SELL" and not ALLOW_SHORT:
                why = "shorts disabled"
            elif day_r <= DAILY_LIMIT_R:
                why = "daily loss limit"
            elif len(st["open"]) >= MAX_OPEN or any(t["symbol"] == sym for t in st["open"]):
                why = "max open / symbol busy"
            elif news:
                why = f"news: {news}"
            if why:
                continue
            ok, note = gemini_review(sig, S, i)
            if not ok:
                tg(f"🚫 AI rejected {sym} {sig['side']} [{name}]: {note}")
                continue
            risk = abs(sig["entry"] - sig["sl"])
            notional = min(st["equity"] * RISK_PCT / 100 * sig["entry"] / risk, st["equity"] * 0.5)
            tr = dict(sig, id=st["next_id"], symbol=sym, risk_usd=round(notional * risk / sig["entry"], 2),
                      notional=round(notional, 2), ai=note, opened=int(time.time()))
            st["next_id"] += 1
            st["open"].append(tr)
            tg(f"{'🟢 BUY' if sig['side'] == 'BUY' else '🔴 SELL'} {sym} {core.TF_MIN}m [{name}] PAPER trade #{tr['id']}\n"
               f"Entry {sig['entry']:.6g}  SL {sig['sl']:.6g}  TP {sig['tp']:.6g}  RR {sig['rr']}\n"
               f"Risk {tr['risk_usd']} USD. {sig['note']}. {('AI: ' + note) if note else ''}\nSimulated; not financial advice.")


def apply_cash(st):
    """Simulated deposit/withdraw, triggered only by you via the workflow's manual-run input."""
    try:
        amt = float(os.getenv("PAPER_CASH", "0") or 0)
    except ValueError:
        amt = 0
    if amt and st["equity"] + amt >= 0:
        st["equity"] = round(st["equity"] + amt, 2)
        st["start_equity"] = round(st["start_equity"] + amt, 2)
        st.setdefault("ledger", []).append([int(time.time()), amt])
        tg(f"{'Deposited' if amt > 0 else 'Withdrew'} {abs(amt):,.2f} simulated USD. Equity {st['equity']}")


def main():
    st = load()
    apply_cash(st)
    data = {s: core.fetch_candles(s) for s in SYMS}
    update_open(st, data)
    if time.time() - st.get("bt_ts", 0) > 86400:
        refresh_backtest(st, data)
    scan(st, data)
    now = int(time.time())
    if not st["curve"] or st["curve"][-1][1] != st["equity"] or now - st["curve"][-1][0] > 3600:
        st["curve"].append([now, st["equity"]])
        st["curve"] = st["curve"][-3000:]
    st["last_run"] = now
    save(st)
    dashboard.render(st, ROOT / "docs" / "index.html", data)
    print("ok", {k: len(v) for k, v in data.items()}, "open", len(st["open"]), "closed", len(st["closed"]))


if __name__ == "__main__":
    main()
