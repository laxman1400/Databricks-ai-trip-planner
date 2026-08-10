from collections import defaultdict
from datetime import date
import requests

from config import (
    OPEN_METEO_GEOCODING_URL,
    OPEN_METEO_FORECAST_URL,
    OPEN_METEO_AIR_QUALITY_URL,
)


class OpenMeteoClient:
    def __init__(self, timeout=20):
        self.timeout = timeout

    def geocode(self, place_name):
        response = requests.get(
            OPEN_METEO_GEOCODING_URL,
            params={
                "name": place_name,
                "count": 5,
                "language": "en",
                "format": "json",
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        results = response.json().get("results", [])
        if not results:
            raise ValueError(f"No location found for '{place_name}'.")

        hit = results[0]
        return {
            "name": hit["name"],
            "country": hit.get("country"),
            "latitude": hit["latitude"],
            "longitude": hit["longitude"],
            "timezone": hit.get("timezone", "auto"),
            "admin1": hit.get("admin1"),
        }

    def forecast(self, latitude, longitude, timezone="auto", forecast_days=16):
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "timezone": timezone or "auto",
            "forecast_days": forecast_days,
            "hourly": ",".join(
                [
                    "temperature_2m",
                    "precipitation_probability",
                    "weather_code",
                    "wind_speed_10m",
                    "uv_index",
                ]
            ),
            "daily": ",".join(
                [
                    "weather_code",
                    "temperature_2m_max",
                    "temperature_2m_min",
                    "precipitation_probability_max",
                    "wind_speed_10m_max",
                    "uv_index_max",
                ]
            ),
        }
        response = requests.get(
            OPEN_METEO_FORECAST_URL, params=params, timeout=self.timeout
        )
        response.raise_for_status()
        return response.json()

    def air_quality(self, latitude, longitude, timezone="auto", forecast_days=7):
        response = requests.get(
            OPEN_METEO_AIR_QUALITY_URL,
            params={
                "latitude": latitude,
                "longitude": longitude,
                "timezone": timezone or "auto",
                "forecast_days": forecast_days,
                "hourly": "us_aqi,pm2_5,pm10,alder_pollen,birch_pollen,grass_pollen",
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def daily_summary(self, latitude, longitude, target_date, timezone="auto"):
        if isinstance(target_date, date):
            target_date = target_date.isoformat()

        weather = self.forecast(latitude, longitude, timezone=timezone)
        daily = weather.get("daily", {})
        dates = daily.get("time", [])
        if target_date not in dates:
            return {
                "date": target_date,
                "available": False,
                "message": "Requested date is outside the available forecast window.",
            }

        i = dates.index(target_date)
        summary = {
            "date": target_date,
            "available": True,
            "weather_code": daily.get("weather_code", [None] * len(dates))[i],
            "min_temp_c": daily.get("temperature_2m_min", [None] * len(dates))[i],
            "max_temp_c": daily.get("temperature_2m_max", [None] * len(dates))[i],
            "precipitation_probability": daily.get(
                "precipitation_probability_max", [None] * len(dates)
            )[i],
            "wind_speed_kmh": daily.get("wind_speed_10m_max", [None] * len(dates))[i],
            "uv_index": daily.get("uv_index_max", [None] * len(dates))[i],
        }

        try:
            aq = self.air_quality(
                latitude, longitude, timezone=timezone, forecast_days=7
            )
            aq_hourly = aq.get("hourly", {})
            aq_values = [
                v
                for t, v in zip(
                    aq_hourly.get("time", []), aq_hourly.get("us_aqi", [])
                )
                if t.startswith(target_date) and v is not None
            ]
            summary["aqi"] = max(aq_values) if aq_values else None
        except Exception:
            summary["aqi"] = None

        return summary
