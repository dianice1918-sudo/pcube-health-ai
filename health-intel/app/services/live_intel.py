import json
import os
import re
import time
import urllib.parse
import urllib.request
from datetime import date, datetime


_OUTBREAK_HINTS = {
    "lassa fever": {
        "tokens": ("lassa",),
        "tip": "Store food in rodent-proof containers and seek hospital care quickly if fever persists.",
    },
    "cholera": {
        "tokens": ("cholera",),
        "tip": "Drink only safe water, wash hands frequently, and treat diarrhea urgently.",
    },
    "yellow fever": {
        "tokens": ("yellow fever",),
        "tip": "Use mosquito protection and seek urgent care for high fever or jaundice.",
    },
    "mpox": {
        "tokens": ("mpox", "monkeypox"),
        "tip": "Avoid close skin contact with symptomatic persons and isolate early for suspicious rash.",
    },
    "meningitis": {
        "tokens": ("meningitis",),
        "tip": "Persistent fever, neck stiffness, or confusion should be treated as an emergency.",
    },
    "measles": {
        "tokens": ("measles",),
        "tip": "Limit exposure for unvaccinated contacts and seek clinical review for fever with rash.",
    },
}

_INTEL_CACHE: dict[str, tuple[float, dict]] = {}
_ALERT_LEVEL_RANK = {"NORMAL": 0, "WARNING": 1, "URGENT": 2}
_HEADING_RE = re.compile(r"<h[1-4][^>]*>(.*?)</h[1-4]>", flags=re.IGNORECASE | re.DOTALL)
_ANCHOR_RE = re.compile(r"<a[^>]*>(.*?)</a>", flags=re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_SPACE_RE = re.compile(r"\s+")


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except Exception:
        return default


def _http_get_json(url: str, timeout: int = 12, headers: dict | None = None):
    try:
        req = urllib.request.Request(url=url, method="GET", headers=headers or {})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def _http_get_text(url: str, timeout: int = 12, headers: dict | None = None) -> str | None:
    try:
        req = urllib.request.Request(url=url, method="GET", headers=headers or {})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="ignore")
    except Exception:
        return None


def _as_float(value) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def _as_int(value) -> int | None:
    try:
        if value is None:
            return None
        return int(round(float(value)))
    except Exception:
        return None


def _unique_keep_order(values: list[str], max_items: int = 10) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in values:
        text = str(item or "").strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
        if len(out) >= max_items:
            break
    return out


def _weather_code_to_text(code: int | None) -> str | None:
    mapping = {
        0: "clear",
        1: "mainly clear",
        2: "partly cloudy",
        3: "overcast",
        45: "fog",
        48: "rime fog",
        51: "light drizzle",
        53: "moderate drizzle",
        55: "dense drizzle",
        61: "light rain",
        63: "moderate rain",
        65: "heavy rain",
        71: "light snow",
        73: "moderate snow",
        75: "heavy snow",
        80: "rain showers",
        81: "rain showers",
        82: "violent rain showers",
        95: "thunderstorm",
    }
    return mapping.get(code) if code is not None else None


def _fetch_openweather(lat: float, lon: float) -> dict:
    api_key = (os.getenv("OPENWEATHER_API_KEY") or "").strip()
    if not api_key:
        return {}
    url = (
        "https://api.openweathermap.org/data/3.0/onecall?"
        + urllib.parse.urlencode(
            {
                "lat": lat,
                "lon": lon,
                "units": "metric",
                "exclude": "minutely,hourly,daily,alerts",
                "appid": api_key,
            }
        )
    )
    data = _http_get_json(url)
    if not isinstance(data, dict):
        return {}
    current = data.get("current") if isinstance(data.get("current"), dict) else {}
    weather_rows = current.get("weather") if isinstance(current.get("weather"), list) else []
    desc = None
    if weather_rows and isinstance(weather_rows[0], dict):
        desc = weather_rows[0].get("description")
    return {
        "weather_condition": desc,
        "temperature_c": _as_float(current.get("temp")),
        "uv_index": _as_float(current.get("uvi")),
        "weather_source": "openweather",
    }


