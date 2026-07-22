"""EIA Open Data API — the secondary crude price source.

Series used (EIA v2, petroleum/pri/spt):
  RBRTE  Europe Brent spot FOB, $/bbl, daily
  RWTC   Cushing WTI spot FOB, $/bbl, daily

This is official U.S. government data — reliable, but needs a free
registered key (EIA_API_KEY), which is why it sits second in the chain
behind the keyless Yahoo Finance source in prices.py, not first. It also
reports the physical *spot* price rather than the futures price most tickers
show — a real, legitimate methodological difference from Yahoo's numbers,
not a bug in either source.
"""

from __future__ import annotations

from ..config import SETTINGS, sourced  # noqa: F401  (sourced kept for symmetry/future use)
import httpx

EIA_LABEL = "EIA Open Data — Petroleum Spot Prices (RBRTE / RWTC)"
EIA_HOME = "https://www.eia.gov/opendata/browser/petroleum/pri/spt"

STATUS: dict[str, dict] = {
    "RBRTE": {"ok": None, "detail": "not attempted yet"},
    "RWTC": {"ok": None, "detail": "not attempted yet"},
}


async def fetch_eia_series(series_id: str) -> list[tuple[str, float]] | None:
    if not SETTINGS.eia_key:
        STATUS[series_id] = {"ok": False, "detail": "no EIA_API_KEY configured"}
        return None
    params = {
        "api_key": SETTINGS.eia_key,
        "frequency": "daily",
        "data[0]": "value",
        "facets[series][]": series_id,
        "sort[0][column]": "period",
        "sort[0][direction]": "desc",
        "length": 60,
    }
    try:
        async with httpx.AsyncClient(timeout=SETTINGS.http_timeout) as client:
            r = await client.get(SETTINGS.eia_url, params=params)
            if r.status_code != 200:
                # Capture EIA's own error body — it usually says exactly what's
                # wrong (bad key, bad facet, rate limit) rather than leaving us
                # to guess from a generic exception.
                try:
                    detail = r.json()
                except Exception:
                    detail = r.text[:200]
                STATUS[series_id] = {"ok": False, "detail": f"HTTP {r.status_code}: {detail}"}
                return None
            body = r.json()
            if "response" not in body or "data" not in body.get("response", {}):
                STATUS[series_id] = {"ok": False,
                                     "detail": f"unexpected response shape: {str(body)[:200]}"}
                return None
            rows = body["response"]["data"]
        out = [(row["period"], float(row["value"])) for row in rows if row.get("value") is not None]
        out.sort(key=lambda x: x[0])
        if not out:
            STATUS[series_id] = {"ok": False, "detail": "request succeeded but returned zero rows"}
            return None
        STATUS[series_id] = {"ok": True, "detail": f"{len(out)} rows, latest {out[-1][0]}"}
        return out
    except httpx.TimeoutException:
        STATUS[series_id] = {"ok": False, "detail": f"timed out after {SETTINGS.http_timeout}s"}
        return None
    except Exception as exc:
        STATUS[series_id] = {"ok": False, "detail": f"{type(exc).__name__}: {exc}"}
        return None


def eia_status() -> dict:
    return STATUS
