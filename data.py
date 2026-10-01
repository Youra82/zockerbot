# zockerbot/data.py — sammelt den taeglichen Marktbericht (nur abgeschlossene Tage, nur oeffentliche Daten).
import time, datetime
import numpy as np
import pandas as pd
import requests
import ccxt

FAPI = "https://fapi.binance.com"


def daily_candles(ex, coins, limit=220):
    now_ms = time.time() * 1000
    out = {}
    for b in coins:
        rows = ex.fetch_ohlcv(f"{b}/USDT", "1d", limit=limit)
        rows = [r for r in rows if r[0] + 86_400_000 <= now_ms]          # laufender Tag raus
        df = pd.DataFrame(rows, columns="t o h l c v".split())
        df.index = pd.to_datetime(df.t, unit="ms")
        out[b] = df
    return out


def funding_7d(coins):
    start = int((time.time() - 9 * 86400) * 1000); out = {}
    for b in coins:
        r = requests.get(FAPI + "/fapi/v1/fundingRate", params={"symbol": f"{b}USDT", "startTime": start, "limit": 100},
                         timeout=20).json()
        if isinstance(r, list) and r:
            f = pd.Series({x["fundingTime"]: float(x["fundingRate"]) for x in r})
            f.index = pd.to_datetime(f.index, unit="ms").floor("D")
            out[b] = f.groupby(level=0).sum()
    return pd.DataFrame(out).sort_index()


def stablecoin_growth_30d():
    try:
        r = requests.get("https://stablecoins.llama.fi/stablecoincharts/all", timeout=30).json()
        s = pd.Series({int(x["date"]): x["totalCirculatingUSD"].get("peggedUSD", 0) for x in r}).sort_index()
        return float(s.iloc[-1] / s.iloc[-31] - 1), float(s.iloc[-1] / 1e9)
    except Exception:
        return None, None


def binance_announcements(hours=48):
    try:
        r = requests.get("https://www.binance.com/bapi/composite/v1/public/cms/article/list/query",
                         params={"type": 1, "catalogId": 48, "pageNo": 1, "pageSize": 20},
                         headers={"User-Agent": "Mozilla/5.0"}, timeout=15).json()
        arts = r["data"]["catalogs"][0]["articles"]
        cut = (time.time() - hours * 3600) * 1000
        return [a["title"] for a in arts if a["releaseDate"] >= cut]
    except Exception:
        return []


def rsi(c, n=14):
    d = c.diff(); up = d.clip(lower=0).ewm(alpha=1 / n, min_periods=n).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, min_periods=n).mean()
    return float((100 - 100 / (1 + up / dn)).iloc[-1])


def coin_features(df):
    c = df.c
    def ret(n): return round(float(c.iloc[-1] / c.iloc[-1 - n] - 1) * 100, 2)
    def dist(n): return round(float(c.iloc[-1] / c.iloc[-n:].mean() - 1) * 100, 2)
    vol = float(c.pct_change().iloc[-30:].std() * np.sqrt(365) * 100)
    atr = float(((df.h - df.l) / df.c).iloc[-14:].mean() * 100)
    return {"preis": round(float(c.iloc[-1]), 6), "ret_1d_%": ret(1), "ret_7d_%": ret(7), "ret_30d_%": ret(30),
            "ret_90d_%": ret(90), "abstand_sma20_%": dist(20), "abstand_sma50_%": dist(50),
            "abstand_sma100_%": dist(100), "rsi14": round(rsi(c), 1), "vol30_ann_%": round(vol, 1),
            "tagesspanne14_%": round(atr, 2)}


def build_report(ex, coins):
    C = daily_candles(ex, coins)
    day = min(df.index[-1] for df in C.values())
    feats = {b: coin_features(df.loc[:day]) for b, df in C.items()}
    F = funding_7d(coins)
    for b in coins:
        if b in F:
            feats[b]["funding_7d_avg_pro_tag_%"] = round(float(F[b].iloc[-7:].mean()) * 100, 4)
    btc = C["BTC"].c.loc[:day]
    sg, scap = stablecoin_growth_30d()
    market = {"datum": str(day.date()), "btc_ueber_sma100": bool(btc.iloc[-1] > btc.iloc[-100:].mean()),
              "btc_ueber_sma200": bool(btc.iloc[-1] > btc.iloc[-200:].mean()),
              "stablecoin_wachstum_30d_%": None if sg is None else round(sg * 100, 2),
              "stablecoin_gesamt_mrd_usd": None if scap is None else round(scap, 1),
              "binance_ankuendigungen_48h": binance_announcements()}
    ohlc = {b: tuple(float(x) for x in df.loc[day, ["o", "h", "l", "c"]]) for b, df in C.items() if day in df.index}
    fund_today = {b: float(F[b].loc[day]) for b in coins if b in F and day in F[b].index}
    return day, market, feats, ohlc, fund_today, C
