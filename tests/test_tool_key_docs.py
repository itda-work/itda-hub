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

from apps.catalog.models import Tool

ROOT = Path(__file__).resolve().parent.parent
KEY_DOC = ROOT / 'docs' / 'tool-keys.md'
ENV_SAMPLE = ROOT / '.env.example'

# slug 규칙은 모델을 따른다 — `SlugField` 는 대문자·밑줄도 받는다(`apps/catalog/models.py`).
ANCHOR = re.compile(r'^ {0,3}<!--\s*tool-key:\s*([-a-zA-Z0-9_]+)\s*-->\s*$')
HEADING = re.compile(r'^ {0,3}##[ \t]')
# 펜스는 백틱·틸드 셋 이상이고 들여쓰기는 세 칸까지다(네 칸부터는 펜스가 아니라 들여쓴 코드).
FENCE = re.compile(r'^ {0,3}(`{3,}|~{3,})(.*)$')


def anchored_sections(text: str) -> dict[str, int]:
    """`<!-- tool-key: slug -->` 앵커 → 그 slug 가 앵커된 횟수.

    코드 펜스 안의 예시(기여자 안내의 견본)는 세지 않는다. 앵커 **바로 뒤에 실제 `##` 절**이 와야
    한다 — 앵커만 문서 아무 데나 흘려 두면 「절이 있다」 는 말이 거짓이 된다.

    펜스는 열고 닫는 짝을 CommonMark 대로 본다. 여는 줄의 **문자와 길이**를 기억하고, 같은 문자로
    그만큼 이상 길고 정보 문자열이 없는 줄에서만 닫는다. 백틱만 홀짝으로 세면 `~~~` 예시나 네 겹
    백틱 안의 세 겹 줄이 문서를 뒤집어, 예시뿐인 문서가 「절이 있다」 로 통과한다.
    """
    found: dict[str, int] = {}
    lines = text.splitlines()
    open_fence: tuple[str, int] | None = None
    for i, line in enumerate(lines):
        fence = FENCE.match(line)
        if fence:
            marker, info = fence.group(1), fence.group(2)
            char, length = marker[0], len(marker)
            if open_fence is None:
                open_fence = (char, length)
                continue
            if char == open_fence[0] and length >= open_fence[1] and not info.strip():
                open_fence = None
            continue
        if open_fence is not None:
            continue
        m = ANCHOR.match(line)
        if not m:
            continue
        following = next((x for x in lines[i + 1 :] if x.strip()), '')
        assert HEADING.match(following), (
            f'{m.group(1)} 앵커 뒤에 절이 없다 — 앵커는 절의 머리에만 둔다: {following[:60]!r}'
        )
        found[m.group(1)] = found.get(m.group(1), 0) + 1
    return found


def test_앵커_파서는_코드_예시를_절로_세지_않는다():
    """파서가 생긴 이상 파서도 잰다 — 예시가 절로 둔갑하면 문서 검사 전체가 거짓말이 된다."""
    예시뿐인_문서 = '~~~markdown\n<!-- tool-key: kosis -->\n## 예시\n~~~\n'
    assert anchored_sections(예시뿐인_문서) == {}, '틸드 펜스 안의 예시를 절로 셌다'

    네겹_백틱 = '````markdown\n```\n<!-- tool-key: kosis -->\n## 예시\n```\n````\n'
    assert anchored_sections(네겹_백틱) == {}, '네 겹 백틱 안의 세 겹 줄에 펜스가 열렸다'

    들여쓴_코드 = '    ```\n    예시\n\n<!-- tool-key: kosis -->\n## 진짜 가이드\n'
    assert anchored_sections(들여쓴_코드) == {'kosis': 1}, '네 칸 들여쓴 줄을 펜스로 봤다'

    표준_문서 = '<!-- tool-key: kosis -->\n## KOSIS (`kosis`)\n\n내용\n'
    assert anchored_sections(표준_문서) == {'kosis': 1}


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
