"""uvicorn 로그 설정 — 접근 로그에서 성공한 `/healthz` 만 뺀다.

compose healthcheck 가 10초마다 부르므로 그대로 두면 접근 로그의 대부분이 그 줄이다. 실패(503)는 남긴다 —
헬스가 나빠진 순간은 로그에서 보여야 한다. 나머지 설정은 uvicorn 기본값 그대로다.
"""

import copy
import logging

from uvicorn.config import LOGGING_CONFIG


class HealthzAccessFilter(logging.Filter):
    """uvicorn.access 레코드의 args 는 (client, method, path, http_version, status) 다."""

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if not isinstance(args, tuple) or len(args) < 5:
            return True
        path, status = str(args[2]), args[4]
        is_healthz = path == '/healthz' or path.startswith('/healthz?')
        return not (is_healthz and isinstance(status, int) and 200 <= status < 300)


def uvicorn_log_config() -> dict:
    config = copy.deepcopy(LOGGING_CONFIG)
    config.setdefault('filters', {})['no_healthz_ok'] = {'()': HealthzAccessFilter}
    config['handlers']['access'].setdefault('filters', []).append('no_healthz_ok')
    return config
