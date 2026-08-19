# FundingRadar

Multi-exchange funding-rate scanner. One command, no API key, no wallet.

- Ranks every active perp by hourly funding, shows annualized % and premium
- Venues: Hyperliquid, Binance USDT-M, Bybit USDT perps — or all merged
- Filters by open interest so you never chase illiquid tickers
- JSON snapshot + threshold alert exit codes for cron/CI pipelines

## Install

Requires Python 3.10+ (stdlib only).

    python3 src/fundingradar.py --top 15

## Usage

    # top 15 on Hyperliquid (default)
    python3 src/fundingradar.py --top 15

    # all three venues merged, ranked by |hourly funding|
    python3 src/fundingradar.py --exchange all --top 15 --min-oi 5000000

    # Binance USDT-M only
    python3 src/fundingradar.py --exchange binance --top 10

    # Bybit linear only
    python3 src/fundingradar.py --exchange bybit --top 10

    # only coins with > $5M open interest, save snapshot
    python3 src/fundingradar.py --min-oi 5000000 --json-out snap.json

    # cron-friendly alert: exit code 3 when anything is >= 20% annualized
    python3 src/fundingradar.py --alert 20

## Sample output (merged)

    EX   coin           1h %     ann %     prem           OI $
    HL   ACE         -0.0696   -609.62  -0.0065     10,635,263
    BYBIT HOME        -0.0500   -437.67   0.0000      6,602,046
    BYBIT BTW          0.0472    413.44   0.0000     21,808,197
    HL   XAI         -0.0291   -255.28  -0.0041     46,956,605

`ann %` = per-period rate x (24 / interval hours) x 365, the naive number.
Real net carry is lower after execution costs, premium mean-reversion, and
rate decay. Binance funding is 8h; Bybit interval is read from
instruments-info; Hyperliquid is hourly.

## Data sources

- Hyperliquid: `api.hyperliquid.xyz/info` (metaAndAssetCtxs)
- Binance: `fapi.binance.com/fapi/v1/premiumIndex` (public)
- Bybit: `api.bybit.com/v5/market/tickers` + `instruments-info` (public)

All read-only public endpoints. No API keys. Poll every 60s or more to
stay within rate limits.

Paid services from the same author (encrypted DM delivery):
https://store.economicagent.net/ — daily digest, real-time spike alerts,
weekly Solana narrative report. Machine-payable for AI agents (x402,
USDC on Solana, $0.001-0.002/call): GET https://api.economicagent.net:8080/funding/top
