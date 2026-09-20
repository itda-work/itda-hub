"""키가 필요한 도구는 발급 가이드 한 절과 `.env.example` 항목을 함께 갖는다 (#2).

CONTRIBUTING 의 「새 도구는 카탈로그 선언 + 어댑터 + 테스트 + 도구 문서 한 장이 한 묶음」 중 **문서가
있는지**만 기계가 지킨다. 계약 테스트(`tests/test_catalog_adapter_contract.py`)와 파일을 나눈 이유는
관심이 다르기 때문이다 — 그쪽은 선언들의 대응이고, 여기는 저장소의 문서다.

**이 검사가 보장하지 않는 것**(사람이 지켜야 한다):

- 발급 절차의 **정확성**. 메뉴 이름을 잘못 적어도 앵커는 그대로 통과한다 — 「통계목록/KOSIS통합검색」
  오기가 그 반례였다. 실제로 한 번 발급해 보고 화면의 말 그대로 적는 수밖에 없다.
- 절의 **충분성**. 발급처·비용·유효기간·오류 표가 다 있는지는 보지 않는다.
- 키가 **필요 없는** 도구의 문서. 이 검사는 `credential != NONE` 인 공개 도구만 본다.

문구가 아니라 앵커의 존재만 본다 — 문서를 다듬을 때마다 테스트가 깨지면 안 된다.
"""

import re
from pathlib import Path

import pytest
from markdown_it import MarkdownIt

from apps.catalog.models import Tool

ROOT = Path(__file__).resolve().parent.parent
KEY_DOC = ROOT / 'docs' / 'tool-keys.md'
ENV_SAMPLE = ROOT / '.env.example'

# slug 규칙은 모델을 따른다 — `SlugField` 는 대문자·밑줄도 받는다(`apps/catalog/models.py`).
ANCHOR = re.compile(r'<!--\s*tool-key:\s*([-a-zA-Z0-9_]+)\s*-->')


def anchored_sections(text: str) -> dict[str, int]:
    """`<!-- tool-key: slug -->` 앵커 → 그 slug 가 앵커된 횟수.

    코드 예시(기여자 안내의 견본)는 세지 않고, 앵커 **바로 뒤에 실제 `##` 절**이 와야 한다 —
    앵커만 문서 아무 데나 흘려 두면 「절이 있다」 는 말이 거짓이 된다.

    판정을 **CommonMark 파서의 토큰**에 맡긴다. 코드 블록·제목의 경계를 손으로 재구현하면
    펜스 하나마다 반례가 나온다 — 백틱 홀짝은 `~~~` 예시에 뒤집히고, 문자와 길이를 추적해도
    ``` ```예시``` ``` 같은 인라인 코드를 여는 펜스로 보거나(실제 절이 코드로 묻힌다) 닫는 줄 뒤의
    NBSP 를 공백으로 보아 코드 안의 앵커를 세고, 목록 안 펜스는 아예 다르게 닫힌다. 여기서 관심은
    「렌더링된 문서에 그 절이 있는가」 하나뿐이라, 렌더러가 보는 것을 그대로 본다.
    """
    tokens = MarkdownIt('commonmark').parse(text)
    found: dict[str, int] = {}
    for i, token in enumerate(tokens):
        # 앵커는 HTML 주석이라 최상위 html_block 으로만 온다. 코드 블록 안이면 fence·code_block 이다.
        if token.type != 'html_block':
            continue
        m = ANCHOR.fullmatch(token.content.strip())
        if not m:
            continue
        following = tokens[i + 1] if i + 1 < len(tokens) else None
        assert following is not None and (following.type, following.tag) == (
            'heading_open',
            'h2',
        ), (
            f'{m.group(1)} 앵커 뒤에 절이 없다 — 앵커는 `## ` 절의 머리에만 둔다: '
            f'{following.type if following else "문서 끝"}'
        )
        found[m.group(1)] = found.get(m.group(1), 0) + 1
    return found


