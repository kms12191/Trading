import { fireEvent, render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import AdminAiFundDashboard from '../pages/AdminAiFundDashboard'

describe('AdminAiFundDashboard Component', () => {
  it('renders Admin AI Fund Emergency Kill-Switch button', () => {
    render(<AdminAiFundDashboard userId="test-admin-id" />)
    const killSwitchBtn = screen.getByRole('button', { name: /Emergency Stop/i })
    expect(killSwitchBtn).toBeInTheDocument()
  })

  it('renders the stock auto-selection controls in the existing dashboard', () => {
    render(<AdminAiFundDashboard userId="test-admin-id" />)
    expect(screen.getByRole('heading', { name: '토스 주식 자동선별' })).toBeInTheDocument()
    expect(screen.getByText('국내·미국')).toBeInTheDocument()
  })

  it('opens the operating guide from the dashboard header', () => {
    render(<AdminAiFundDashboard userId="test-admin-id" />)

    fireEvent.click(screen.getByRole('button', { name: '가이드 보기' }))

    expect(screen.getByRole('dialog', { name: 'AI 위탁 자동투자 사용 가이드' })).toBeInTheDocument()
    expect(screen.getByText('1. 자동선별 거래소와 자금을 정합니다.')).toBeInTheDocument()
  })
})
