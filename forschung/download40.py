"""15m-Klines USDT-M-Futures von data.binance.vision (Monatspakete) -> Parquet je Coin."""
import io, os, sys, time, zipfile, urllib.request
import pandas as pd
from concurrent.futures import ThreadPoolExecutor
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "kerzen40", "ohlcv_15m")
os.makedirs(OUT, exist_ok=True)
COINS = ["BTC", "ETH", "SOL", "XRP", "BNB", "DOGE", "ADA", "AVAX", "LINK", "DOT", "LTC", "TRX", "BCH", "NEAR",
         "ATOM", "UNI", "FIL", "ETC", "APT", "ARB", "OP", "SUI", "INJ", "AAVE", "TIA", "SEI", "WLD", "1000PEPE",
         "1000SHIB", "XLM", "HBAR", "ICP", "RUNE", "STX", "IMX", "GALA", "SAND", "MANA", "AXS", "CRV", "LDO", "ENA"]
months = pd.period_range("2021-01", "2026-10", freq="M")
for c in COINS:
    sym = f"{c}USDT"; path = os.path.join(OUT, f"{sym}.parquet")
    if os.path.exists(path):
        continue
    t0 = time.time()
    def get(m):
        url = f"https://data.binance.vision/data/futures/um/monthly/klines/{sym}/15m/{sym}-15m-{m.year}-{m.month:02d}.zip"
        for attempt in range(4):
            try:
                with urllib.request.urlopen(url, timeout=30) as r:
                    z = zipfile.ZipFile(io.BytesIO(r.read()))
                df = pd.read_csv(z.open(z.namelist()[0]), header=None)
                if not str(df.iloc[0, 0]).isdigit():
                    df = df.iloc[1:]
                return df.iloc[:, :6].astype(float)
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    return None
                time.sleep(2)
            except Exception:
                time.sleep(2)
        return "FEHLER"
    with ThreadPoolExecutor(8) as pool:
        got = list(pool.map(get, months))
    if any(isinstance(g, str) for g in got):
        print(f"{sym}: Abruffehler bei {sum(isinstance(g, str) for g in got)} Monaten", flush=True)
    parts = [g for g in got if g is not None and not isinstance(g, str)]
    if not parts:
        print(f"{sym}: keine Daten", flush=True); continue
    df = pd.concat(parts); df.columns = ["open_time", "open", "high", "low", "close", "volume"]
    df["open_time"] = df.open_time.astype("int64")
    df.loc[df.open_time > 10**14, "open_time"] //= 1000          # Mikrosekunden ab 2025 -> ms
    df = df.drop_duplicates("open_time").sort_values("open_time").reset_index(drop=True)
    df.to_parquet(path)
    print(f"{sym}: {len(df)} Kerzen ab {pd.to_datetime(df.open_time.iloc[0], unit='ms').date()} ({time.time()-t0:.0f}s)", flush=True)
print("ALLDONE", flush=True)
