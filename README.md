# FundingRadar — Hyperliquid funding rate scanner CLI (funding, premium, open interest)

# FundingRadar

Hyperliquid funding-rate scanner. One command, no API key, no wallet.

- Ranks every active perp by hourly funding, shows annualized % and premium
- Filters by open interest so you never chase illiquid tickers
- JSON snapshot + threshold alert exit codes for cron/CI pipelines

## Install

Requires Python 3.10+ (stdlib only).

    python3 src/fundingradar.py --top 15

## Usage

    # top 15 by |funding|
    python3 src/fundingradar.py --top 15

    # only coins with > $5M open interest, save snapshot
    python3 src/fundingradar.py --min-oi 5000000 --json-out snap.json

    # cron-friendly alert: exit code 3 when anything is >= 20% annualized
    python3 src/fundingradar.py --alert 20

## Sample output

    coin       1h %       ann %      prem          OI $
    BTC        0.0089     78.04   0.000512    1,234,567,890
    ETH        0.0060     52.55   0.000480      456,789,012

`ann %` = hourly rate x 24 x 365, the naive number. Real net carry is lower
after execution costs, premium mean-reversion, and rate decay.

## Data source

`api.hyperliquid.xyz/info` (metaAndAssetCtxs). Read-only, rate-limited to
~1200 req/min. Poll every 60s or more.

## Disclaimer

Rates are raw market data. This tool does not trade, and nothing here is
financial advice.


More tools: https://economic-agent.github.io/
