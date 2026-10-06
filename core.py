"""Market data, indicators, strategies, backtest. Candle = (t, open, high, low, close)."""
import os
import time

TF_MIN = int(os.getenv("TF_MIN", "60"))
FEE_PCT = float(os.getenv("FEE_PCT", "0.1"))  # round-trip fees + slippage, in percent
SYMBOLS = {"BTC": ("XBTUSD", "BTC-USD"), "ETH": ("ETHUSD", "ETH-USD"), "SOL": ("SOLUSD", "SOL-USD"),
           "DOGE": ("XDGUSD", "DOGE-USD"), "XRP": ("XRPUSD", "XRP-USD")}


def fetch_yahoo(sym: str) -> list:
    """Stocks via Yahoo's unofficial chart endpoint (best effort; may rate-limit)."""
    import httpx
    try:
        j = httpx.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}", params={"interval": "15m", "range": "30d"},
                      headers={"User-Agent": "Mozilla/5.0"}, timeout=20).json()
        r = j["chart"]["result"][0]
        q = r["indicators"]["quote"][0]
        out = [(int(t), float(o), float(h), float(l), float(c)) for t, o, h, l, c in
               zip(r["timestamp"], q["open"], q["high"], q["low"], q["close"]) if None not in (o, h, l, c)]
        return out[:-1] if out and out[-1][0] + TF_MIN * 60 > time.time() else out
    except Exception:
        return []


def fetch_candles(sym: str) -> list:
    """Crypto: Kraken first, Coinbase backup (public, no key). Anything else is treated as a stock ticker."""
    import httpx
    if sym not in SYMBOLS:
        return fetch_yahoo(sym)
    kr, cb = SYMBOLS[sym]
    try:
        j = httpx.get("https://api.kraken.com/0/public/OHLC", params={"pair": kr, "interval": TF_MIN}, timeout=20).json()
        if not j.get("error"):
            rows = next(v for k, v in j["result"].items() if k != "last")
            return [(int(x[0]), float(x[1]), float(x[2]), float(x[3]), float(x[4])) for x in rows][:-1]
    except Exception:
        pass
    try:
        rows = sorted(httpx.get(f"https://api.exchange.coinbase.com/products/{cb}/candles",
                                params={"granularity": TF_MIN * 60}, headers={"User-Agent": "bot"}, timeout=20).json(),
                      key=lambda x: x[0])
        c = [(int(x[0]), float(x[3]), float(x[2]), float(x[1]), float(x[4])) for x in rows]
        return c[:-1] if c and c[-1][0] + TF_MIN * 60 > time.time() else c
    except Exception:
        return []


def ema(vals, n):
    k, out, e = 2 / (n + 1), [], None
    for v in vals:
        e = v if e is None else v * k + e * (1 - k)
        out.append(e)
    return out


def atr_series(c, n=14):
    out, a, trs = [None], None, []
    for i in range(1, len(c)):
        tr = max(c[i][2] - c[i][3], abs(c[i][2] - c[i - 1][4]), abs(c[i][3] - c[i - 1][4]))
        trs.append(tr)
        if len(trs) == n:
            a = sum(trs) / n
        elif len(trs) > n:
            a = (a * (n - 1) + tr) / n
        out.append(a)
    return out


class Series:
    def __init__(self, c):
        self.c = c
        cl = [x[4] for x in c]
        self.e20, self.e50, self.e200 = ema(cl, 20), ema(cl, 50), ema(cl, 200)
        self.atr = atr_series(c)


def swings(S, i, kind, look=80, k=3):
    """Confirmed fractal swing highs/lows (idx, price) in the window, oldest first."""
    c, out = S.c, []
    for j in range(max(k, i - look), i - k):
        w = range(j - k, j + k + 1)
        if kind == "h" and all(c[j][2] >= c[x][2] for x in w):
            out.append((j, c[j][2]))
        if kind == "l" and all(c[j][3] <= c[x][3] for x in w):
            out.append((j, c[j][3]))
    return out


def finalize(S, i, name, side, sl, tp=None, note=""):
    c, a = S.c, S.atr[i]
    e = c[i][4]
    risk = abs(e - sl)
    if not a or risk < 0.5 * a or risk > 3 * a:
        return None
    if tp is None or abs(tp - e) < 2 * risk or (tp - e) * (1 if side == "BUY" else -1) <= 0:
        tp = e + 2 * risk if side == "BUY" else e - 2 * risk
    return {"strategy": name, "side": side, "entry": e, "sl": sl, "tp": tp,
            "rr": round(abs(tp - e) / risk, 2), "note": note, "t": c[i][0]}