def _fetch_open_meteo(lat: float, lon: float) -> dict:
    weather_url = (
        "https://api.open-meteo.com/v1/forecast?"
        + urllib.parse.urlencode(
            {
                "latitude": lat,
                "longitude": lon,
                "current": "temperature_2m,weather_code,uv_index",
                "timezone": "auto",
            }
        )
    )
    air_url = (
        "https://air-quality-api.open-meteo.com/v1/air-quality?"
        + urllib.parse.urlencode(
            {
                "latitude": lat,
                "longitude": lon,
                "current": "us_aqi",
                "timezone": "auto",
            }
        )
    )
    weather_data = _http_get_json(weather_url) or {}
    air_data = _http_get_json(air_url) or {}
    current_w = weather_data.get("current", {}) if isinstance(weather_data.get("current"), dict) else {}
    current_a = air_data.get("current", {}) if isinstance(air_data.get("current"), dict) else {}
    return {
        "weather_condition": _weather_code_to_text(_as_int(current_w.get("weather_code"))),
        "temperature_c": _as_float(current_w.get("temperature_2m")),
        "uv_index": _as_float(current_w.get("uv_index")),
        "aqi": _as_int(current_a.get("us_aqi")),
        "weather_source": "open-meteo",
        "air_source": "open-meteo",
    }


def _fetch_iqair(lat: float, lon: float) -> dict:
    api_key = (os.getenv("IQAIR_API_KEY") or "").strip()
    if not api_key:
        return {}
    url = (
        "https://api.airvisual.com/v2/nearest_city?"
        + urllib.parse.urlencode({"lat": lat, "lon": lon, "key": api_key})
    )
    data = _http_get_json(url)
    if not isinstance(data, dict):
        return {}
    root = data.get("data") if isinstance(data.get("data"), dict) else {}
    current = root.get("current") if isinstance(root.get("current"), dict) else {}
    pollution = current.get("pollution") if isinstance(current.get("pollution"), dict) else {}
    return {
        "aqi": _as_int(pollution.get("aqius")),
        "air_source": "iqair",
    }


def fetch_weather_and_air(lat: float, lon: float) -> dict:
    weather = _fetch_openweather(lat, lon)
    fallback = _fetch_open_meteo(lat, lon)
    air = _fetch_iqair(lat, lon)

    condition = weather.get("weather_condition") or fallback.get("weather_condition")
    temperature = weather.get("temperature_c")
    if temperature is None:
        temperature = fallback.get("temperature_c")
    uv_index = weather.get("uv_index")
    if uv_index is None:
        uv_index = fallback.get("uv_index")
    aqi = air.get("aqi")
    if aqi is None:
        aqi = fallback.get("aqi")

    return {
        "weather_condition": condition,
        "temperature_c": temperature,
        "uv_index": uv_index,
        "aqi": aqi,
        "weather_source": weather.get("weather_source") or fallback.get("weather_source") or "unknown",
        "air_source": air.get("air_source") or fallback.get("air_source") or "unknown",
    }


def _normalize_text(raw: str) -> str:
    no_tags = _TAG_RE.sub(" ", raw)
    compact = _SPACE_RE.sub(" ", no_tags)
    return compact.strip()


def _extract_headlines_from_html(html: str, max_items: int = 80) -> list[str]:
    rows: list[str] = []
    for chunk in _HEADING_RE.findall(html):
        cleaned = _normalize_text(chunk)
        if len(cleaned) >= 12:
            rows.append(cleaned)
    for chunk in _ANCHOR_RE.findall(html):
        cleaned = _normalize_text(chunk)
        if len(cleaned) >= 20:
            rows.append(cleaned)
        if len(rows) >= max_items:
            break
    return _unique_keep_order(rows, max_items=max_items)


def _ncdc_outbreak_signals() -> list[dict]:
    url = os.getenv("NCDC_ALERT_URL", "https://ncdc.gov.ng/news").strip() or "https://ncdc.gov.ng/news"
    html = _http_get_text(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; PCUBE/1.0)",
            "Accept": "text/html,application/xhtml+xml,application/xml",
        },
    )
    if not html:
        return []

    signals: list[dict] = []
    titles = _extract_headlines_from_html(html)
    for title in titles:
        lower = title.lower()
        for disease, cfg in _OUTBREAK_HINTS.items():
            tokens = cfg["tokens"]
            if any(token in lower for token in tokens):
                signals.append(
                    {
                        "disease": disease.title(),
                        "title": title,
                        "tip": cfg["tip"],
                        "source": "ncdc",
                    }
                )
    unique = []
    seen = set()
    for row in signals:
        key = (row["disease"].lower(), row["title"].lower())
        if key in seen:
            continue
        seen.add(key)
        unique.append(row)
    return unique[:8]


