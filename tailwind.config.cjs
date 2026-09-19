/*
 * Tailwind 설정 — 스킬.잇다 웹사이트(tailwind.config.cjs)의 토큰을 그대로 가져온다.
 *   - 색: 사이트처럼 Tailwind 기본 팔레트를 쓴다(gray·slate 바탕, blue 강조, indigo 로고). 따로 늘리지 않는다.
 *   - 폰트: Pretendard(CDN, templates/base.html) → system-ui
 *   - 다크 모드: html.dark 클래스(static/js/theme-boot.js · theme.js, 저장 키 'theme')
 *   - typography: 사이트의 prose 색·간격(허브는 긴 본문이 없어 안내 문단에만 쓴다)
 *   - 모듈 형식: CJS (package.json 이 ESM 이라 .cjs 확장자 필수)
 */
const typography = require('@tailwindcss/typography')

/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./templates/**/*.html', './apps/**/*.py', './static/js/**/*.js'],
  darkMode: 'class',
  theme: {
    extend: {
      fontFamily: {
        sans: ['Pretendard', 'system-ui', 'sans-serif'],
      },
      typography: {
        DEFAULT: {
          css: {
            maxWidth: '72ch',
            lineHeight: '1.8',
            '--tw-prose-body': '#1f2937',
            '--tw-prose-headings': '#111827',
            '--tw-prose-lead': '#374151',
            '--tw-prose-links': '#2563eb',
            '--tw-prose-bold': '#111827',
            '--tw-prose-counters': '#6b7280',
            '--tw-prose-bullets': '#9ca3af',
            '--tw-prose-hr': '#e5e7eb',
            '--tw-prose-quotes': '#111827',
            '--tw-prose-quote-borders': '#2563eb',
            '--tw-prose-captions': '#6b7280',
            '--tw-prose-code': '#1d4ed8',
            '--tw-prose-pre-code': '#e2e8f0',
            '--tw-prose-pre-bg': '#1e293b',
            '--tw-prose-th-borders': '#d1d5db',
            '--tw-prose-td-borders': '#e5e7eb',
          },
        },
        invert: {
          css: {
            '--tw-prose-body': '#e2e8f0',
            '--tw-prose-headings': '#f1f5f9',
            '--tw-prose-lead': '#94a3b8',
            '--tw-prose-links': '#60a5fa',
            '--tw-prose-bold': '#f1f5f9',
            '--tw-prose-counters': '#94a3b8',
            '--tw-prose-bullets': '#64748b',
            '--tw-prose-hr': '#334155',
            '--tw-prose-quotes': '#f1f5f9',
            '--tw-prose-quote-borders': '#2563eb',
            '--tw-prose-captions': '#94a3b8',
            '--tw-prose-code': '#93c5fd',
            '--tw-prose-pre-code': '#e2e8f0',
            '--tw-prose-pre-bg': '#0f172a',
            '--tw-prose-th-borders': '#334155',
            '--tw-prose-td-borders': '#1e293b',
          },
        },
      },
    },
  },
  plugins: [typography],
}
