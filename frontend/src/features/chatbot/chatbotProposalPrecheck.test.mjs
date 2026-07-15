import assert from 'node:assert/strict'
import test from 'node:test'

import {
  buildProposalPrecheckSummary,
  isChatbotApprovalProposal,
  isProposalApprovalBlocked,
} from './chatbotProposalPrecheck.js'

test('수동 주문 멱등성 레코드는 챗봇 승인 카드에서 제외한다', () => {
  assert.equal(isChatbotApprovalProposal({
    status: 'PENDING',
    raw_order_payload: { source: 'MANUAL_ORDER' },
  }), false)
  assert.equal(isChatbotApprovalProposal({
    status: 'PENDING',
    raw_order_payload: { idempotency_fingerprint: 'manual-order-fingerprint' },
  }), false)
  assert.equal(isChatbotApprovalProposal({
    status: 'PENDING',
    raw_order_payload: {
      source: 'CHATBOT_ORDER_PARSER',
      precheck_status: 'OK',
      precheck: {
        reference_price: 108.5,
        estimated_amount_krw: 15190,
      },
    },
  }), true)
  assert.equal(isChatbotApprovalProposal({
    status: 'PENDING',
    raw_order_payload: {
      order: {},
      post_order_status_check: {},
    },
  }), false)
})

test('builds compact precheck summary from raw_order_payload', () => {
  const summary = buildProposalPrecheckSummary({
    raw_order_payload: {
      precheck_status: 'OK',
      precheck: {
        estimated_amount_krw: 70000,
        available_cash: 200000,
        insufficient_cash: false,
        insufficient_holding: false,
        is_market_closed: false,
        warnings: [],
      },
    },
  })

  assert.equal(summary.status, 'OK')
  assert.equal(summary.estimatedAmountText, '70,000원')
  assert.equal(summary.availableCashText, '200,000원')
  assert.deepEqual(summary.warnings, [])
})

test('includes risk warnings for blocked precheck conditions', () => {
  const summary = buildProposalPrecheckSummary({
    raw_order_payload: {
      precheck_status: 'OK',
      precheck: {
        estimated_amount_krw: 120000,
        insufficient_cash: true,
        insufficient_holding: true,
        is_market_closed: true,
        market_status_message: '현재는 장외 시간입니다.',
        warnings: ['예수금 대비 주문 예정 금액이 큽니다.'],
      },
    },
  })

  assert.equal(summary.status, 'WARNING')
  assert.equal(summary.estimatedAmountText, '120,000원')
  assert.deepEqual(summary.warnings, [
    '예수금이 부족할 수 있습니다.',
    '보유 수량보다 많은 매도 주문입니다.',
    '현재는 장외 시간입니다.',
    '예수금 대비 주문 예정 금액이 큽니다.',
  ])
})

test('blocks approval when precheck status is missing or a blocker is true', () => {
  assert.equal(isProposalApprovalBlocked({ raw_order_payload: {} }), true)
  assert.equal(isProposalApprovalBlocked({
    raw_order_payload: {
      precheck_status: 'OK',
      precheck: { insufficient_permission: true },
    },
  }), true)
  assert.equal(isProposalApprovalBlocked({
    raw_order_payload: {
      precheck_status: 'OK',
      precheck: { balance_check_failed: true },
    },
  }), true)
})

test('advisory warnings alone do not block a validated proposal', () => {
  assert.equal(isProposalApprovalBlocked({
    raw_order_payload: {
      precheck_status: 'OK',
      precheck: {
        warnings: ['가격 변동 가능성이 있습니다.'],
        insufficient_cash: false,
        insufficient_holding: false,
        is_market_closed: false,
        insufficient_permission: false,
        futures_real_blocked: false,
        exceeds_real_order_limit: false,
      },
    },
  }), false)
})
