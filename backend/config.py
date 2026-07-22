"""Configuration, provenance envelopes and a tiny TTL cache.

Design rule for this whole backend: **no bare numbers cross the wire**.
Every value the frontend renders arrives wrapped by `sourced()`, carrying the
source label, a URL a human can open, when it was retrieved, and whether it is
live, cached or a documented reference value. The UI can therefore always
answer "where did this come from" without the backend guessing later.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional


# --------------------------------------------------------------------------
# Configuration — keys are optional; the platform degrades, it does not break.
# --------------------------------------------------------------------------

@dataclass
class Settings:
    aisstream_key: Optional[str] = os.getenv("AISSTREAM_API_KEY") or None
    eia_key: Optional[str] = os.getenv("EIA_API_KEY") or None
    opensanctions_key: Optional[str] = os.getenv("OPENSANCTIONS_API_KEY") or None
    anthropic_key: Optional[str] = os.getenv("ANTHROPIC_API_KEY") or None
    vesselapi_key: Optional[str] = os.getenv("VESSELAPI_KEY") or None
    gdelt_cloud_key: Optional[str] = os.getenv("GDELT_CLOUD_API_KEY") or None

    # Endpoints (kept here so a reviewer can see exactly what we call)
    eia_url: str = "https://api.eia.gov/v2/petroleum/pri/spt/data/"
    gdelt_url: str = "https://api.gdeltproject.org/api/v2/doc/doc"
    gdelt_cloud_url: str = "https://gdeltcloud.com"
    open_meteo_marine: str = "https://marine-api.open-meteo.com/v1/marine"
    open_meteo_weather: str = "https://api.open-meteo.com/v1/forecast"
    ofac_sdn_csv: str = "https://www.treasury.gov/ofac/downloads/sdn.csv"
    ofac_sdn_alt: str = "https://sanctionslist.ofac.treas.gov/Home/SdnList"
    opensanctions_url: str = "https://api.opensanctions.org/search/default"
    vesselapi_url: str = "https://api.vesselapi.com/v1"
    portwatch_ports: str = (
        "https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services/"
        "Daily_Ports_Data/FeatureServer/0/query"
    )
    portwatch_chokepoints: str = (
        "https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services/"
        "Daily_Chokepoints_Data/FeatureServer/0/query"
    )
    aisstream_ws: str = "wss://stream.aisstream.io/v0/stream"

    http_timeout: float = 12.0
    refresh_seconds: int = 180


SETTINGS = Settings()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --------------------------------------------------------------------------
# Provenance envelope
# --------------------------------------------------------------------------

LIVE = "live"            # fetched from the upstream API in this cycle
CACHED = "cached"        # fetched earlier, served from cache
REFERENCE = "reference"  # documented constant from reference.py
MODELLED = "modelled"    # computed by SUPATH's own engine from sourced inputs
UNAVAILABLE = "unavailable"


def sourced(value: Any, *, source: str, url: str = "", mode: str = LIVE,
            as_of: Optional[str] = None, method: str = "") -> Dict[str, Any]:
    """Wrap a value with the evidence needed to defend it."""
    return {
        "value": value,
        "source": source,
        "url": url,
        "mode": mode,
        "as_of": as_of or now_iso(),
        "method": method,
    }


def unwrap(x: Any, default: Any = None) -> Any:
    if isinstance(x, dict) and "value" in x and "source" in x:
        return x["value"]
    return x if x is not None else default


# --------------------------------------------------------------------------
# TTL cache
# --------------------------------------------------------------------------

class TTLCache:
    def __init__(self):
        self._store: Dict[str, tuple[float, Any]] = {}

    def get(self, key: str, ttl: float) -> Optional[Any]:
        hit = self._store.get(key)
        if not hit:
            return None
        ts, val = hit
        if time.time() - ts > ttl:
            return None
        return val

    def stale(self, key: str) -> Optional[Any]:
        """Last known value regardless of age — used when upstream is down."""
        hit = self._store.get(key)
        return hit[1] if hit else None

    def set(self, key: str, value: Any) -> None:
        self._store[key] = (time.time(), value)

    def age(self, key: str) -> Optional[float]:
        hit = self._store.get(key)
        return time.time() - hit[0] if hit else None


CACHE = TTLCache()
