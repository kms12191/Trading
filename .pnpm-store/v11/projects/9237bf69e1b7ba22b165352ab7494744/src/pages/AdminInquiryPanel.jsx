import { useState } from 'react'

// 트레이딩 봇 관련 가상 문의 목록 데이터
const initialInquiries = [
  {
    id: 'INQ-1004',
    userEmail: 'user1@example.com',
    title: '코인원 API 출금주소록 등록 에러가 계속 납니다.',
    category: 'API 연동',
    content: '코인원 API를 통해서 바이낸스로 리플 출금을 진행하려고 하는데, "API 출금주소록 등록이 필요합니다"라는 에러 메시지가 뜹니다. 코인원 사이트에서 출금 주소와 데스티네이션 태그까지 다 등록했고 OTP 인증도 완료했는데 왜 이런 에러가 뜨는지 모르겠습니다. 백엔드에서 주소 매핑이 잘못된 건가요?',
    status: 'PENDING',
    createdAt: '2026-07-07T10:15:30Z',
    reply: '',
  },
  {
    id: 'INQ-1003',
    userEmail: 'investor_k@naver.com',
    title: 'Toss증권 1회 실거래 주문 한도 상향 요청',
    category: '주문 실행',
    content: '현재 시스템의 1회 주문 한도가 10만원으로 설정되어 있는 것 같습니다. 투자 금액을 조금 더 크게 굴리고 싶은데, 혹시 이 한도를 100만원 정도로 상향 조절할 수 있는 설정이나 옵션이 있을까요? 챗봇 제안 승인 단계에서 한도 제한으로 주문이 생성되지 않고 제안으로 우회되는 상태입니다.',
    status: 'PENDING',
    createdAt: '2026-07-06T18:40:00Z',
    reply: '',
  },
  {
    id: 'INQ-1002',
    userEmail: 'algo_trader@gmail.com',
    title: 'LightGBM v8 모델의 Stochastic/OBV 피처 산출 주기 문의',
    category: 'ML 모델',
    content: 'v8 모델에서 Stochastic Oscillator와 OBV 기술지표 피처가 강화되었다고 설명에 적혀있던데, 이 피처들을 백엔드 스케줄러가 몇 분 단위로 업데이트하여 예측 신호에 반영하는지 알고 싶습니다. 30분봉 기준인지 1시간봉 기준인지 궁금하네요.',
    status: 'COMPLETED',
    createdAt: '2026-07-06T11:22:15Z',
    reply: '안녕하세요. AI 운영팀입니다. LightGBM v8 모델의 예측 피처는 30분 단위(30m 캔들)로 백엔드 ml_scheduler가 기동되어 데이터를 수집 및 지표를 산출하고 있습니다. OBV와 Stochastic의 경우 30분봉 종가 마감 시점에 동기화되어 활성 신호 판단에 활용됩니다. 추가 문의사항이 있으시면 언제든 남겨주세요. 감사합니다.',
    repliedAt: '2026-07-06T14:05:00Z',
  },
  {
    id: 'INQ-1001',
    userEmail: 'korean_whale@daum.net',
    title: '바이낸스 USD-M 선물 자동매도 숏 포지션 지원 여부',
    category: '자동 매매',
    content: '조건식 자동/반자동 매도 설정 시 바이낸스 선물의 롱 포지션 청산(reduceOnly SELL)만 지원하는지 여쭤봅니다. 숏 포지션으로 진입해 있는 경우, 반대 매수로 청산하는 자동화 로직도 현재 릴리즈 버전에 포함되어 있는 상태인가요?',
    status: 'COMPLETED',
    createdAt: '2026-07-05T09:05:10Z',
    reply: '안녕하세요. 문의하신 사항에 답변드립니다. 현재 Phase 4 조건식 엔진에서는 롱 포지션 청산(BOTH 마진 모드 하에서 reduceOnly SELL 주문 실행)을 우선적으로 처리하도록 설계되어 있습니다. 숏 포지션 청산(매수 청산)의 경우, 현재 로드맵상 Phase 4.5 확장 기능으로 분류되어 있어 다음 패치 시점에 숏 포지션 청산 옵션이 활성화될 예정입니다. 이용에 참고를 부탁드립니다.',
    repliedAt: '2026-07-05T13:45:00Z',
  },
]

