#!/usr/bin/env python3
"""Poll the Polymarket public API and emit a clean odds snapshot.

Runs inside GitHub Actions (GitHub's network can reach gamma-api.polymarket.com, which
is blocked from our host). Fetches active markets, sorts by volume, and distils each
EVENT into a compact record: title, the (outcome, probability) pairs across its markets,
total volume, liquidity, resolution date, and category tags. The result JSON is
published to the `data` branch for the host's `marketdata.polymarket` to fetch raw.

Unlike a naive `limit=10` pull, this paginates and volume-ranks so the snapshot is the
LIQUID, decision-relevant markets — not stale low-volume noise.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

import requests

EVENTS_API = "https://gamma-api.polymarket.com/events"
UA = {"User-Agent": "datafeed-bridge/1.0"}


def _parse(field, default):
    if isinstance(field, list):
        return field
    if isinstance(field, str):
        try:
            v = json.loads(field)
            return v if isinstance(v, list) else default
        except Exception:  # noqa: BLE001
            return default
    return default


def _num(x, d=0.0):
    try:
        return float(x)
    except (TypeError, ValueError):
        return d


def fetch_events(pages: int = 6, per: int = 100) -> list[dict]:
    events, seen = [], set()
    for p in range(pages):
        try:
            r = requests.get(EVENTS_API, params={"limit": per, "offset": p * per,
                             "active": "true", "closed": "false", "order": "volume24hr",
                             "ascending": "false"}, headers=UA, timeout=25)
            if not r.ok:
                break
            batch = r.json()
            if not batch:
                break
            for e in batch:
                slug = e.get("slug") or e.get("id")
                if slug and slug not in seen:
                    seen.add(slug)
                    events.append(e)
            if len(batch) < per:
                break
        except Exception as ex:  # noqa: BLE001
            print(f"fetch page {p} failed: {type(ex).__name__}: {ex}")
            break
    return events


def distil(event: dict) -> dict | None:
    markets = event.get("markets") or []
    outcomes = []
    for m in markets:
        oc = _parse(m.get("outcomes", "[]"), [])
        pr = _parse(m.get("outcomePrices", "[]"), [])
        if not oc or len(oc) != len(pr):
            continue
        lower = [str(o).lower() for o in oc]
        if len(oc) == 2 and set(lower) == {"yes", "no"}:
            yes_i = lower.index("yes")
            label = m.get("groupItemTitle") or m.get("question") or event.get("title", "")
            outcomes.append({"name": label, "prob": round(_num(pr[yes_i]), 4)})
        else:
            for o, p in zip(oc, pr):
                outcomes.append({"name": str(o), "prob": round(_num(p), 4)})
    if not outcomes:
        return None
    outcomes = sorted(outcomes, key=lambda x: x["prob"], reverse=True)[:8]
    tags = event.get("tags") or []
    cats = [t.get("label") for t in tags if isinstance(t, dict) and t.get("label")]
    return {
        "title": event.get("title", ""),
        "slug": event.get("slug", ""),
        "url": f"https://polymarket.com/event/{event.get('slug','')}",
        "volume": round(_num(event.get("volume")), 0),
        "liquidity": round(_num(event.get("liquidity")), 0),
        "end_date": event.get("endDate") or event.get("end_date_iso") or "",
        "categories": cats,
        "outcomes": outcomes,
    }


def build(min_volume: float, limit: int) -> dict:
    events = fetch_events()
    records = [d for d in (distil(e) for e in events) if d]
    records = [r for r in records if r["volume"] >= min_volume]
    records.sort(key=lambda r: r["volume"], reverse=True)
    records = records[:limit]
    return {"source": "polymarket", "generated": datetime.now(timezone.utc).isoformat(),
            "count": len(records), "min_volume": min_volume, "markets": records}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="polymarket.json")
    ap.add_argument("--min-volume", type=float, default=25000.0)
    ap.add_argument("--limit", type=int, default=90)
    a = ap.parse_args()
    snap = build(a.min_volume, a.limit)
    with open(a.out, "w") as f:
        json.dump(snap, f, indent=2)
    print(f"wrote {snap['count']} markets -> {a.out} (from {a.limit} cap, min_vol {a.min_volume})")
    for r in snap["markets"][:5]:
        lead = r["outcomes"][0] if r["outcomes"] else {}
        print(f"  ${r['volume']:>12,.0f}  {r['title'][:55]:55}  {lead.get('name','')[:20]} {lead.get('prob','')}")


if __name__ == "__main__":
    main()
