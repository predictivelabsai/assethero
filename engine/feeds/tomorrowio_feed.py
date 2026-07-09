"""Tomorrow.io weather feed — secondary forecast cross-check for prediction markets.

Synchronous port of the polytrade WeatherClient (daily + hourly high/low). Used to
double-check the Visual Crossing primary during forward predictions. `requests` is
imported lazily so the module imports with no third-party deps installed. The API
key comes from the integrations layer (provider ``tomorrowio``, field ``api_key``)
with the ``TOMORROWIO_API_KEY`` env var as fallback.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

BASE_URL = "https://api.tomorrow.io/v4/weather/forecast"

CITY_COORDS = {
    "London": (51.5074, -0.1278),
    "New York": (40.7128, -74.0060),
    "Seoul": (37.5665, 126.9780),
    "Tokyo": (35.6762, 139.6503),
    "Paris": (48.8566, 2.3522),
    "Singapore": (1.3521, 103.8198),
    "Hong Kong": (22.3193, 114.1694),
    "Dubai": (25.2048, 55.2708),
}


class TomorrowIoFeed:
    """Forecast highs/lows for a city/day via Tomorrow.io."""

    def __init__(self, api_key: Optional[str] = None, user_id: Optional[str] = None):
        self.user_id = user_id
        self._api_key = api_key

    @property
    def api_key(self) -> Optional[str]:
        if self._api_key:
            return self._api_key
        from engine.integrations import resolve
        self._api_key = resolve(self.user_id, "tomorrowio", "api_key")
        return self._api_key

    def _raw_forecast(self, city: str) -> Optional[Dict[str, Any]]:
        if not self.api_key:
            return None
        import requests
        location = city
        coords = CITY_COORDS.get(city.title())
        if coords:
            location = f"{coords[0]},{coords[1]}"
        params = {
            "location": location,
            "apikey": self.api_key,
            "units": "imperial",
            "timelines": "1d,1h",
        }
        try:
            resp = requests.get(BASE_URL, params=params, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:  # noqa: BLE001
            logger.error(f"Tomorrow.io error for {city}: {e}")
            return None

    def get_day_weather(self, city: str, date_str: str) -> Optional[Dict[str, Any]]:
        """Return {tempmax, tempmin, temp, forecast_time} for the given day."""
        data = self._raw_forecast(city)
        if not data:
            return None
        try:
            target = datetime.strptime(date_str, "%Y-%m-%d").date()
            now = datetime.now().strftime("%m-%d %H:%M")

            daily = data.get("timelines", {}).get("daily", [])
            for day in daily:
                t = day.get("time", "")
                if not t:
                    continue
                if datetime.fromisoformat(t.replace("Z", "+00:00")).date() == target:
                    v = day.get("values", {})
                    return {
                        "tempmax": v.get("temperatureMax"),
                        "tempmin": v.get("temperatureMin"),
                        "temp": v.get("temperatureAvg"),
                        "forecast_time": now,
                    }

            hourly = data.get("timelines", {}).get("hourly", [])
            temps = [
                h["values"].get("temperature", 0)
                for h in hourly
                if datetime.fromisoformat(h["time"].replace("Z", "+00:00")).date() == target
            ]
            if temps:
                return {"tempmax": max(temps), "tempmin": min(temps),
                        "temp": sum(temps) / len(temps), "forecast_time": now}
            return None
        except Exception as e:  # noqa: BLE001
            logger.error(f"Tomorrow.io parse error for {city} {date_str}: {e}")
            return None
