"""Ứng dụng Flask: Bản đồ trường THPT và thời tiết đến trường ở Bình Dương.

WebApp hiển thị linh hoạt một hoặc hai vị trí, chỉ sử dụng Open-Meteo:
- Vị trí GPS của học sinh.
- Trường học đang được chọn.

Thời tiết chỉ lấy từ Open-Meteo theo GPS. Khi API không phản hồi,
ứng dụng báo lỗi hoặc hiển thị dữ liệu Open-Meteo gần nhất có ghi nhãn cũ.
Chu kỳ kiểm tra 5 phút không phải chu kỳ cập nhật của mô hình khí tượng.
"""

from __future__ import annotations

import copy
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
import math
import os
import socket
import sys
import tempfile
import threading
import time
import unicodedata
import webbrowser
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from flask import Flask, jsonify, render_template, request, send_from_directory

ROOT = Path(__file__).resolve().parent
DATA_FILE = ROOT / "data" / "schools.json"

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_TIMEOUT_SECONDS = 7.0
# Chỉ dùng cache Open-Meteo cũ tối đa 15 phút và luôn ghi rõ đã cũ.
LAST_GOOD_MAX_AGE_MINUTES = 15
VIETNAM_TZ = timezone(timedelta(hours=7), name="UTC+07:00")
WEATHER_INTERVAL_MINUTES = 5

CURRENT_WEATHER_FIELDS = (
    "temperature_2m",
    "relative_humidity_2m",
    "apparent_temperature",
    "precipitation",
    "rain",
    "weather_code",
    "wind_speed_10m",
    "wind_direction_10m",
    "is_day",
)

HOURLY_WEATHER_FIELDS = (
    "temperature_2m",
    "apparent_temperature",
    "relative_humidity_2m",
    "precipitation_probability",
    "precipitation",
    "weather_code",
    "wind_speed_10m",
    "is_day",
)

app = Flask(__name__)
app.json.ensure_ascii = False



@app.get("/manifest.webmanifest")
def pwa_manifest():
    return send_from_directory(ROOT / "static", "manifest.webmanifest", mimetype="application/manifest+json")


@app.get("/service-worker.js")
def pwa_service_worker():
    response = send_from_directory(ROOT / "static", "service-worker.js", mimetype="application/javascript")
    response.headers["Service-Worker-Allowed"] = "/"
    response.headers["Cache-Control"] = "no-cache"
    return response


DATA_LOCK = threading.RLock()
WEATHER_CACHE_LOCK = threading.RLock()
WEATHER_CACHE: dict[tuple[str, float, float], dict[str, Any]] = {}
LAST_GOOD_WEATHER: dict[tuple[float, float], dict[str, Any]] = {}

DATA_CACHE: dict[str, Any] | None = None
DATA_CACHE_MTIME_NS: int | None = None


def normalize_text(value: Any) -> str:
    """Chuẩn hóa chuỗi tiếng Việt để tìm kiếm không dấu."""
    text = str(value or "").strip().lower()
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = text.replace("đ", "d")
    return " ".join(text.split())


def load_database() -> dict[str, Any]:
    """Đọc schools.json có cache theo mtime để giảm I/O khi nhiều học sinh truy cập cùng lúc."""
    global DATA_CACHE, DATA_CACHE_MTIME_NS
    if not DATA_FILE.exists():
        raise FileNotFoundError(f"Không tìm thấy tệp dữ liệu: {DATA_FILE}")
    mtime_ns = DATA_FILE.stat().st_mtime_ns
    with DATA_LOCK:
        if DATA_CACHE is not None and DATA_CACHE_MTIME_NS == mtime_ns:
            return DATA_CACHE
        with DATA_FILE.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        if not isinstance(data.get("schools"), list):
            raise ValueError("schools.json không có danh sách 'schools' hợp lệ")
        DATA_CACHE = data
        DATA_CACHE_MTIME_NS = mtime_ns
        return data