ANCHOR_CASES = [
    ('표준 문서', '<!-- tool-key: kosis -->\n## KOSIS (`kosis`)\n\n내용\n', {'kosis': 1}),
    ('틸드 펜스 예시', '~~~markdown\n<!-- tool-key: kosis -->\n## 예시\n~~~\n', {}),
    (
        '네 겹 백틱 안의 세 겹 줄',
        '````markdown\n```\n<!-- tool-key: kosis -->\n## 예시\n```\n````\n',
        {},
    ),
    (
        '네 칸 들여쓴 코드 뒤의 진짜 절',
        '    ```\n    예시\n\n<!-- tool-key: kosis -->\n## 가이드\n',
        {'kosis': 1},
    ),
    (
        '인라인 코드는 펜스가 아니다 — 뒤의 절은 살아 있다',
        '```예시```\n\n<!-- tool-key: kosis -->\n## 가이드\n',
        {'kosis': 1},
    ),
    (
        '인라인 코드 뒤 진짜 펜스 안의 예시',
        '```예시```\n\n```\n<!-- tool-key: kosis -->\n## 가이드\n```\n',
        {},
    ),
    (
        '닫는 줄 뒤 NBSP 는 펜스를 닫지 않는다',
        '~~~markdown\n~~~\u00a0\n<!-- tool-key: kosis -->\n## 예시\n~~~\n',
        {},
    ),
    (
        '목록 안 펜스 뒤의 진짜 절',
        '- ```\n  예시\n  ```\n\n<!-- tool-key: kosis -->\n## 가이드\n',
        {'kosis': 1},
    ),
    (
        '펜스를 닫은 뒤의 진짜 절',
        '```\n예시\n```\n\n<!-- tool-key: kosis -->\n## 가이드\n',
        {'kosis': 1},
    ),
    (
        '더 긴 닫기와 뒤따르는 공백·탭',
        '```\n예시\n```` \t\n\n<!-- tool-key: kosis -->\n## 가이드\n',
        {'kosis': 1},
    ),
]


@pytest.mark.parametrize('name,text,expected', ANCHOR_CASES, ids=[c[0] for c in ANCHOR_CASES])
def test_앵커_파서는_렌더링된_절만_센다(name, text, expected):
    """파서가 생긴 이상 파서도 잰다 — 예시가 절로 둔갑하면 문서 검사 전체가 거짓말이 된다.

    거짓 통과(코드 안 예시를 절로 셈)와 거짓 실패(진짜 절을 코드로 봄) 양쪽을 한 표에 둔다.
    """
    assert anchored_sections(text) == expected


def test_자격증명이_필요한_공개_도구는_발급_가이드_절이_있다(catalog):
    text = KEY_DOC.read_text(encoding='utf-8')
    anchors = anchored_sections(text)
    needs_key = Tool.objects.filter(enabled=True).exclude(credential=Tool.Credential.NONE)
    for tool in needs_key:
        assert anchors.get(tool.slug), (
            f'{tool.slug} 는 키가 필요한데 docs/tool-keys.md 에 절이 없다 — '
            f'`<!-- tool-key: {tool.slug} -->` 와 함께 발급 절차 한 절을 더한다'
        )
        assert anchors[tool.slug] == 1, f'{tool.slug} 앵커가 {anchors[tool.slug]} 번 나온다'


def test_공용_키를_받는_도구는_env_예시에_이름이_있다(catalog):
    """값이 아니라 **이름**이다. 샘플의 `SHARED_*` 는 비어 있어야 하고, 개인 키만 쓰는 배포도 정상이다."""
    sample = ENV_SAMPLE.read_text(encoding='utf-8')
    shared = Tool.objects.filter(enabled=True, credential=Tool.Credential.SHARED)
    for tool in shared:
        name = f'SHARED_{tool.setting_key}'
        assert re.search(rf'^{re.escape(name)}=', sample, re.MULTILINE), (
            f'{tool.slug} 가 관리자 공용 키를 받는데 .env.example 에 {name} 항목이 없다'
        )