def liquidity_sweep(S, i):
    """Wick through an obvious swing high/low, close back inside, then displacement back the other way."""
    c, a = S.c, S.atr[i]
    if i < 120 or not a or a / c[i][4] < 0.0015:
        return None
    highs, lows = swings(S, i - 1, "h"), swings(S, i - 1, "l")
    for j in (i - 1, i - 2):
        if any(c[j][3] < p < c[j][4] for _, p in lows) and c[i][4] > c[j][2] and c[i][4] > c[i][1] \
                and not (S.e50[i] < S.e200[i] and c[i][4] < S.e200[i]):
            sl = min(x[3] for x in c[j:i + 1]) - 0.1 * a
            above = [p for _, p in highs if p > c[i][4]]
            return finalize(S, i, "liquidity_sweep", "BUY", sl, min(above) if above else None, "sell-side sweep + displacement up")
        if any(c[j][4] < p < c[j][2] for _, p in highs) and c[i][4] < c[j][3] and c[i][4] < c[i][1] \
                and not (S.e50[i] > S.e200[i] and c[i][4] > S.e200[i]):
            sl = max(x[2] for x in c[j:i + 1]) + 0.1 * a
            below = [p for _, p in lows if p < c[i][4]]
            return finalize(S, i, "liquidity_sweep", "SELL", sl, max(below) if below else None, "buy-side sweep + displacement down")
    return None


def trend_pullback(S, i):
    c, a = S.c, S.atr[i]
    if i < 220 or not a or a / c[i][4] < 0.0015:
        return None
    last = range(i - 5, i + 1)
    if S.e20[i] > S.e50[i] > S.e200[i] and any(c[k][3] <= S.e50[k] for k in last) \
            and c[i][4] > S.e20[i] and c[i][4] > c[i][1] and c[i][4] > c[i - 1][2]:
        return finalize(S, i, "trend_pullback", "BUY", min(c[k][3] for k in last) - 0.1 * a, None, "pullback to EMA50 in uptrend")
    if S.e20[i] < S.e50[i] < S.e200[i] and any(c[k][2] >= S.e50[k] for k in last) \
            and c[i][4] < S.e20[i] and c[i][4] < c[i][1] and c[i][4] < c[i - 1][3]:
        return finalize(S, i, "trend_pullback", "SELL", max(c[k][2] for k in last) + 0.1 * a, None, "pullback to EMA50 in downtrend")
    return None


def breakout_retest(S, i):
    c, a = S.c, S.atr[i]
    if i < 220 or not a or a / c[i][4] < 0.0015:
        return None
    R, Sx = max(x[2] for x in c[i - 48:i - 8]), min(x[3] for x in c[i - 48:i - 8])
    if not 1.5 * a <= R - Sx <= 12 * a:
        return None
    for b in range(i - 7, i - 1):
        if c[b][4] > R and all(c[x][4] > R - 0.3 * a for x in range(b, i + 1)) and c[i][4] > R and c[i][4] > c[i][1]:
            ks = [k for k in range(b + 1, i + 1) if c[k][3] <= R + 0.2 * a]
            if ks:
                return finalize(S, i, "breakout_retest", "BUY", min(c[k][3] for k in ks) - 0.1 * a, None, "range breakout, retest held")
        if c[b][4] < Sx and all(c[x][4] < Sx + 0.3 * a for x in range(b, i + 1)) and c[i][4] < Sx and c[i][4] < c[i][1]:
            ks = [k for k in range(b + 1, i + 1) if c[k][2] >= Sx - 0.2 * a]
            if ks:
                return finalize(S, i, "breakout_retest", "SELL", max(c[k][2] for k in ks) + 0.1 * a, None, "range breakdown, retest rejected")
    return None


STRATS = {"liquidity_sweep": liquidity_sweep, "trend_pullback": trend_pullback, "breakout_retest": breakout_retest}


def simulate(c, i, s, hold=96):
    """Returns (R after costs, exit index). SL checked first when both hit in one candle (conservative)."""
    e, sl, tp, buy = s["entry"], s["sl"], s["tp"], s["side"] == "BUY"
    risk = abs(e - sl)
    cost = FEE_PCT / 100 * e / risk
    for j in range(i + 1, min(len(c), i + 1 + hold)):
        if (c[j][3] <= sl) if buy else (c[j][2] >= sl):
            return -1 - cost, j
        if (c[j][2] >= tp) if buy else (c[j][3] <= tp):
            return s["rr"] - cost, j
    j = min(len(c) - 1, i + hold)
    return ((c[j][4] - e) if buy else (e - c[j][4])) / risk - cost, j


def backtest(c, fn):
    S, rs, i = Series(c), [], 220
    while i < len(c) - 1:
        s = fn(S, i)
        if not s:
            i += 1
            continue
        r, j = simulate(c, i, s)
        rs.append(r)
        i = j + 1
    return rs


def summarize(rs):
    n = len(rs)
    return {"n": n, "win_rate": round(100 * sum(r > 0 for r in rs) / n, 1) if n else 0.0,
            "avg_r": round(sum(rs) / n, 2) if n else 0.0, "total_r": round(sum(rs), 2)}