export default function AdminInquiryPanel() {
  const [inquiries, setInquiries] = useState(initialInquiries)
  const [filter, setFilter] = useState('ALL') // ALL, PENDING, COMPLETED
  const [selectedInquiry, setSelectedInquiry] = useState(null)
  const [replyText, setReplyText] = useState('')

  const filteredInquiries = inquiries.filter((item) => {
    if (filter === 'ALL') return true
    return item.status === filter
  })

  const handleSelectInquiry = (inquiry) => {
    setSelectedInquiry(inquiry)
    setReplyText(inquiry.reply || '')
  }

  const handleSendReply = () => {
    if (!selectedInquiry) return
    if (!replyText.trim()) {
      alert('답변 내용을 입력해 주세요.')
      return
    }

    setInquiries((prev) =>
      prev.map((item) => {
        if (item.id === selectedInquiry.id) {
          return {
            ...item,
            status: 'COMPLETED',
            reply: replyText,
            repliedAt: new Date().toISOString(),
          }
        }
        return item
      })
    )

    // 상태 동기화
    setSelectedInquiry((prev) => ({
      ...prev,
      status: 'COMPLETED',
      reply: replyText,
      repliedAt: new Date().toISOString(),
    }))

    alert('답변 등록이 완료되었습니다.')
  }

  const formatDate = (isoString) => {
    if (!isoString) return '-'
    const date = new Date(isoString)
    return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(
      date.getDate()
    ).padStart(2, '0')} ${String(date.getHours()).padStart(2, '0')}:${String(
      date.getMinutes()
    ).padStart(2, '0')}`
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[1.2fr_0.8fr]">
      {/* 문의 목록 */}
      <section className="rounded-lg border border-slate-700/80 bg-slate-surface p-5">
        <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-ai-cyan">User Inquiries</p>
            <h2 className="mt-1 text-xl font-bold text-white">사용자 문의 및 답변 관리</h2>
            <p className="mt-1 text-xs text-slate-400">
              트레이딩 시스템 관련 오류 보고 및 기능 요청 문의에 대한 답변을 관리합니다.
            </p>
          </div>
          {/* 필터 탭 */}
          <div className="flex rounded-lg border border-slate-700 bg-[#0f172a] p-1 self-start sm:self-center">
            {['ALL', 'PENDING', 'COMPLETED'].map((type) => (
              <button
                key={type}
                type="button"
                onClick={() => setFilter(type)}
                className={`rounded-md px-3 py-1.5 text-xs font-bold transition ${
                  filter === type ? 'bg-ai-cyan text-[#07111f]' : 'text-slate-400 hover:text-white'
                }`}
              >
                {type === 'ALL' ? '전체' : type === 'PENDING' ? '답변 대기' : '답변 완료'}
              </button>
            ))}
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse text-xs">
            <thead>
              <tr className="border-b border-slate-800 text-slate-500 font-bold uppercase tracking-wider">
                <th className="pb-3 pl-2">문의 ID</th>
                <th className="pb-3">카테고리</th>
                <th className="pb-3">제목</th>
                <th className="pb-3">작성자</th>
                <th className="pb-3">등록일시</th>
                <th className="pb-3 pr-2 text-right">상태</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/50">
              {filteredInquiries.length === 0 ? (
                <tr>
                  <td colSpan={6} className="py-8 text-center text-slate-500">
                    조회된 문의 내역이 없습니다.
                  </td>
                </tr>
              ) : (
                filteredInquiries.map((inquiry) => (
                  <tr
                    key={inquiry.id}
                    onClick={() => handleSelectInquiry(inquiry)}
                    className={`cursor-pointer hover:bg-slate-800/40 transition-colors ${
                      selectedInquiry?.id === inquiry.id ? 'bg-slate-800/60' : ''
                    }`}
                  >
                    <td className="py-4 pl-2 font-mono font-bold text-slate-400">{inquiry.id}</td>
                    <td className="py-4 font-bold">
                      <span className="rounded border border-slate-700/60 bg-[#0f172a] px-2 py-0.5 text-[10px] text-slate-300">
                        {inquiry.category}
                      </span>
                    </td>
                    <td className="py-4 font-bold text-white max-w-[200px] truncate" title={inquiry.title}>
                      {inquiry.title}
                    </td>
                    <td className="py-4 text-slate-400 font-mono">{inquiry.userEmail}</td>
                    <td className="py-4 text-slate-400 font-mono">{formatDate(inquiry.createdAt)}</td>
                    <td className="py-4 pr-2 text-right">
                      <span
                        className={`rounded px-2 py-0.5 text-[10px] font-bold ${
                          inquiry.status === 'COMPLETED'
                            ? 'bg-emerald-950/40 border border-emerald-500/30 text-emerald-300'
                            : 'bg-amber-950/40 border border-amber-500/30 text-amber-300'
                        }`}
                      >
                        {inquiry.status === 'COMPLETED' ? '답변 완료' : '답변 대기'}
                      </span>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>

      {/* 상세 보기 및 답변 처리 */}
      <section className="rounded-lg border border-slate-700/80 bg-slate-surface p-5">
        <h3 className="text-sm font-bold uppercase tracking-wider text-white mb-4">문의 상세 정보</h3>

        {selectedInquiry ? (
          <div className="space-y-4">
            <div className="rounded-lg border border-slate-800 bg-[#0f172a] p-4">
              <div className="flex items-center justify-between gap-3">
                <span className="text-[10px] font-bold text-ai-cyan font-mono">{selectedInquiry.id}</span>
                <span
                  className={`rounded px-2 py-0.5 text-[9px] font-bold ${
                    selectedInquiry.status === 'COMPLETED'
                      ? 'bg-emerald-950/40 border border-emerald-500/30 text-emerald-300'
                      : 'bg-amber-950/40 border border-amber-500/30 text-amber-300'
                  }`}
                >
                  {selectedInquiry.status === 'COMPLETED' ? '답변 완료' : '답변 대기'}
                </span>
              </div>
              <h4 className="mt-2 text-sm font-bold text-white leading-relaxed">{selectedInquiry.title}</h4>
              <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-slate-500">
                <p>
                  카테고리: <span className="text-slate-400 font-bold">{selectedInquiry.category}</span>
                </p>
                <p>
                  작성자: <span className="text-slate-400 font-mono">{selectedInquiry.userEmail}</span>
                </p>
                <p>
                  등록: <span className="text-slate-400 font-mono">{formatDate(selectedInquiry.createdAt)}</span>
                </p>
              </div>
            </div>

            <div className="rounded-lg border border-slate-800 bg-[#0f172a] p-4">
              <h5 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-2">문의 내용</h5>
              <p className="text-xs leading-relaxed text-slate-200 whitespace-pre-wrap">
                {selectedInquiry.content}
              </p>
            </div>

            {selectedInquiry.status === 'COMPLETED' && (
              <div className="rounded-lg border border-emerald-500/20 bg-emerald-950/10 p-4">
                <div className="flex items-center justify-between mb-2">
                  <h5 className="text-xs font-bold text-emerald-400 uppercase tracking-wider">등록된 답변</h5>
                  <span className="text-[10px] text-slate-500 font-mono">
                    {formatDate(selectedInquiry.repliedAt)}
                  </span>
                </div>
                <p className="text-xs leading-relaxed text-slate-300 whitespace-pre-wrap">
                  {selectedInquiry.reply}
                </p>
              </div>
            )}

            <div className="rounded-lg border border-slate-800 bg-[#0f172a] p-4 space-y-3">
              <h5 className="text-xs font-bold text-slate-400 uppercase tracking-wider">
                {selectedInquiry.status === 'COMPLETED' ? '답변 수정하기' : '답변 작성하기'}
              </h5>
              <textarea
                value={replyText}
                onChange={(e) => setReplyText(e.target.value)}
                placeholder="사용자 문의에 대한 공식 답변 내용을 작성해 주세요..."
                className="w-full h-32 rounded border border-slate-700 bg-obsidian-bg p-3 text-xs text-white outline-none transition focus:border-ai-cyan resize-none leading-relaxed"
              />
              <button
                type="button"
                onClick={handleSendReply}
                className="w-full rounded bg-ai-cyan py-2.5 text-xs font-bold text-[#07111f] transition hover:bg-ai-cyan/80"
              >
                {selectedInquiry.status === 'COMPLETED' ? '답변 수정 저장' : '답변 등록하기'}
              </button>
            </div>
          </div>
        ) : (
          <div className="rounded-lg border border-slate-800 bg-[#0f172a] p-8 text-center text-xs text-slate-500">
            좌측 목록에서 문의 내역을 선택하면 상세 내용 확인 및 답변 작성이 가능합니다.
          </div>
        )}
      </section>
    </div>
  )
}
