"""`python -m mcp_server` — MCP 프로세스 진입점. Django 는 ORM 으로만 쓴다(웹 서버 아님)."""

import os

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hub.settings')
django.setup()

from mcp_server.logs import uvicorn_log_config
from mcp_server.server import build

if __name__ == '__main__':
    bind = os.environ.get('HUB_MCP_BIND', '127.0.0.1:8080')
    host, _, port = bind.rpartition(':')
    build().run(
        transport='http',
        host=host or '127.0.0.1',
        port=int(port),
        path='/mcp',
        uvicorn_config={'log_config': uvicorn_log_config()},
    )
