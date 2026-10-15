"""
Daily weather from Open-Meteo (free, no API key): https://open-meteo.com

Each run asks for the last 2 days plus today. Past days are observed values;
today is a forecast. Because rows are upserted on (city, date), tomorrow's run
overwrites today's forecast with the observed value, so history ends up accurate.
"""
from datetime import date

from collector.db import now_utc, upsert
from collector.sources.base import Source

URL = "https://api.open-meteo.com/v1/forecast"
DAILY = "temperature_2m_max,temperature_2m_min,precipitation_sum,wind_speed_10m_max,weather_code"


class Weather(Source):
    name = "weather"

    def extract(self):
        raw = []
        for city in self.settings.cities:
            resp = self.session.get(
                URL,
                params={
                    "latitude": city.latitude,
                    "longitude": city.longitude,
                    "daily": DAILY,
                    "past_days": 2,
                    "forecast_days": 1,
                    "timezone": "auto",
                },
                timeout=self.settings.request_timeout,
            )
            resp.raise_for_status()
            raw.append({"city": city.name, "data": resp.json()})
        return raw

    def transform(self, raw):
        updated = now_utc()
        rows = []
        for item in raw:
            d = item["data"]["daily"]
            # "today" in the city's own time zone (Open-Meteo returns dates in local time)
            today = d["time"][-1] if d["time"] else date.today().isoformat()
            for i, day in enumerate(d["time"]):
                rows.append({
                    "city": item["city"],
                    "date": day,
                    "temp_max_c": d["temperature_2m_max"][i],
                    "temp_min_c": d["temperature_2m_min"][i],
                    "precipitation_mm": d["precipitation_sum"][i],
                    "wind_max_kmh": d["wind_speed_10m_max"][i],
                    "weather_code": d["weather_code"][i],
                    "is_forecast": int(day >= today),
                    "updated_at": updated,
                })
        return {"weather_daily": rows}

    def load(self, conn, tables):
        return upsert(conn, "weather_daily", tables["weather_daily"], key=("city", "date"))