def _newsapi_outbreak_signals(location_label: str | None, today: date) -> list[dict]:
    api_key = (os.getenv("NEWSAPI_KEY") or "").strip()
    if not api_key:
        return []
    location = (location_label or "Nigeria").strip() or "Nigeria"
    query = f"{location} outbreak OR lassa OR cholera OR meningitis OR yellow fever OR mpox"
    url = (
        "https://newsapi.org/v2/everything?"
        + urllib.parse.urlencode(
            {
                "q": query,
                "language": "en",
                "sortBy": "publishedAt",
                "pageSize": 12,
                "from": today.isoformat(),
            }
        )
    )
    data = _http_get_json(url, headers={"X-Api-Key": api_key})
    if not isinstance(data, dict):
        return []
    rows = data.get("articles") if isinstance(data.get("articles"), list) else []
    signals: list[dict] = []
    for row in rows:
        title = ""
        if isinstance(row, dict):
            title = str(row.get("title") or "").strip()
        if not title:
            continue
        lower = title.lower()
        for disease, cfg in _OUTBREAK_HINTS.items():
            if any(token in lower for token in cfg["tokens"]):
                signals.append(
                    {
                        "disease": disease.title(),
                        "title": title,
                        "tip": cfg["tip"],
                        "source": "newsapi",
                    }
                )
    unique = []
    seen = set()
    for row in signals:
        key = (row["disease"].lower(), row["title"].lower())
        if key in seen:
            continue
        seen.add(key)
        unique.append(row)
    return unique[:6]


def _google_custom_search(query: str, limit: int = 3) -> list[str]:
    api_key = (os.getenv("GOOGLE_API_KEY") or "").strip()
    cse_id = (os.getenv("GOOGLE_CSE_ID") or "").strip()
    if not api_key or not cse_id:
        return []

    url = (
        "https://www.googleapis.com/customsearch/v1?"
        + urllib.parse.urlencode(
            {
                "key": api_key,
                "cx": cse_id,
                "q": query,
                "num": max(1, min(limit, 10)),
            }
        )
    )
    data = _http_get_json(url) or {}
    items = data.get("items", []) if isinstance(data.get("items"), list) else []
    results: list[str] = []
    for item in items:
        title = item.get("title")
        snippet = item.get("snippet")
        if title and snippet:
            results.append(f"{title}: {snippet}")
        elif snippet:
            results.append(str(snippet))
        if len(results) >= limit:
            break
    return _unique_keep_order(results, max_items=limit)


def _classify_intel_alert_level(aqi: int | None, uv_index: float | None, outbreak_count: int) -> str:
    if outbreak_count > 0:
        return "URGENT"
    if aqi is not None and aqi >= 151:
        return "URGENT"
    if uv_index is not None and uv_index >= 11:
        return "URGENT"
    if (aqi is not None and aqi > 100) or (uv_index is not None and uv_index > 7):
        return "WARNING"
    return "NORMAL"


def _environment_tips(aqi: int | None, uv_index: float | None, temperature_c: float | None, weather_condition: str | None) -> list[str]:
    tips: list[str] = []
    if aqi is not None and aqi > 100:
        tips.append("Air quality is unhealthy right now. Wear an N95 mask outdoors and reduce prolonged outdoor activity.")
    if uv_index is not None and uv_index > 7:
        tips.append("UV exposure is high. Use sunscreen and avoid long outdoor exposure between 11 AM and 4 PM.")
    if temperature_c is not None and temperature_c >= 34:
        tips.append("Heat stress risk is elevated. Increase water intake, rest in shade, and avoid intense midday exercise.")
    condition = (weather_condition or "").lower()
    if "rain" in condition or "storm" in condition:
        tips.append("Rainy conditions can increase mosquito and water-borne disease risk. Keep water storage covered and use repellents.")
    return _unique_keep_order(tips, max_items=6)


def _build_summary(
    *,
    location_label: str | None,
    weather_condition: str | None,
    temperature_c: float | None,
    uv_index: float | None,
    aqi: int | None,
    outbreak_alerts: list[str],
) -> str:
    city = (location_label or "your location").strip() or "your location"
    chunks: list[str] = []
    weather_part: list[str] = []
    if temperature_c is not None:
        weather_part.append(f"{temperature_c:.0f}C")
    if weather_condition:
        weather_part.append(weather_condition)
    if weather_part:
        chunks.append(f"{city}: {' and '.join(weather_part)}.")
    if aqi is not None:
        chunks.append(f"AQI is {aqi}.")
    if uv_index is not None:
        chunks.append(f"UV index is {uv_index:.1f}.")
    if outbreak_alerts:
        chunks.append(f"Outbreak signal: {outbreak_alerts[0]}")
    if not chunks:
        return "Live intelligence is currently limited, but no severe signal is detected."
    return " ".join(chunks)


