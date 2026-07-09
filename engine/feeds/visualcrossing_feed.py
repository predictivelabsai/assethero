"""Visual Crossing weather feed — primary weather source for the prediction vertical.

Synchronous port of the polytrade VisualCrossingClient. `requests` is imported
lazily inside methods so `import engine.feeds.visualcrossing_feed` never requires
any third-party package. The API key is resolved through the encrypted
integrations layer (provider ``visual_crossing``, field ``api_key``), falling back
to the ``VISUAL_CROSSING_API_KEY`` env var — never read from a hardcoded value.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

BASE_URL = ("https://weather.visualcrossing.com/VisualCrossingWebServices"
            "/rest/services/timeline")


class VisualCrossingFeed:
    """Historical daily weather (highs/lows) via the Timeline API."""

    def __init__(self, api_key: Optional[str] = None, user_id: Optional[str] = None):
        self.user_id = user_id
        self._api_key = api_key

    @property
    def api_key(self) -> Optional[str]:
        if self._api_key:
            return self._api_key
        from engine.integrations import resolve
        self._api_key = resolve(self.user_id, "visual_crossing", "api_key")
        return self._api_key

    def get_historical_weather_range(self, city: str, end_date: str,
                                     days: int = 7) -> Dict[str, Any]:
        """Daily weather for `days` prior to (and including) `end_date`."""
        if not self.api_key:
            logger.warning("Visual Crossing API key not configured")
            return {"days": [], "forecast_time": None, "error": "no_api_key"}

        import requests

        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        start_date = (end_dt - timedelta(days=days)).strftime("%Y-%m-%d")
        url = f"{BASE_URL}/{city}/{start_date}/{end_date}"
        params = {
            "key": self.api_key,
            "unitGroup": "us",
            "include": "days",
            "contentType": "json",
        }
        try:
            resp = requests.get(url, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            return {
                "days": data.get("days", []),
                "forecast_time": datetime.now().strftime("%m-%d %H:%M"),
            }
        except Exception as e:  # noqa: BLE001
            logger.error(f"Visual Crossing error for {city}: {e}")
            return {"days": [], "forecast_time": None, "error": str(e)}

    def get_day_weather(self, city: str, date: str) -> Optional[Dict[str, Any]]:
        """Weather for a single calendar day (tempmax/tempmin/temp)."""
        res = self.get_historical_weather_range(city, date, days=0)
        days = res.get("days", [])
        if not days:
            return None
        day = dict(days[0])
        day["forecast_time"] = res.get("forecast_time")
        return day
