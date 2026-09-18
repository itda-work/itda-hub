# 배포

## 전제

- 공개 HTTPS 도메인 하나(`HUB_BASE_URL`). Claude 는 Anthropic 아웃바운드 대역 `160.79.104.0/21` 에서 허브와 인가 서버 양쪽에 닿아야 한다. WAF 가 이 대역을 막으면 연결이 실패한다.
- 프로세스 둘: Django(web) 와 MCP(`python -m mcp_server`). 같은 DB 를 본다. v1 은 SQLite(WAL) 로 충분하다.
  - WAL 은 설정의 `init_command` 가 연결마다 건다(`journal_mode=WAL`, `synchronous=NORMAL`), 잠금 대기는 `timeout=20`(초), 쓰기 트랜잭션은 `IMMEDIATE`.
  - 전제: DB 파일과 `-wal`·`-shm` 파일이 **같은 로컬 볼륨**에 있고 두 프로세스가 **같은 호스트**에서 돈다. NFS·SMB 같은 네트워크 파일시스템 금지.
  - 백업은 파일 복사가 아니라 `sqlite3 /data/hub.sqlite3 ".backup /backup/hub-$(date +%F).sqlite3"` 또는 `VACUUM INTO`. 쓰기 중 파일 복사는 깨진 사본을 만든다.
- OAuth 엔드포인트는 10초 안에 답해야 한다.

## 절차

1. `.env` 를 서버에만 둔다(`.env.example` 참고). `HUB_SETTINGS_ENCRYPTION_KEY` 는 한 번 만들면 바꾸지 않는다. 바꾸면 저장된 설정 값을 전부 풀 수 없다.
2. `python manage.py migrate && python manage.py seed_catalog`
3. introspection 용 DOT Application 을 하나 만든다(confidential · client_credentials). 그 ID·시크릿을 `HUB_INTROSPECTION_CLIENT_ID/SECRET` 에 둔다. MCP 프로세스는 이것으로 `/o/introspect/` 를 부른다.
4. Google OAuth 클라이언트를 만들고 리디렉션 URI 에 `${HUB_BASE_URL}/accounts/google/login/callback/` 을 등록한다.
5. `deploy/compose.yml` 로 web·mcp 를 띄우고 리버스 프록시에서 `/mcp` 는 `mcp:8080`, 나머지는 `web:8000` 으로 보낸다. `/.well-known/*` 는 Django 로 간다.
6. 스모크: `curl -sS ${HUB_BASE_URL}/.well-known/oauth-authorization-server | jq .issuer` 가 `HUB_BASE_URL` 과 같아야 하고, `curl -sS ${HUB_BASE_URL}/.well-known/oauth-protected-resource/mcp | jq .resource` 가 `HUB_MCP_URL` 과 같아야 한다.

## 기수 리셋

교육 기수가 끝나면 `ToolboxEntry`·`ToolSetting`·`ToolCall` 을 비우고 관리자 공용 키를 재발급한다. 사용자 계정은 남겨도 되지만 요청이 있으면 삭제한다.