def _build_speak_text(alert_level: str, summary: str, health_tips: list[str]) -> str:
    lead = {
        "URGENT": "Urgent health alert.",
        "WARNING": "Health warning.",
        "NORMAL": "Health update.",
    }.get(alert_level, "Health update.")
    details = " ".join([summary] + health_tips[:2])
    text = f"{lead} {details}".strip()
    return text[:650]


def alert_level_rank(level: str | None) -> int:
    return _ALERT_LEVEL_RANK.get(str(level or "").upper(), 0)


def fetch_google_health_intel(location_label: str | None, today: date) -> dict:
    location = (location_label or "Nigeria").strip() or "Nigeria"
    day_txt = today.isoformat()

    ncdc_rows = _ncdc_outbreak_signals()
    news_rows = _newsapi_outbreak_signals(location, today)
    all_rows = ncdc_rows + news_rows
    outbreak_alerts = [
        f"{row['disease']}: {row['title']}"
        for row in all_rows
    ]
    health_tips = [row["tip"] for row in all_rows]

    # Optional Google CSE fallback for broad intel sources.
    if not outbreak_alerts:
        outbreak_query = f"{location} disease outbreak {day_txt} NCDC WHO CDC"
        outbreak_alerts.extend(_google_custom_search(outbreak_query, limit=2))
    tips_query = f"{location} weather health tips air quality hydration heat safety"
    health_tips.extend(_google_custom_search(tips_query, limit=3))

    return {
        "outbreak_alerts": _unique_keep_order(outbreak_alerts, max_items=6),
        "health_tips": _unique_keep_order(health_tips, max_items=8),
        "outbreak_sources": _unique_keep_order([row["source"] for row in all_rows], max_items=3),
    }


def collect_live_intel(lat: float, lon: float, location_label: str | None, today: date) -> dict:
    ttl_seconds = max(60, _env_int("LIVE_INTEL_CACHE_SECONDS", 900))
    key = f"{round(float(lat), 3)}|{round(float(lon), 3)}|{(location_label or '').strip().lower()}|{today.isoformat()}"
    now = time.time()
    cached = _INTEL_CACHE.get(key)
    if cached and (now - cached[0]) <= ttl_seconds:
        return dict(cached[1])

    weather = fetch_weather_and_air(lat, lon)
    intel = fetch_google_health_intel(location_label, today)

    outbreak_alerts = _unique_keep_order(intel.get("outbreak_alerts", []), max_items=5)
    env_tips = _environment_tips(
        weather.get("aqi"),
        weather.get("uv_index"),
        weather.get("temperature_c"),
        weather.get("weather_condition"),
    )
    health_tips = _unique_keep_order(env_tips + list(intel.get("health_tips", [])), max_items=8)
    alert_level = _classify_intel_alert_level(
        aqi=weather.get("aqi"),
        uv_index=weather.get("uv_index"),
        outbreak_count=len(outbreak_alerts),
    )
    summary = _build_summary(
        location_label=location_label,
        weather_condition=weather.get("weather_condition"),
        temperature_c=weather.get("temperature_c"),
        uv_index=weather.get("uv_index"),
        aqi=weather.get("aqi"),
        outbreak_alerts=outbreak_alerts,
    )
    speak_text = _build_speak_text(alert_level, summary, health_tips)
    payload = {
        "city": location_label,
        "weather_condition": weather.get("weather_condition"),
        "temperature_c": weather.get("temperature_c"),
        "uv_index": weather.get("uv_index"),
        "aqi": weather.get("aqi"),
        "environment_tips": env_tips,
        "outbreak_alerts": outbreak_alerts,
        "health_tips": health_tips,
        "alert_level": alert_level,
        "summary": summary,
        "speak_text": speak_text,
        "generated_at": datetime.utcnow(),
        "sources": {
            "weather": weather.get("weather_source", "unknown"),
            "air_quality": weather.get("air_source", "unknown"),
            "outbreak": ", ".join(intel.get("outbreak_sources", []) or ["ncdc/news"]),
        },
    }
    _INTEL_CACHE[key] = (now, payload)
    return dict(payload)
