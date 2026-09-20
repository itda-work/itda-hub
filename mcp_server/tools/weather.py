"""Open-Meteo 현재 날씨. HTTPS GET, 키 불요, 응답은 원문 JSON 의 필요한 조각만."""

import httpx

from . import safe

URL = 'https://api.open-meteo.com/v1/forecast'
SOURCE = 'open-meteo.com'


def now(latitude: float, longitude: float) -> dict:
    params = {
        'latitude': latitude,
        'longitude': longitude,
        'current': 'temperature_2m,wind_speed_10m,weather_code',
        'daily': 'temperature_2m_max,temperature_2m_min,precipitation_probability_max',
        'forecast_days': 1,
        'timezone': 'Asia/Seoul',
    }
    r = httpx.get(URL, params=params, timeout=10.0)
    # 이 도구에는 키가 없지만 같은 규약을 쓴다 — 예외 문자열에 쿼리스트링을 싣지 않는다.
    safe.check(r, SOURCE)
    data = r.json()
    return {
        'source': SOURCE,
        'retrieved_at': data.get('current', {}).get('time'),
        'current': data.get('current'),
        'today': {
            k: (v[0] if isinstance(v, list) and v else None)
            for k, v in data.get('daily', {}).items()
        },
    }
