import logging
import httpx

logger = logging.getLogger("aura.tools.location_service")

async def reverse_geocode_location(lat: float, lon: float) -> str:
    """Reverse geocode GPS coordinates to a display address via Nominatim API."""
    address = "Lokasi Tidak Diketahui"
    try:
        headers = {"User-Agent": "AuraTelegramBot/1.0 (khairulxshafiq)"}
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://nominatim.openstreetmap.org/reverse",
                params={"lat": lat, "lon": lon, "format": "json"},
                headers=headers
            )
            if resp.status_code == 200:
                data = resp.json()
                address = data.get("display_name", address)
    except Exception as e:
        logger.error(f"Error reverse geocoding location ({lat}, {lon}): {e}")
    return address

async def _get_weather_forecast(lat: float, lon: float) -> str:
    """Fetch 1-day hourly weather forecast from Open-Meteo API."""
    try:
        url = (
            f"https://api.open-meteo.com/v1/forecast?"
            f"latitude={lat}&longitude={lon}"
            f"&hourly=temperature_2m,weathercode,precipitation_probability"
            f"&timezone=Asia%2FKuala_Lumpur&forecast_days=1"
        )
        async with httpx.AsyncClient(timeout=8) as client:
            res = await client.get(url)
            if res.status_code == 200:
                data = res.json()
                hourly = data.get("hourly", {})
                temps = hourly.get("temperature_2m", [])
                codes = hourly.get("weathercode", [])
                precip = hourly.get("precipitation_probability", [])

                def get_desc(c, p):
                    if c == 0: return "☀️ Cerah"
                    elif c in [1, 2, 3]: return "⛅ Berawan"
                    elif c in [45, 48]: return "🌫️ Kabus"
                    elif c in [51, 53, 55, 61, 63, 65, 80, 81, 82]: return f"🌧️ Hujan ({p}%)"
                    elif c in [95, 96, 99]: return f"⛈️ Ribut ({p}%)"
                    return "🌤️ Redup"

                pagi = f"• *Pagi (9am)*: {get_desc(codes[9], precip[9])} | `{temps[9]}°C`"
                ptg = f"• *Petang (3pm)*: {get_desc(codes[15], precip[15])} | `{temps[15]}°C`"
                malam = f"• *Malam (9pm)*: {get_desc(codes[21], precip[21])} | `{temps[21]}°C`"
                return f"{pagi}\n{ptg}\n{malam}"
    except Exception as e:
        logger.warning(f"Weather forecast error: {e}")
    return "• *Cuaca*: Tidak dapat diproses"

async def _get_extended_weather_forecast(lat: float, lon: float) -> str:
    """Fetch 7-day daily weather forecast from Open-Meteo API."""
    try:
        url = (
            f"https://api.open-meteo.com/v1/forecast?"
            f"latitude={lat}&longitude={lon}"
            f"&daily=weathercode,temperature_2m_max,temperature_2m_min,precipitation_sum"
            f"&timezone=Asia%2FKuala_Lumpur&forecast_days=7"
        )
        async with httpx.AsyncClient(timeout=8) as client:
            res = await client.get(url)
            if res.status_code == 200:
                data = res.json()
                daily = data.get("daily", {})
                times = daily.get("time", [])
                max_temps = daily.get("temperature_2m_max", [])
                min_temps = daily.get("temperature_2m_min", [])
                codes = daily.get("weathercode", [])
                precip = daily.get("precipitation_sum", [])

                def get_desc(c):
                    if c == 0: return "☀️ Cerah"
                    elif c in [1, 2, 3]: return "⛅ Berawan"
                    elif c in [45, 48]: return "🌫️ Kabus"
                    elif c in [51, 53, 55, 61, 63, 65, 80, 81, 82]: return "🌧️ Hujan"
                    elif c in [95, 96, 99]: return "⛈️ Ribut"
                    return "🌤️ Redup"

                lines = []
                for i in range(len(times)):
                    date_str = times[i]
                    lines.append(f"• `{date_str}`: {get_desc(codes[i])} | `{min_temps[i]}°C - {max_temps[i]}°C` (Hujan: `{precip[i]}mm`)")

                return "\n".join(lines)
    except Exception as e:
        logger.warning(f"Extended weather forecast error: {e}")
    return "• *Cuaca 7 Hari*: Tidak dapat diproses"
