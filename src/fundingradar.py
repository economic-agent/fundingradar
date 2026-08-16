"""FundingRadar - Hyperliquid funding-rate scanner.

Fetches all perp funding rates, ranks by absolute rate, prints top movers
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


def _post(payload: dict) -> dict:
    req = urllib.request.Request(
        HL_INFO,
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) fundingradar/1.0",
        },
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode())


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
                "coin": m["name"],
                "funding_hourly": funding,
                "funding_annualized_pct": round(funding * 24 * 365 * 100, 2),
                "premium": round(premium, 6),
                "open_interest": round(oi, 2),
                "mark": float(c.get("markPx") or 0),
            }
        )
    rows.sort(key=lambda r: -abs(r["funding_hourly"]))
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description="Hyperliquid funding scanner")
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--min-oi", type=float, default=100_000.0)
    ap.add_argument("--coins", default=None,
                    help="comma-separated list, e.g. ETH,BTC,SOL (empty = all)")
    ap.add_argument("--json-out", default=None, help="write snapshot JSON")
    ap.add_argument("--csv-out", default=None,
                    help="append rows to CSV (coin, hourly pct, ann pct, premium, oi, mark)")
    ap.add_argument("--alert", type=float, default=None,
                    help="exit code 3 if any |annualized| >= this threshold (pct)")
    args = ap.parse_args()

    meta, ctxs = _post({"type": "metaAndAssetCtxs"})
    coins = {c.strip().upper() for c in args.coins.split(",")} if args.coins else None
    rows = funding_snapshot(meta, ctxs, args.min_oi, coins)

    print(f"{'coin':<10} {'1h %':>8} {'ann %':>9} {'prem':>8} {'OI $':>14}")
    for r in rows[: args.top]:
        print(
            f"{r['coin']:<10} {r['funding_hourly']*100:>8.4f} "
            f"{r['funding_annualized_pct']:>9.2f} {r['premium']:>8.4f} "
            f"{r['open_interest']:>14,.0f}"
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
                w.writerow(["ts", "coin", "funding_hourly_pct", "ann_pct",
                            "premium", "open_interest", "mark"])
            for r in rows:
                w.writerow([snap["ts"], r["coin"],
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