def save_database(data: dict[str, Any]) -> None:
    """Ghi JSON theo kiểu atomic để tránh hỏng tệp nếu chương trình bị dừng."""
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    with DATA_LOCK:
        fd, temp_name = tempfile.mkstemp(
            prefix="schools_", suffix=".json.tmp", dir=str(DATA_FILE.parent)
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(data, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
            os.replace(temp_name, DATA_FILE)
            global DATA_CACHE, DATA_CACHE_MTIME_NS
            DATA_CACHE = data
            DATA_CACHE_MTIME_NS = DATA_FILE.stat().st_mtime_ns
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)


def find_school(data: dict[str, Any], school_id: str) -> dict[str, Any] | None:
    return next((item for item in data["schools"] if item.get("id") == school_id), None)


def school_search_blob(school: dict[str, Any]) -> str:
    fields = (
        school.get("name"),
        school.get("short_name"),
        school.get("address"),
        school.get("ward_name"),
        school.get("district_name"),
        school.get("school_type"),
    )
    return normalize_text(" ".join(str(item or "") for item in fields))


def valid_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def query_float(name: str) -> float:
    raw = request.args.get(name, "").strip()
    try:
        value = float(raw)
    except (TypeError, ValueError) as error:
        raise ValueError(f"Tham số {name} không hợp lệ") from error
    if not math.isfinite(value):
        raise ValueError(f"Tham số {name} không hợp lệ")
    return value


def current_weather_slot(now: datetime | None = None) -> datetime:
    """Trả về mốc 5 phút gần nhất theo giờ Việt Nam."""
    moment = (now or datetime.now(VIETNAM_TZ)).astimezone(VIETNAM_TZ)
    minute = moment.minute - (moment.minute % WEATHER_INTERVAL_MINUTES)
    return moment.replace(minute=minute, second=0, microsecond=0)


def next_weather_slot(slot: datetime) -> datetime:
    return slot + timedelta(minutes=WEATHER_INTERVAL_MINUTES)


def iso_local(moment: datetime) -> str:
    return moment.astimezone(VIETNAM_TZ).isoformat(timespec="seconds")


def finite_or_none(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def int_or_none(value: Any) -> int | None:
    number = finite_or_none(value)
    return int(round(number)) if number is not None else None


def parse_open_meteo_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=VIETNAM_TZ)
    return parsed.astimezone(VIETNAM_TZ)


def weather_description(code: int | None, is_day: int | None = 1) -> dict[str, str]:
    day = is_day != 0
    mapping: dict[int, tuple[str, str, str]] = {
        0: ("Trời quang", "☀️", "🌙"),
        1: ("Ít mây", "🌤️", "🌙"),
        2: ("Mây rải rác", "⛅", "☁️"),
        3: ("Nhiều mây", "☁️", "☁️"),
        45: ("Sương mù", "🌫️", "🌫️"),
        48: ("Sương mù đóng băng", "🌫️", "🌫️"),
        51: ("Mưa phùn nhẹ", "🌦️", "🌧️"),
        53: ("Mưa phùn", "🌦️", "🌧️"),
        55: ("Mưa phùn dày", "🌧️", "🌧️"),
        56: ("Mưa phùn lạnh nhẹ", "🌧️", "🌧️"),
        57: ("Mưa phùn lạnh", "🌧️", "🌧️"),
        61: ("Mưa nhẹ", "🌦️", "🌧️"),
        63: ("Mưa vừa", "🌧️", "🌧️"),
        65: ("Mưa to", "🌧️", "🌧️"),
        66: ("Mưa lạnh nhẹ", "🌧️", "🌧️"),
        67: ("Mưa lạnh", "🌧️", "🌧️"),
        71: ("Tuyết nhẹ", "🌨️", "🌨️"),
        73: ("Tuyết vừa", "🌨️", "🌨️"),
        75: ("Tuyết dày", "❄️", "❄️"),
        77: ("Hạt tuyết", "❄️", "❄️"),
        80: ("Mưa rào nhẹ", "🌦️", "🌧️"),
        81: ("Mưa rào", "🌧️", "🌧️"),
        82: ("Mưa rào mạnh", "⛈️", "⛈️"),
        85: ("Mưa tuyết nhẹ", "🌨️", "🌨️"),
        86: ("Mưa tuyết mạnh", "🌨️", "🌨️"),
        95: ("Dông", "⛈️", "⛈️"),
        96: ("Dông kèm mưa đá nhẹ", "⛈️", "⛈️"),
        99: ("Dông kèm mưa đá mạnh", "⛈️", "⛈️"),
    }
    label, day_icon, night_icon = mapping.get(code or -1, ("Chưa xác định", "🌤️", "🌙"))
    return {"label": label, "icon": day_icon if day else night_icon}


class WeatherProviderError(RuntimeError):
    """Lỗi nguồn thời tiết có thông báo thân thiện và chi tiết để ghi log."""

    def __init__(
        self,
        provider: str,
        public_message: str,
        technical_message: str | None = None,
        status: int | None = None,
    ) -> None:
        super().__init__(public_message)
        self.provider = provider
        self.public_message = public_message
        self.technical_message = technical_message or public_message
        self.status = status


def fetch_json_source(
    url: str,
    *,
    provider: str,
    timeout: float,
    headers: dict[str, str],
) -> Any:
    request_object = Request(url, headers=headers)
    try:
        with urlopen(request_object, timeout=timeout) as response:
            raw = response.read()
        return json.loads(raw.decode("utf-8"))
    except HTTPError as error:
        detail = ""
        try:
            detail = error.read().decode("utf-8", errors="replace")[:400]
        except Exception:
            pass
        if error.code in (429, 500, 502, 503, 504):
            public = f"{provider} đang bận hoặc quá tải"
        else:
            public = f"{provider} tạm thời không phản hồi"
        raise WeatherProviderError(
            provider,
            public,
            f"HTTP {error.code}: {detail or error.reason}",
            status=error.code,
        ) from error
    except TimeoutError as error:
        raise WeatherProviderError(
            provider,
            f"{provider} phản hồi quá chậm",
            "Hết thời gian chờ kết nối",
        ) from error
    except URLError as error:
        raise WeatherProviderError(
            provider,
            f"Không kết nối được {provider}",
            str(error.reason or error),
        ) from error
    except (json.JSONDecodeError, OSError) as error:
        raise WeatherProviderError(
            provider,
            f"{provider} trả dữ liệu không hợp lệ",
            str(error),
        ) from error


def open_meteo_batch_request(points: list[tuple[float, float]]) -> list[dict[str, Any]]:
    """Gọi Open-Meteo một lần cho một hoặc nhiều tọa độ."""
    if not points:
        return []

    params = {
        "latitude": ",".join(f"{lat:.6f}" for lat, _ in points),
        "longitude": ",".join(f"{lon:.6f}" for _, lon in points),
        "current": ",".join(CURRENT_WEATHER_FIELDS),
        "hourly": ",".join(HOURLY_WEATHER_FIELDS),
        "timezone": "Asia/Ho_Chi_Minh",
        # Chỉ lấy vài giờ cần hiển thị, tránh tải 48 giờ dữ liệu không dùng tới.
        "forecast_hours": "4",
        "temperature_unit": "celsius",
        "wind_speed_unit": "kmh",
        "precipitation_unit": "mm",
        "cell_selection": "land",
    }
    url = f"{OPEN_METEO_URL}?{urlencode(params)}"
    payload = fetch_json_source(
        url,
        provider="Open-Meteo",
        timeout=OPEN_METEO_TIMEOUT_SECONDS,
        headers={
            "Accept": "application/json",
            "User-Agent": "BinhDuongSchoolWeather/7.3 (+local education project)",
        },
    )

    if len(points) == 1:
        payloads = [payload]
    elif isinstance(payload, list):
        payloads = payload
    else:
        raise WeatherProviderError(
            "Open-Meteo",
            "Open-Meteo trả dữ liệu không hợp lệ",
            "Yêu cầu nhiều tọa độ nhưng phản hồi không phải danh sách",
        )

    if len(payloads) != len(points):
        raise WeatherProviderError(
            "Open-Meteo",
            "Open-Meteo trả thiếu dữ liệu",
            f"Cần {len(points)} vị trí nhưng nhận {len(payloads)}",
        )

    result: list[dict[str, Any]] = []
    for payload_item in payloads:
        if not isinstance(payload_item, dict):
            raise WeatherProviderError(
                "Open-Meteo",
                "Open-Meteo trả dữ liệu không hợp lệ",
                "Một phần tử phản hồi không phải JSON object",
            )
        if payload_item.get("error"):
            raise WeatherProviderError(
                "Open-Meteo",
                "Open-Meteo đang bận hoặc báo lỗi",
                str(payload_item.get("reason") or payload_item),
            )
        result.append(payload_item)
    return result


def hourly_row(hourly: dict[str, Any], index: int) -> dict[str, Any]:
    def item(name: str) -> Any:
        values = hourly.get(name)
        if not isinstance(values, list) or index < 0 or index >= len(values):
            return None
        return values[index]

    time_value = item("time")
    code = int_or_none(item("weather_code"))
    is_day = int_or_none(item("is_day"))
    descriptor = weather_description(code, is_day)
    return {
        "time": time_value,
        "temperature_c": finite_or_none(item("temperature_2m")),
        "apparent_temperature_c": finite_or_none(item("apparent_temperature")),
        "humidity_percent": finite_or_none(item("relative_humidity_2m")),
        "precipitation_probability_percent": finite_or_none(item("precipitation_probability")),
        "precipitation_mm": finite_or_none(item("precipitation")),
        "wind_speed_kmh": finite_or_none(item("wind_speed_10m")),
        "weather_code": code,
        "is_day": is_day,
        "condition": descriptor["label"],
        "icon": descriptor["icon"],
    }


def normalize_open_meteo(payload: dict[str, Any], lat: float, lon: float) -> dict[str, Any]:
    current = payload.get("current") if isinstance(payload.get("current"), dict) else {}
    hourly = payload.get("hourly") if isinstance(payload.get("hourly"), dict) else {}
    current_units = payload.get("current_units") if isinstance(payload.get("current_units"), dict) else {}
    hourly_times = hourly.get("time") if isinstance(hourly.get("time"), list) else []

    source_time = parse_open_meteo_time(current.get("time"))
    reference_time = source_time or datetime.now(VIETNAM_TZ)

    parsed_hourly_times: list[datetime | None] = [parse_open_meteo_time(value) for value in hourly_times]
    valid_time_indexes = [(idx, moment) for idx, moment in enumerate(parsed_hourly_times) if moment is not None]

    nearest_index: int | None = None
    if valid_time_indexes:
        nearest_index = min(valid_time_indexes, key=lambda pair: abs((pair[1] - reference_time).total_seconds()))[0]

    forecast_indexes = [
        idx
        for idx, moment in valid_time_indexes
        if moment > reference_time
    ][:2]

    current_code = int_or_none(current.get("weather_code"))
    is_day = int_or_none(current.get("is_day"))
    descriptor = weather_description(current_code, is_day)
    nearest_hour = hourly_row(hourly, nearest_index) if nearest_index is not None else {}

    return {
        "provider": {
            "name": "Open-Meteo",
            "url": "https://open-meteo.com/",
            "is_fallback": False,
        },
        "fetched_at": iso_local(datetime.now(VIETNAM_TZ)),
        "model_updated_at": None,
        "stale": False,
        "coordinates": {
            "requested_lat": round(lat, 6),
            "requested_lon": round(lon, 6),
            "model_lat": finite_or_none(payload.get("latitude")),
            "model_lon": finite_or_none(payload.get("longitude")),
            "elevation_m": finite_or_none(payload.get("elevation")),
        },
        "source_time": current.get("time"),
        "timezone": payload.get("timezone") or "Asia/Ho_Chi_Minh",
        "current": {
            "temperature_c": finite_or_none(current.get("temperature_2m")),
            "apparent_temperature_c": finite_or_none(current.get("apparent_temperature")),
            "humidity_percent": finite_or_none(current.get("relative_humidity_2m")),
            "precipitation_probability_percent": nearest_hour.get("precipitation_probability_percent"),
            "precipitation_mm": finite_or_none(current.get("precipitation")),
            "rain_mm": finite_or_none(current.get("rain")),
            "wind_speed_kmh": finite_or_none(current.get("wind_speed_10m")),
            "wind_direction_degrees": finite_or_none(current.get("wind_direction_10m")),
            "weather_code": current_code,
            "is_day": is_day,
            "condition": descriptor["label"],
            "icon": descriptor["icon"],
        },
        "forecast": [hourly_row(hourly, idx) for idx in forecast_indexes],
        "units": {
            "temperature": current_units.get("temperature_2m", "°C"),
            "humidity": current_units.get("relative_humidity_2m", "%"),
            "precipitation": current_units.get("precipitation", "mm"),
            "wind_speed": current_units.get("wind_speed_10m", "km/h"),
        },
    }


def weather_cache_key(slot: datetime, lat: float, lon: float) -> tuple[str, float, float]:
    return (slot.isoformat(timespec="minutes"), round(lat, 5), round(lon, 5))


def last_good_key(lat: float, lon: float) -> tuple[float, float]:
    return (round(lat, 5), round(lon, 5))


def store_weather_result(slot: datetime, lat: float, lon: float, weather: dict[str, Any]) -> None:
    slot_key = weather_cache_key(slot, lat, lon)
    latest_key = last_good_key(lat, lon)
    saved = copy.deepcopy(weather)
    with WEATHER_CACHE_LOCK:
        WEATHER_CACHE[slot_key] = saved
        LAST_GOOD_WEATHER[latest_key] = {
            "weather": copy.deepcopy(saved),
            "saved_at": datetime.now(VIETNAM_TZ),
        }


def latest_good_weather(lat: float, lon: float) -> dict[str, Any] | None:
    key = last_good_key(lat, lon)
    with WEATHER_CACHE_LOCK:
        entry = LAST_GOOD_WEATHER.get(key)
        if not isinstance(entry, dict):
            return None
        saved_at = entry.get("saved_at")
        weather = entry.get("weather")
        if not isinstance(saved_at, datetime) or not isinstance(weather, dict):
            return None
        age = datetime.now(VIETNAM_TZ) - saved_at
        if age > timedelta(minutes=LAST_GOOD_MAX_AGE_MINUTES):
            LAST_GOOD_WEATHER.pop(key, None)
            return None
        result = copy.deepcopy(weather)
        result["stale"] = True
        result["stale_age_minutes"] = max(0, round(age.total_seconds() / 60, 1))
        result["stale_reason"] = "Nguồn trực tuyến đang bận; đang hiển thị lần lấy thành công gần nhất."
        return result


def cleanup_weather_cache(active_slot: datetime) -> None:
    cutoff = active_slot - timedelta(minutes=WEATHER_INTERVAL_MINUTES * 4)
    latest_cutoff = datetime.now(VIETNAM_TZ) - timedelta(minutes=LAST_GOOD_MAX_AGE_MINUTES)
    with WEATHER_CACHE_LOCK:
        stale_slot_keys = []
        for key in WEATHER_CACHE:
            try:
                slot = datetime.fromisoformat(key[0])
            except ValueError:
                stale_slot_keys.append(key)
                continue
            if slot.tzinfo is None:
                slot = slot.replace(tzinfo=VIETNAM_TZ)
            if slot < cutoff:
                stale_slot_keys.append(key)
        for key in stale_slot_keys:
            WEATHER_CACHE.pop(key, None)

        stale_latest_keys = [
            key for key, entry in LAST_GOOD_WEATHER.items()
            if not isinstance(entry.get("saved_at"), datetime) or entry["saved_at"] < latest_cutoff
        ]
        for key in stale_latest_keys:
            LAST_GOOD_WEATHER.pop(key, None)


def resolve_weather_targets(
    targets: dict[str, tuple[float, float]],
    slot: datetime,
) -> tuple[dict[str, dict[str, Any]], dict[str, bool], dict[str, str], list[str]]:
    """Chỉ dùng Open-Meteo: cache theo mốc → API → cache Open-Meteo có nhãn cũ.

    Không dùng nguồn dự phòng khác và không tự suy diễn thông số khi API thất bại.
    """
    results: dict[str, dict[str, Any]] = {}
    cache_flags: dict[str, bool] = {}
    errors: dict[str, str] = {}
    events: list[str] = []
    missing: list[tuple[str, float, float]] = []

    for name, (lat, lon) in targets.items():
        key = weather_cache_key(slot, lat, lon)
        with WEATHER_CACHE_LOCK:
            cached = WEATHER_CACHE.get(key)
        if isinstance(cached, dict):
            results[name] = copy.deepcopy(cached)
            cache_flags[name] = True
        else:
            missing.append((name, lat, lon))

    if missing:
        try:
            payloads = open_meteo_batch_request([(lat, lon) for _, lat, lon in missing])
            for (name, lat, lon), payload in zip(missing, payloads):
                weather = normalize_open_meteo(payload, lat, lon)
                store_weather_result(slot, lat, lon, weather)
                results[name] = weather
                cache_flags[name] = False
            missing = []
        except Exception as error:
            # Nếu yêu cầu nhiều tọa độ cùng lúc lỗi, thử từng điểm độc lập.
            # Nhờ vậy lỗi tại Nhà riêng/GPS không làm mất kết quả của điểm còn lại.
            app.logger.warning("Open-Meteo batch lỗi, thử từng vị trí: %s", error)
            events.append("Yêu cầu thời tiết nhiều vị trí gặp lỗi; đang thử riêng từng vị trí.")
            retry_targets = list(missing)
            failed: list[tuple[str, float, float]] = []

            def fetch_one(target: tuple[str, float, float]):
                name, lat, lon = target
                payload = open_meteo_batch_request([(lat, lon)])[0]
                return name, lat, lon, normalize_open_meteo(payload, lat, lon)

            # Chạy song song để không cộng dồn thời gian chờ của từng tọa độ.
            with ThreadPoolExecutor(max_workers=min(4, len(retry_targets))) as pool:
                futures = {pool.submit(fetch_one, target): target for target in retry_targets}
                for future in as_completed(futures):
                    target = futures[future]
                    try:
                        name, lat, lon, weather = future.result()
                        store_weather_result(slot, lat, lon, weather)
                        results[name] = weather
                        cache_flags[name] = False
                    except Exception as retry_error:
                        app.logger.warning("Open-Meteo lỗi tại %s: %s", target[0], retry_error)
                        failed.append(target)
            missing = failed

    for name, lat, lon in missing:
        stale = latest_good_weather(lat, lon)
        if stale is not None and stale.get("provider", {}).get("name") == "Open-Meteo":
            results[name] = stale
            cache_flags[name] = True
            events.append("Dữ liệu Open-Meteo lấy trước đó, đã đánh dấu cũ.")
        else:
            errors[name] = "Chưa lấy được dữ liệu Open-Meteo. Hãy thử lại sau ít phút."

    cleanup_weather_cache(slot)
    return results, cache_flags, errors, list(dict.fromkeys(events))


@app.after_request
def add_no_cache_headers(response):
    # HTML/API nội bộ không cache; dữ liệu thời tiết có cache 5 phút riêng ở backend.
    response.headers["Cache-Control"] = "no-store, max-age=0"
    response.headers["Pragma"] = "no-cache"
    return response


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/health")
def health():
    data = load_database()
    return jsonify(
        {
            "ok": True,
            "service": "binh-duong-school-weather-map",
            "version": data.get("metadata", {}).get("version", "1.0.0"),
            "school_count": len(data["schools"]),
            "weather_provider": "Open-Meteo",
            "weather_interval_minutes": WEATHER_INTERVAL_MINUTES,
        }
    )


@app.get("/api/districts")
def districts():
    data = load_database()
    counts: dict[str, int] = {}
    for school in data["schools"]:
        district_id = str(school.get("district_id", ""))
        counts[district_id] = counts.get(district_id, 0) + 1

    result = []
    for district in data.get("districts", []):
        item = dict(district)
        item["school_count"] = counts.get(str(item.get("id", "")), 0)
        result.append(item)
    return jsonify({"count": len(result), "districts": result})


@app.get("/api/schools")
def schools():
    data = load_database()
    district = request.args.get("district", "").strip()
    quality = request.args.get("quality", "").strip()
    query = normalize_text(request.args.get("q", ""))

    result = []
    for school in data["schools"]:
        if district and school.get("district_id") != district:
            continue
        if quality and school.get("coordinate_quality") != quality:
            continue
        if query and query not in school_search_blob(school):
            continue
        result.append(school)

    result.sort(key=lambda item: normalize_text(item.get("name", "")))
    return jsonify(
        {
            "metadata": data.get("metadata", {}),
            "filters": {"district": district, "quality": quality, "q": request.args.get("q", "")},
            "count": len(result),
            "schools": result,
        }
    )


@app.get("/api/schools/<school_id>")
def school_detail(school_id: str):
    data = load_database()
    school = find_school(data, school_id)
    if school is None:
        return jsonify({"ok": False, "error": "Không tìm thấy trường học"}), 404
    return jsonify({"ok": True, "school": school})


@app.get("/api/weather-info")
def weather_info():
    """Trả thời tiết cho một hoặc cả hai vị trí.

    Có thể gọi theo một trong ba cách:
    - Chỉ vị trí học sinh: user_lat + user_lon.
    - Chỉ trường học: school_id.
    - Cả hai: user_lat + user_lon + school_id.

    Nhờ vậy, vừa chọn trường là có thể hiện thời tiết trường ngay; GPS gửi mẫu
    đầu tiên là có thể hiện thời tiết vị trí học sinh ngay, không cần chờ đủ 60 giây.
    """
    user_lat_raw = request.args.get("user_lat", "").strip()
    user_lon_raw = request.args.get("user_lon", "").strip()
    school_id = request.args.get("school_id", "").strip()

    wants_student = bool(user_lat_raw or user_lon_raw)
    wants_school = bool(school_id)

    if wants_student and (not user_lat_raw or not user_lon_raw):
        return jsonify({"ok": False, "error": "Cần đủ user_lat và user_lon"}), 400
    if not wants_student and not wants_school:
        return jsonify({"ok": False, "error": "Cần tọa độ học sinh hoặc school_id"}), 400

    user_lat: float | None = None
    user_lon: float | None = None
    if wants_student:
        try:
            user_lat = query_float("user_lat")
            user_lon = query_float("user_lon")
        except ValueError as error:
            return jsonify({"ok": False, "error": str(error)}), 400
        if not (-90 <= user_lat <= 90 and -180 <= user_lon <= 180):
            return jsonify({"ok": False, "error": "Tọa độ học sinh nằm ngoài phạm vi hợp lệ"}), 400

    school: dict[str, Any] | None = None
    school_lat: float | None = None
    school_lon: float | None = None
    if wants_school:
        data = load_database()
        school = find_school(data, school_id)
        if school is None:
            return jsonify({"ok": False, "error": "Không tìm thấy trường học"}), 404
        school_lat = finite_or_none(school.get("lat"))
        school_lon = finite_or_none(school.get("lon"))
        if school_lat is None or school_lon is None:
            return jsonify({"ok": False, "error": "Trường chưa có tọa độ hợp lệ"}), 409

    slot = current_weather_slot()
    checked_at = datetime.now(VIETNAM_TZ)

    targets: dict[str, tuple[float, float]] = {}
    if wants_student and user_lat is not None and user_lon is not None:
        targets["student"] = (user_lat, user_lon)
    if wants_school and school_lat is not None and school_lon is not None:
        targets["school"] = (school_lat, school_lon)

    results, cache_flags, errors, provider_events = resolve_weather_targets(targets, slot)

    if not results:
        return (
            jsonify(
                {
                    "ok": False,
                    "error": "Không lấy được dữ liệu thời tiết cho vị trí được yêu cầu",
                    "details": errors,
                    "provider_events": provider_events,
                    "requested_targets": list(targets),
                    "schedule": {
                        "update_slot": iso_local(slot),
                        "next_update": iso_local(next_weather_slot(slot)),
                        "checked_at": iso_local(checked_at),
                        "interval_minutes": WEATHER_INTERVAL_MINUTES,
                    },
                }
            ),
            503,
        )

    student_payload: dict[str, Any] | None = None
    if wants_student and user_lat is not None and user_lon is not None:
        student_payload = {
            "name": "Vị trí học sinh",
            "lat": round(user_lat, 6),
            "lon": round(user_lon, 6),
            "weather": results.get("student"),
            "from_cache": cache_flags.get("student", False),
            "error": errors.get("student"),
        }

    school_payload: dict[str, Any] | None = None
    if wants_school and school is not None and school_lat is not None and school_lon is not None:
        school_payload = {
            "id": school.get("id"),
            "name": school.get("short_name") or school.get("name"),
            "full_name": school.get("name"),
            "address": school.get("address"),
            "lat": school_lat,
            "lon": school_lon,
            "weather": results.get("school"),
            "from_cache": cache_flags.get("school", False),
            "error": errors.get("school"),
        }

    response = {
        "ok": not errors,
        "partial": bool(errors),
        "requested_targets": list(targets),
        "provider": {
            "name": " / ".join(sorted({
                str(item.get("provider", {}).get("name") or "Nguồn thời tiết")
                for item in results.values()
            })),
            "url": "https://open-meteo.com/",
            "type": "Dữ liệu mô hình thời tiết gần thời gian thực và dự báo",
            "note": "Dữ liệu mô hình Open-Meteo theo tọa độ GPS. Nếu nguồn tạm lỗi, chỉ hiển thị dữ liệu Open-Meteo cũ có ghi rõ thời gian hoặc thông báo chưa lấy được dữ liệu.",
        },
        "provider_events": provider_events,
        "schedule": {
            "update_slot": iso_local(slot),
            "next_update": iso_local(next_weather_slot(slot)),
            "checked_at": iso_local(checked_at),
            "interval_minutes": WEATHER_INTERVAL_MINUTES,
            "origin": "00:00",
        },
        "student": student_payload,
        "school": school_payload,
        "errors": errors,
    }
    return jsonify(response)


@app.post("/api/schools/<school_id>/coordinates")
def update_school_coordinates(school_id: str):
    """Lưu tọa độ sau khi người dùng kéo marker rà soát trên bản đồ."""
    payload = request.get_json(silent=True) or {}
    lat = payload.get("lat")
    lon = payload.get("lon")

    if not valid_number(lat) or not valid_number(lon):
        return jsonify({"ok": False, "error": "lat và lon phải là số hợp lệ"}), 400

    lat = float(lat)
    lon = float(lon)

    if not (10.70 <= lat <= 11.70 and 106.15 <= lon <= 107.10):
        return (
            jsonify(
                {
                    "ok": False,
                    "error": "Tọa độ nằm ngoài phạm vi kiểm tra Bình Dương mở rộng",
                }
            ),
            400,
        )

    data = load_database()
    school = find_school(data, school_id)
    if school is None:
        return jsonify({"ok": False, "error": "Không tìm thấy trường học"}), 404

    school["lat"] = round(lat, 7)
    school["lon"] = round(lon, 7)
    school["coordinate_quality"] = "user_verified"
    school["coordinate_note"] = "Đã được người dùng rà soát và lưu trong ứng dụng"

    counts = {
        "verified_osm": 0,
        "user_verified": 0,
        "estimated_from_address": 0,
    }
    for item in data["schools"]:
        quality = item.get("coordinate_quality")
        if quality in counts:
            counts[quality] += 1
    metadata = data.setdefault("metadata", {})
    metadata["verified_coordinates"] = counts["verified_osm"] + counts["user_verified"]
    metadata["user_verified_coordinates"] = counts["user_verified"]
    metadata["estimated_coordinates"] = counts["estimated_from_address"]

    save_database(data)
    return jsonify({"ok": True, "message": "Đã lưu tọa độ mới", "school": school})


@app.errorhandler(404)
def not_found(_error):
    if request.path.startswith("/api/"):
        return jsonify({"ok": False, "error": "API không tồn tại"}), 404
    return render_template("index.html"), 404


@app.errorhandler(Exception)
def handle_exception(error):
    app.logger.exception("Lỗi ứng dụng: %s", error)
    if request.path.startswith("/api/"):
        return jsonify({"ok": False, "error": "Lỗi máy chủ", "detail": str(error)}), 500
    return "Ứng dụng gặp lỗi. Hãy xem cửa sổ CMD để biết chi tiết.", 500


def choose_port(start: int = 5000, end: int = 5010) -> int:
    for port in range(start, end + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"Không tìm được cổng trống trong khoảng {start}-{end}")


def main() -> int:
    try:
        data = load_database()
    except Exception as error:
        print(f"\n[LỖI] Không thể đọc dữ liệu trường: {error}\n")
        return 1

    port = choose_port()
    address = f"http://127.0.0.1:{port}"
    print("\n" + "=" * 76)
    print("ĐƯỜNG ĐẾN TRƯỜNG AN TOÀN - V14.1 OPEN-METEO")
    print(f"Số trường: {len(data['schools'])}")
    print("Nguồn thời tiết duy nhất: Open-Meteo")
    print(f"Chu kỳ ứng dụng: {WEATHER_INTERVAL_MINUTES} phút, mốc gốc 00:00")
    print(f"Địa chỉ mở ứng dụng: {address}")
    print("Nhấn Ctrl+C để dừng máy chủ.")
    print("=" * 76 + "\n")

    if "--no-browser" not in sys.argv:
        threading.Timer(1.0, lambda: webbrowser.open(address)).start()

    app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False, threaded=True)
    return 0




