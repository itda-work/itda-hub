/*
 * 잇다 허브 화면 스크립트 — 정적 파일 하나(defer). 인라인 스크립트·on*= 속성은 쓰지 않는다.
 *
 * 1. 테마 토글(#theme-toggle) — 스킬.잇다 웹사이트 static/js/theme.js 와 같은 계약:
 *    저장 키 'theme', html.dark 클래스 하나, 기본값 light, 다른 탭의 변경(storage 이벤트)을 따른다.
 * 2. 복사 버튼([data-copy-target="<요소 id>"]) — 대상 요소의 textContent 를 클립보드로.
 *    도구함의 MCP 주소 카드가 쓴다. 스크립트는 화면에 이미 있는 값을 클립보드로만 옮긴다.
 */
;(function () {
  'use strict'

  var KEY = 'theme'
  var memory = null

  function getTheme() {
    if (memory) return memory
    try {
      var s = localStorage.getItem(KEY)
      if (s === 'light' || s === 'dark') return s
    } catch (_) {}
    return 'light'
  }

  function apply(theme) {
    document.documentElement.classList.toggle('dark', theme === 'dark')
    var btn = document.getElementById('theme-toggle')
    if (btn) btn.setAttribute('aria-pressed', theme === 'dark' ? 'true' : 'false')
  }

  function setTheme(theme) {
    memory = theme
    try {
      localStorage.setItem(KEY, theme)
    } catch (_) {
      /* 스토리지를 못 쓰는 환경 — memory 로만 동작한다. */
    }
    apply(theme)
  }

  window.addEventListener('storage', function (e) {
    if (e.key !== KEY) return
    memory = e.newValue === 'dark' ? 'dark' : 'light'
    apply(memory)
  })

  function copyText(text) {
    if (navigator.clipboard && window.isSecureContext) {
      return navigator.clipboard.writeText(text)
    }
    // http://localhost 가 아닌 평문 origin 등 Clipboard API 가 없는 곳 — 선택 후 execCommand.
    return new Promise(function (resolve, reject) {
      var ta = document.createElement('textarea')
      ta.value = text
      ta.setAttribute('readonly', '')
      ta.className = 'fixed -left-[9999px] top-0'
      document.body.appendChild(ta)
      ta.select()
      var ok = false
      try {
        ok = document.execCommand('copy')
      } catch (_) {}
      document.body.removeChild(ta)
      if (ok) resolve()
      else reject(new Error('copy failed'))
    })
  }

  function bindCopy(btn) {
    var label = btn.querySelector('[data-copy-label]') || btn
    var original = label.textContent
    var status = document.getElementById(btn.getAttribute('data-copy-status') || '')
    btn.addEventListener('click', function () {
      var target = document.getElementById(btn.getAttribute('data-copy-target'))
      if (!target) return
      copyText(target.textContent.trim()).then(
        function () {
          label.textContent = '복사됨'
          if (status) status.textContent = '클립보드에 복사했습니다.'
          window.setTimeout(function () {
            label.textContent = original
          }, 2000)
        },
        function () {
          if (status) status.textContent = '복사하지 못했습니다. 직접 선택해 복사하세요.'
        }
      )
    })
  }

  function init() {
    apply(getTheme())
    var toggle = document.getElementById('theme-toggle')
    if (toggle) {
      toggle.addEventListener('click', function () {
        setTheme(getTheme() === 'dark' ? 'light' : 'dark')
      })
    }
    var buttons = document.querySelectorAll('[data-copy-target]')
    for (var i = 0; i < buttons.length; i++) {
      buttons[i].hidden = false
      bindCopy(buttons[i])
    }
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init)
  else init()
})()
