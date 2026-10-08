"""Binance SPOT executor for trade-cloud. Long-only: market BUY, then an exchange-side OCO (take-profit + stop-loss)
so your stop still works if the phone/bot is offline. Used by run.py when MODE is 'testnet' or 'live'."""
import hashlib
import hmac
import os
import time
from decimal import Decimal, ROUND_DOWN
from urllib.parse import urlencode

import httpx

MODE = os.getenv("MODE", "paper").lower()  # paper | testnet | live
BASE = os.getenv("BINANCE_BASE") or ("https://testnet.binance.vision" if MODE == "testnet" else "https://api.binance.com")
KEY = os.getenv("BINANCE_API_KEY", "")
SECRET = os.getenv("BINANCE_API_SECRET", "")
QUOTE = "USDT"
CAPITAL = Decimal(os.getenv("LIVE_CAPITAL", "50"))      # money the bot is allowed to size from
MAX_TRADE = Decimal(os.getenv("LIVE_MAX_USDT", "20"))   # hard cap per single trade
STOP_SLIP = Decimal("0.002")                            # stop-limit sits 0.2% under the stop price
CRYPTO = {"BTC", "ETH", "SOL", "DOGE", "XRP"}


class BinanceError(Exception):
    pass


def _req(method, path, params=None, signed=False):
    p = dict(params or {})
    headers = {"X-MBX-APIKEY": KEY}
    if signed:
        p["timestamp"] = int(time.time() * 1000)
        p["recvWindow"] = 10000
        q = urlencode(p)
        q += "&signature=" + hmac.new(SECRET.encode(), q.encode(), hashlib.sha256).hexdigest()
        r = httpx.request(method, f"{BASE}{path}?{q}", headers=headers, timeout=20)
    else:
        r = httpx.request(method, f"{BASE}{path}", params=p, headers=headers, timeout=20)
    if r.status_code != 200:
        raise BinanceError(f"HTTP {r.status_code}: {r.text[:300]}")
    return r.json()


def fmt(d):
    return format(d, "f")


def floor(x, step):
    return (Decimal(str(x)) / step).to_integral_value(ROUND_DOWN) * step


_info = {}


def sym_info(pair):
    if pair not in _info:
        j = _req("GET", "/api/v3/exchangeInfo", {"symbol": pair})["symbols"][0]
        f = {x["filterType"]: x for x in j["filters"]}
        mn = f.get("NOTIONAL") or f.get("MIN_NOTIONAL") or {}
        _info[pair] = {"base": j["baseAsset"], "tick": Decimal(f["PRICE_FILTER"]["tickSize"]),
                       "step": Decimal(f["LOT_SIZE"]["stepSize"]), "min_qty": Decimal(f["LOT_SIZE"]["minQty"]),
                       "min_notional": Decimal(mn.get("minNotional", "5"))}
    return _info[pair]


def free_quote():
    for b in _req("GET", "/api/v3/account", signed=True)["balances"]:
        if b["asset"] == QUOTE:
            return Decimal(b["free"])
    return Decimal(0)


def _fees(fills, asset):
    return sum((Decimal(f["commission"]) for f in fills if f["commissionAsset"] == asset), Decimal(0))


def market_sell(pair, qty):
    return _req("POST", "/api/v3/order", {"symbol": pair, "side": "SELL", "type": "MARKET", "quantity": fmt(qty),
                                           "newOrderRespType": "FULL"}, signed=True)


