# datafeed-bridge

A tiny GitHub-Actions proxy for **free data sources that are network-blocked from our
host** (but reachable from GitHub's runners). The Action polls the source, publishes a
clean JSON snapshot as both a downloadable artifact and a commit on the `data` branch,
and the host's `marketdata` client fetches it raw (auth-free — the data is public).

## Why this exists
`gamma-api.polymarket.com` returns HTTP 000 from our host (network-blocked), yet works
fine inside GitHub Actions. Rather than lose the signal, we fetch it here and analyze
locally. Prediction-market odds (Fed decisions, elections, conflict, macro) are useful
input to the markets/macro/geo digest and the swing trader.

## Layout
- `poll_polymarket.py` — fetches gamma-api, volume-ranks + distils to compact odds JSON.
- `.github/workflows/poll.yml` — schedule (every 2h) + `workflow_dispatch`; uploads the
  `datafeed` artifact and force-pushes `polymarket.json` to the `data` branch.

## Consume from the host
Raw (auth-free): `https://raw.githubusercontent.com/istefanov87-svg/datafeed-bridge/data/polymarket.json`
— see `marketdata.polymarket` (the shared data package).

Public repo on purpose: the payload is public market-odds data, and a public raw URL
lets the host fetch it with zero auth (reliable from cron). No secrets live here.
