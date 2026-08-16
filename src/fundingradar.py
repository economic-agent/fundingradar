"""FundingRadar - multi-exchange funding-rate scanner (Hyperliquid, Binance, Bybit).

Fetches perp funding rates, ranks by absolute rate, prints top movers
and emits a JSON snapshot for alerting. No API key, no wallet needed.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request

HL_INFO = "https://api.hyperliquid.xyz/info"
BINANCE_PREMIUM = "https://fapi.binance.com/fapi/v1/premiumIndex"
BYBIT_TICKERS = "https://api.bybit.com/v5/market/tickers"
BYBIT_INSTRUMENTS = "https://api.bybit.com/v5/market/instruments-info"


def _get(url: str) -> dict | list:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) fundingradar/1.3"},
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode())


def _post(payload: dict) -> dict:
    req = urllib.request.Request(
        HL_INFO,
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) fundingradar/1.3",
        },
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode())


def _annualize(rate_per_period: float, interval_hours: float) -> float:
    return rate_per_period * 24.0 / interval_hours * 365.0 * 100.0


def funding_snapshot(meta: dict, ctxs: list[dict], min_open_interest: float,
                     coins: set[str] | None) -> list[dict]:
    rows = []
    for m, c in zip(meta["universe"], ctxs):
        if m.get("isDelisted"):
            continue
        if coins and m["name"] not in coins:
            continue
        oi = float(c.get("openInterest") or 0)
        if oi < min_open_interest:
            continue
        funding = float(c.get("funding") or 0)
        premium = float(c.get("premium") or 0)
        rows.append(
            {
                "exchange": "HL",
                "coin": m["name"],
                "funding_hourly": funding,
                "funding_annualized_pct": round(_annualize(funding, 1.0), 2),
                "premium": round(premium, 6),
                "open_interest": round(oi, 2),
                "mark": float(c.get("markPx") or 0),
            }
        )
    rows.sort(key=lambda r: -abs(r["funding_hourly"]))
    return rows


def binance_snapshot(min_open_interest: float, coins: set[str] | None) -> list[dict]:
    data = _get(BINANCE_PREMIUM)
    rows = []
    for x in data:
        symbol = x.get("symbol", "")
        if not symbol.endswith("USDT"):
            continue
        coin = symbol[:-4]
        if coins and coin not in coins:
            continue
        oi = float(x.get("openInterest") or 0) * float(x.get("markPrice") or 0)
        if oi < min_open_interest:
            continue
        rate = float(x.get("lastFundingRate") or 0)
        rows.append(
            {
                "exchange": "BIN",
                "coin": coin,
                "funding_hourly": rate / 8.0,
                "funding_annualized_pct": round(_annualize(rate, 8.0), 2),
                "premium": 0.0,
                "open_interest": round(oi, 2),
                "mark": float(x.get("markPrice") or 0),
            }
        )
    rows.sort(key=lambda r: -abs(r["funding_hourly"]))
    return rows


def bybit_snapshot(min_open_interest: float, coins: set[str] | None) -> list[dict]:
    instr = _get(BYBIT_INSTRUMENTS + "?category=linear")
    interval = {}
    for x in instr.get("result", {}).get("list", []):
        try:
            interval[x["symbol"]] = float(x.get("fundingInterval") or 8.0) / 60.0
        except Exception:
            interval[x["symbol"]] = 8.0
    data = _get(BYBIT_TICKERS + "?category=linear")
    rows = []
    for x in data.get("result", {}).get("list", []):
        symbol = x.get("symbol", "")
        coin = symbol[:-4] if symbol.endswith("USDT") else symbol
        if coins and coin not in coins:
            continue
        oi = float(x.get("openInterestValue") or x.get("openInterest") or 0)
        if oi < min_open_interest:
            continue
        rate = float(x.get("fundingRate") or 0)
        iv = interval.get(symbol, 8.0)
        rows.append(
            {
                "exchange": "BYBIT",
                "coin": coin,
                "funding_hourly": rate / iv,
                "funding_annualized_pct": round(_annualize(rate, iv), 2),
                "premium": 0.0,
                "open_interest": round(oi, 2),
                "mark": float(x.get("markPrice") or 0),
            }
        )
    rows.sort(key=lambda r: -abs(r["funding_hourly"]))
    return rows


def funding_history(coin: str, hours: int) -> list[float]:
    """Last `hours` of funding rates for a coin (hourly epochs)."""
    now = int(time.time() * 1000)
    start = now - hours * 3600 * 1000
    d = _post({"type": "fundingHistory", "coin": coin, "startTime": start})
    return [float(x["fundingRate"]) for x in d if x.get("fundingRate") is not None]


def main() -> int:
    ap = argparse.ArgumentParser(description="Multi-exchange funding scanner")
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--min-oi", type=float, default=100_000.0)
    ap.add_argument("--exchange", default="hyperliquid",
                    choices=["hyperliquid", "binance", "bybit", "all"],
                    help="venue to scan (default hyperliquid; 'all' merges)")
    ap.add_argument("--coins", default=None,
                    help="comma-separated list, e.g. ETH,BTC,SOL (empty = all)")
    ap.add_argument("--history", type=int, default=None,
                    help="hours of funding history to summarize (HL only)")
    ap.add_argument("--json-out", default=None, help="write snapshot JSON")
    ap.add_argument("--csv-out", default=None,
                    help="append rows to CSV (exchange, coin, hourly pct, ann pct, premium, oi, mark)")
    ap.add_argument("--alert", type=float, default=None,
                    help="exit code 3 if any |annualized| >= this threshold (pct)")
    args = ap.parse_args()

    coins = {c.strip().upper() for c in args.coins.split(",")} if args.coins else None
    multi = args.exchange == "all"
    if args.exchange in ("hyperliquid", "all"):
        meta, ctxs = _post({"type": "metaAndAssetCtxs"})
        rows = funding_snapshot(meta, ctxs, args.min_oi, coins)
    elif args.exchange == "binance":
        rows = binance_snapshot(args.min_oi, coins)
    elif args.exchange == "bybit":
        rows = bybit_snapshot(args.min_oi, coins)
    else:
        rows = []
    if multi:
        hl_rows = rows
        merged = hl_rows + binance_snapshot(args.min_oi, coins) + bybit_snapshot(args.min_oi, coins)
        merged.sort(key=lambda r: -abs(r["funding_hourly"]))
        rows = merged

    hdr = f"{'EX':<3} {'coin':<10} {'1h %':>8} {'ann %':>9} {'prem':>8} {'OI $':>14}" if multi \
        else f"{'coin':<10} {'1h %':>8} {'ann %':>9} {'prem':>8} {'OI $':>14}"
    print(hdr)
    for r in rows[: args.top]:
        line = (
            f"{r['coin']:<10} {r['funding_hourly']*100:>8.4f} "
            f"{r['funding_annualized_pct']:>9.2f} {r['premium']:>8.4f} "
            f"{r['open_interest']:>14,.0f}"
        )
        if multi:
            line = f"{r['exchange']:<3} " + line
        print(line)
    if args.history and args.exchange in ("hyperliquid", "all"):
        print(f"\nfunding history ({args.history}h): coin, min, avg, max, current (hourly %)")
        for r in rows[: args.top]:
            if r["exchange"] != "HL":
                continue
            try:
                h = funding_history(r["coin"], args.history)
            except Exception:
                continue
            if len(h) < 2:
                continue
            print(
                f"{r['coin']:<10} {min(h)*100:>8.4f} {sum(h)/len(h)*100:>8.4f} "
                f"{max(h)*100:>8.4f} {h[-1]*100:>8.4f}"
            )
    snap = {"ts": int(time.time()), "rows": rows}
    if args.json_out:
        with open(args.json_out, "w") as f:
            json.dump(snap, f, indent=2)
    if args.csv_out:
        import csv as _csv
        new = not os.path.exists(args.csv_out)
        with open(args.csv_out, "a", newline="") as f:
            w = _csv.writer(f)
            if new:
                w.writerow(["ts", "exchange", "coin", "funding_hourly_pct",
                            "ann_pct", "premium", "open_interest", "mark"])
            for r in rows:
                w.writerow([snap["ts"], r["exchange"], r["coin"],
                            round(r["funding_hourly"] * 100, 4),
                            r["funding_annualized_pct"], r["premium"],
                            r["open_interest"], r["mark"]])
    if args.alert is not None:
        if any(abs(r["funding_annualized_pct"]) >= args.alert for r in rows):
            print(f"ALERT: |annualized| >= {args.alert}%", file=sys.stderr)
            return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