# V9: dinh tuyen duong bo qua OpenStreetMap (Valhalla / OSRM).
# Ket qua la uoc tinh theo mang duong, KHONG bao gom ket xe truc tiep.
ROUTE_CACHE = {}
ROUTE_LOCK = threading.Lock()


def decode_polyline6(encoded):
    result = []
    index = lat = lon = 0
    while index < len(encoded):
        changes = []
        for _ in range(2):
            shift = value = 0
            while True:
                if index >= len(encoded):
                    raise ValueError("Du lieu tuyen duong khong hop le")
                bit = ord(encoded[index]) - 63
                index += 1
                value |= (bit & 31) << shift
                shift += 5
                if bit < 32:
                    break
            changes.append(~(value >> 1) if value & 1 else value >> 1)
        lat += changes[0]
        lon += changes[1]
        result.append([round(lat / 1e6, 6), round(lon / 1e6, 6)])
    return result


def request_route_valhalla(lat1, lon1, lat2, lon2, mode):
    costing = {"motorbike": "motorcycle", "car": "auto", "walk": "pedestrian", "bicycle": "bicycle"}[mode]
    payload = {"locations": [{"lat": lat1, "lon": lon1}, {"lat": lat2, "lon": lon2}],
               "costing": costing, "units": "kilometers", "language": "vi-VN"}
    url = "https://valhalla1.openstreetmap.de/route?" + urlencode({"json": json.dumps(payload, separators=(',', ':'))})
    req = Request(url, headers={"User-Agent": "BinhDuongSchoolRoute/8.0 (educational-app)",
                                "X-Client-Id": "binhduong-school-route-v8", "Accept": "application/json"})
    with urlopen(req, timeout=4.5) as response:
        data = json.load(response)
    trip = data.get("trip") or {}
    legs = trip.get("legs") or []
    summary = trip.get("summary") or {}
    if not legs or not legs[0].get("shape"):
        raise ValueError("Khong tim thay tuyen duong phu hop")
    points = []
    for leg in legs:
        section = decode_polyline6(leg["shape"])
        points.extend(section if not points else section[1:])
    if len(points) < 2:
        raise ValueError("Tuyen duong khong du diem")
    return {"ok": True, "distance_km": round(float(summary["length"]), 2),
            "duration_minutes": max(1, round(float(summary["time"]) / 60)),
            "coordinates": points, "provider": "Valhalla / OpenStreetMap",
            "mode": mode, "live_traffic": False}


