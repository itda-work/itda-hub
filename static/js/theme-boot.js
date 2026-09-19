/*
 * <head> 부트 가드 — 첫 페인트 전에 <html> 의 dark 클래스를 맞춘다(테마 번쩍임 방지).
 *
 * 스킬.잇다 웹사이트(static/js/head-boot.js, M7-G)와 같은 정책: 저장 키 'theme', 값 'light' | 'dark',
 * 기본값 light, 시스템 선호(prefers-color-scheme)는 읽지 않는다. 같은 키라 두 사이트의 선택이 따로 논다
 * (origin 이 달라 localStorage 는 공유되지 않는다).
 *
 * **defer/async 를 붙이지 말고 <head> 에서 동기로 싣는다** — 늦게 돌면 가드가 아니다.
 * 인라인 <script> 를 쓰지 않는다(tests/test_templates_static.py 가 템플릿 전체를 검사한다).
 */
{
  let t = 'light'
  try {
    const s = localStorage.getItem('theme')
    if (s === 'light' || s === 'dark') t = s
  } catch (_) {}
  document.documentElement.classList.toggle('dark', t === 'dark')
}
