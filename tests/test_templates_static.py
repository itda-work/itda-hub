"""화면 규약(H-4) — 템플릿과 정적 파일을 읽어 검사한다(렌더 없이).

- 인라인 `<style>`·`style=` 속성, 인라인 `<script>`(src 없는 것), 인라인 이벤트 속성(`onclick=` 등)이 0.
  스킬.잇다 웹사이트의 M7-G 규약과 같다 — 스크립트는 static/js/ 의 파일로만 싣는다(CSP 'self' 로 충분하게).
- 문서는 `lang="ko"`, CSS 는 빌드 산출물 static/css/hub.css 하나.
- hub.css 가 템플릿에 새로 쓴 클래스를 담고 있는지는 CI 의 css 잡(빌드 후 diff 0)이 본다. 여기서는 존재와
  핵심 컴포넌트만 확인한다.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = sorted((ROOT / 'templates').rglob('*.html'))

INLINE_SCRIPT = re.compile(r'<script(?![^>]*\bsrc=)[^>]*>', re.IGNORECASE)
EVENT_ATTR = re.compile(r'<[^>]*\son[a-z]+\s*=', re.IGNORECASE)
STYLE_TAG = re.compile(r'<style\b', re.IGNORECASE)
STYLE_ATTR = re.compile(r'<[^>]*\sstyle\s*=', re.IGNORECASE)


def _strip_comments(text: str) -> str:
    """주석({# #}·{% comment %})은 규약을 설명하느라 태그 이름을 적는다 — 검사에서 뺀다."""
    text = re.sub(r'\{%\s*comment\s*%\}.*?\{%\s*endcomment\s*%\}', '', text, flags=re.DOTALL)
    return re.sub(r'\{#.*?#\}', '', text, flags=re.DOTALL)


def test_템플릿이_있다():
    assert len(TEMPLATES) >= 10


@pytest.mark.parametrize('path', TEMPLATES, ids=lambda p: str(p.relative_to(ROOT / 'templates')))
def test_인라인_스타일_스크립트_이벤트_속성이_없다(path):
    text = _strip_comments(path.read_text(encoding='utf-8'))
    assert not STYLE_TAG.search(text), '<style> 금지 — static/src/tailwind.css 로'
    assert not STYLE_ATTR.search(text), 'style= 속성 금지 — 유틸리티 클래스로'
    assert not INLINE_SCRIPT.search(text), '인라인 <script> 금지 — static/js/ 파일로'
    assert not EVENT_ATTR.search(text), 'on*= 이벤트 속성 금지 — addEventListener 로'


@pytest.mark.parametrize('name', ['base.html', '500.html'])
def test_문서는_한국어이고_빌드된_CSS_와_테마_가드를_싣는다(name):
    text = (ROOT / 'templates' / name).read_text(encoding='utf-8')
    assert '<html lang="ko">' in text
    assert "{% static 'css/hub.css' %}" in text
    assert "{% static 'js/theme-boot.js' %}" in text


def test_빌드된_CSS_와_정적_스크립트가_있다():
    css = (ROOT / 'static/css/hub.css').read_text(encoding='utf-8')
    for selector in ('.btn-primary', '.card', '.hub-form', '.dark\\:bg-slate-900'):
        assert selector in css, f'{selector} 가 hub.css 에 없다 — just css'
    assert css.count('\n') < 5, '커밋본은 minify 빌드다(just css)'
    for js in ('theme-boot.js', 'hub.js'):
        assert (ROOT / 'static/js' / js).is_file()


def test_테마_저장_키는_사이트와_같다():
    """html.dark + localStorage 'theme' — 스킬.잇다 웹사이트(SPEC-THEME-001)와 같은 계약."""
    for js in ('theme-boot.js', 'hub.js'):
        text = (ROOT / 'static/js' / js).read_text(encoding='utf-8')
        assert "'theme'" in text and "classList.toggle('dark'" in text


def test_정적_파일_찾기_경로에_hub_css_가_있다():
    """STATICFILES_DIRS — 이 경로가 빠지면 운영(collectstatic·whitenoise)에서 화면이 CSS 없이 뜬다."""
    from django.contrib.staticfiles import finders

    for path in ('css/hub.css', 'js/theme-boot.js', 'js/hub.js', 'img/logo.png'):
        assert finders.find(path), path