def open_trade(sig, sym, risk_budget_usd):
    """Buy + place OCO. Returns fields that override the paper trade record. Raises BinanceError on any problem
    (and dumps the position if it was bought but could not be protected)."""
    if sym not in CRYPTO:
        raise BinanceError(f"{sym} is not a crypto Spot symbol")
    if sig["side"] != "BUY":
        raise BinanceError("Spot is long-only; SELL signals are skipped")
    pair = sym + QUOTE
    inf = sym_info(pair)
    entry, sl, tp = Decimal(str(sig["entry"])), Decimal(str(sig["sl"])), Decimal(str(sig["tp"]))
    notional = min(Decimal(str(risk_budget_usd)) * entry / (entry - sl), CAPITAL * Decimal("0.5"), MAX_TRADE)
    notional = notional.quantize(Decimal("0.01"), ROUND_DOWN)
    if notional < inf["min_notional"] * Decimal("1.2"):
        raise BinanceError(f"size {notional} USDT below Binance minimum {inf['min_notional']}")
    if free_quote() < notional:
        raise BinanceError(f"not enough free {QUOTE} (need {notional})")

    o = _req("POST", "/api/v3/order", {"symbol": pair, "side": "BUY", "type": "MARKET", "quoteOrderQty": fmt(notional),
                                       "newOrderRespType": "FULL"}, signed=True)
    got, spent = Decimal(o["executedQty"]), Decimal(o["cummulativeQuoteQty"])
    if got <= 0:
        raise BinanceError("buy did not fill")
    qty = floor(got - _fees(o["fills"], inf["base"]), inf["step"])  # fee is taken from the coin, so sell a bit less
    fill = spent / got
    sl_p, tp_p = floor(sl, inf["tick"]), floor(tp, inf["tick"])
    lim = floor(sl * (1 - STOP_SLIP), inf["tick"])
    try:
        if qty < inf["min_qty"] or not (sl_p < fill < tp_p):
            raise BinanceError(f"fill {fill:.6g} outside SL/TP range or qty too small")
        oco = _req("POST", "/api/v3/orderList/oco", {
            "symbol": pair, "side": "SELL", "quantity": fmt(qty),
            "aboveType": "LIMIT_MAKER", "abovePrice": fmt(tp_p),
            "belowType": "STOP_LOSS_LIMIT", "belowStopPrice": fmt(sl_p), "belowPrice": fmt(lim),
            "belowTimeInForce": "GTC"}, signed=True)
    except Exception as e:
        try:
            market_sell(pair, qty)
        except Exception as e2:
            raise BinanceError(f"UNPROTECTED POSITION in {pair}, sell manually! {e} / {e2}")
        raise BinanceError(f"could not protect trade, position sold again: {e}")
    return {"live": True, "pair": pair, "list_id": oco["orderListId"], "qty": fmt(qty), "entry": float(fill),
            "sl": float(sl_p), "tp": float(tp_p), "cost_usd": float(spent), "notional": float(spent),
            "risk_usd": round(float(qty * (fill - sl_p)), 4), "rr": round(float((tp_p - fill) / (fill - sl_p)), 2)}


def check(tr, timed_out=False):
    """None while the OCO is still working, else (status, R). Cancels and sells at market on timeout."""
    pair = tr["pair"]
    lst = _req("GET", "/api/v3/orderList", {"orderListId": tr["list_id"]}, signed=True)
    cost = Decimal(str(tr["cost_usd"]))
    if lst["listOrderStatus"] == "EXECUTING":
        if not timed_out:
            return None
        _req("DELETE", "/api/v3/orderList", {"symbol": pair, "orderListId": tr["list_id"]}, signed=True)
        o = market_sell(pair, Decimal(tr["qty"]))
        got = Decimal(o["cummulativeQuoteQty"]) - _fees(o["fills"], QUOTE)
        return "timeout", float((got - cost) / Decimal(str(tr["risk_usd"])))
    for leg in lst["orders"]:
        o = _req("GET", "/api/v3/order", {"symbol": pair, "orderId": leg["orderId"]}, signed=True)
        if o["status"] == "FILLED":
            tl = _req("GET", "/api/v3/myTrades", {"symbol": pair, "orderId": leg["orderId"]}, signed=True)
            fees = _fees(tl, QUOTE)
            got = Decimal(o["cummulativeQuoteQty"]) - fees
            return ("win" if o["type"] == "LIMIT_MAKER" else "loss"), float((got - cost) / Decimal(str(tr["risk_usd"])))
    return "error", 0.0  # OCO ended with no fill (cancelled by hand?). Check your Binance app: coins may still be held.