def request_route_osrm(lat1, lon1, lat2, lon2, mode):
    # OSRM demo chi dung khi Valhalla loi; driving khong phan biet xe may va oto.
    if mode not in ("car", "motorbike"):
        raise ValueError("Khong co du phong cho che do nay")
    base = "https://router.project-osrm.org/route/v1/driving/"
    url = base + f"{lon1},{lat1};{lon2},{lat2}?overview=full&geometries=geojson"
    req = Request(url, headers={"User-Agent": "BinhDuongSchoolRoute/8.0 (educational-app)"})
    with urlopen(req, timeout=4.0) as response:
        data = json.load(response)
    routes = data.get("routes") or []
    if data.get("code") != "Ok" or not routes:
        raise ValueError("Khong tim thay duong di")
    route = routes[0]
    points = [[round(float(y), 6), round(float(x), 6)] for x, y in route["geometry"]["coordinates"]]
    return {"ok": True, "distance_km": round(route["distance"] / 1000, 2),
            "duration_minutes": max(1, round(route["duration"] / 60)),
            "coordinates": points, "provider": "OSRM / OpenStreetMap (du phong)",
            "mode": mode, "live_traffic": False,
            "note": "Du phong dung mo hinh xe oto, khong phan biet duong danh rieng cho xe may."}


