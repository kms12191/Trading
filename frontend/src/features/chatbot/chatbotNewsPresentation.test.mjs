import assert from 'node:assert/strict'
import test from 'node:test'

import {
  buildNewsPresentation,
  normalizeNewsText,
} from './chatbotNewsPresentation.js'

test('normalizes chatbot news items from supported search sources', () => {
  const result = buildNewsPresentation({
    source: 'NAVER_API',
    items: [
      {
        title: '  삼성전자   반도체 투자 확대 ',
        ai_summary: '1. 삼성전자가 투자 계획을 공개했습니다.\n2. 생산라인 확대가 핵심입니다.\n3. 일정은 원문 확인이 필요합니다.',
        source: 'NAVER',
        market: 'DOMESTIC',
        symbol: '005930',
        company_name: '삼성전자',
        published_at: '2026-07-13T01:00:00Z',
        url: 'https://example.com/news',
        raw_payload: { query_category: 'stock_news' },
      },
    ],
  })

  assert.equal(result.items.length, 1)
  assert.equal(result.items[0].title, '삼성전자 반도체 투자 확대')
  assert.equal(result.items[0].market, '국내')
  assert.equal(result.items[0].category, '주식')
  assert.equal(result.items[0].summaryLines.length, 3)
  assert.equal(result.items[0].url, 'https://example.com/news')
})

test('ignores unsupported tool result sources', () => {
  const result = buildNewsPresentation({
    source: 'DISCLOSURE_DB',
    items: [{ title: '공시' }],
  })

  assert.deepEqual(result, { items: [] })
})

test('normalizes news items from combined news and disclosure search results', () => {
  const result = buildNewsPresentation({
    source: 'NEWS_DISCLOSURE_COMBINED',
    news: {
      source: 'NAVER_API',
      items: [
        {
          title: '삼성전자 최근 뉴스',
          ai_summary: '1. 반도체 투자 뉴스입니다.',
          source: 'NAVER',
          market: 'DOMESTIC',
          company_name: '삼성전자',
          raw_payload: { query_category: 'stock_news' },
        },
      ],
    },
    disclosure: {
      source: 'DISCLOSURE_DB',
      items: [{ report_nm: '공시' }],
    },
  })

  assert.equal(result.items.length, 1)
  assert.equal(result.items[0].title, '삼성전자 최근 뉴스')
  assert.equal(result.items[0].market, '국내')
})

test('normalizes repeated news whitespace', () => {
  assert.equal(normalizeNewsText('삼성전자\n\n  최신\t뉴스'), '삼성전자 최신 뉴스')
})

test('removes empty numbered placeholder lines from news summaries', () => {
  const result = buildNewsPresentation({
    source: 'NAVER_API',
    items: [
      {
        title: '하이닉스 최근 뉴스',
        ai_summary: '1. 삼성전자와 SK하이닉스가 시가총액 상위권을 주도했습니다. 2. 코스피 순환매가 관전 포인트입니다. 3. 메모리 반도체 설비투자가 증가했습니다.\n2. -\n3. -',
        source: 'NAVER',
        market: 'DOMESTIC',
        company_name: '하이닉스',
      },
    ],
  })

  assert.deepEqual(result.items[0].summaryLines, [
    '1. 삼성전자와 SK하이닉스가 시가총액 상위권을 주도했습니다. 2. 코스피 순환매가 관전 포인트입니다. 3. 메모리 반도체 설비투자가 증가했습니다.',
  ])
})

test('falls back to article summary when cached AI summary is incomplete', () => {
  const result = buildNewsPresentation({
    source: 'NAVER_API',
    items: [
      {
        title: '삼성전자 최근 뉴스',
        ai_summary: '1. 단계를 구축하고 있으며,\n2. -\n3. -',
        summary: '정부가 반도체 메가산단 구축을 추진한다는 기사입니다.',
        source: 'NAVER',
        market: 'DOMESTIC',
        company_name: '삼성전자',
      },
    ],
  })

  assert.deepEqual(result.items[0].summaryLines, ['정부가 반도체 메가산단 구축을 추진한다는 기사입니다.'])
})