@app.get("/api/route")
def api_route():
    try:
        mode = request.args.get("mode", "motorbike")
        direction = request.args.get("direction", "current_to_school").strip()
        school_id = request.args.get("school_id", "").strip()

        if mode not in ("motorbike", "car", "walk", "bicycle"):
            return jsonify({"ok": False, "error": "Phuong tien khong hop le"}), 400
        if direction not in ("current_to_school", "home_to_school", "school_to_home"):
            return jsonify({"ok": False, "error": "Huong hanh trinh khong hop le"}), 400

        school = find_school(load_database(), school_id)
        if not school:
            return jsonify({"ok": False, "error": "Vui long chon truong hop le"}), 400

        school_lat, school_lon = float(school["lat"]), float(school["lon"])
        if not all(map(math.isfinite, [school_lat, school_lon])):
            raise ValueError("Toa do truong khong hop le")

        school_name = school.get("short_name") or school.get("name")

        if direction == "current_to_school":
            start_lat = float(request.args["user_lat"])
            start_lon = float(request.args["user_lon"])
            end_lat, end_lon = school_lat, school_lon
            origin_name = "Vị trí hiện tại"
            destination_name = school_name
        else:
            home_lat = float(request.args["home_lat"])
            home_lon = float(request.args["home_lon"])
            if not (-90 <= home_lat <= 90 and -180 <= home_lon <= 180 and math.isfinite(home_lat) and math.isfinite(home_lon)):
                raise ValueError("Toa do nha da luu khong hop le")
            if direction == "home_to_school":
                start_lat, start_lon = home_lat, home_lon
                end_lat, end_lon = school_lat, school_lon
                origin_name = "Nhà đã lưu"
                destination_name = school_name
            else:
                start_lat, start_lon = school_lat, school_lon
                end_lat, end_lon = home_lat, home_lon
                origin_name = school_name
                destination_name = "Nhà đã lưu"

        if not (-90 <= start_lat <= 90 and -180 <= start_lon <= 180 and math.isfinite(start_lat) and math.isfinite(start_lon)):
            raise ValueError("Toa do diem xuat phat khong hop le")

        key = (
            round(start_lat, 4), round(start_lon, 4),
            round(end_lat, 4), round(end_lon, 4),
            mode, direction
        )
        with ROUTE_LOCK:
            cached = ROUTE_CACHE.get(key)
            if cached and time.time() - cached[0] < 900:
                return jsonify({**cached[1], "cached": True})

        failures = []
        result = None
        for provider in (request_route_valhalla, request_route_osrm):
            try:
                result = provider(start_lat, start_lon, end_lat, end_lon, mode)
                break
            except Exception as exc:
                failures.append(str(exc)[:120])

        if result is None:
            return jsonify({
                "ok": False,
                "error": "Chua lay duoc tuyen duong. Kiem tra Internet va thu lai.",
                "details": failures
            }), 503

        result["school_name"] = school_name
        result["school_id"] = school_id
        result["direction"] = direction
        result["origin_name"] = origin_name
        result["destination_name"] = destination_name

        with ROUTE_LOCK:
            if len(ROUTE_CACHE) > 200:
                ROUTE_CACHE.clear()
            ROUTE_CACHE[key] = (time.time(), result)
        return jsonify(result)
    except (ValueError, KeyError, TypeError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


if __name__ == "__main__":
    raise SystemExit(main())
