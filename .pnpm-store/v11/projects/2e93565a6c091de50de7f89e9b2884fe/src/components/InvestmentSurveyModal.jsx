import { useState } from 'react'
import { supabase } from '../supabaseClient'

const SURVEY_QUESTIONS = [
  {
    id: 'q1',
    question: '주식·ETF·코인 등 투자 경험은?',
    options: [
      { text: '없음', score: 1 },
      { text: '1년 미만', score: 2 },
      { text: '1~3년', score: 3 },
      { text: '3~5년', score: 4 },
      { text: '5년 이상', score: 5 }
    ]
  },
  {
    id: 'q2',
    question: '투자하는 가장 큰 이유는?',
    options: [
      { text: '원금 보존', score: 1 },
      { text: '예금보다 높은 수익', score: 2 },
      { text: '적절한 수익 추구', score: 3 },
      { text: '높은 수익 추구', score: 4 },
      { text: '매우 높은 수익 추구', score: 5 }
    ]
  },
  {
    id: 'q3',
    question: '투자금을 언제 사용할 예정인가?',
    options: [
      { text: '1년 이내', score: 1 },
      { text: '1~3년', score: 2 },
      { text: '3~5년', score: 3 },
      { text: '5~10년', score: 4 },
      { text: '10년 이상', score: 5 }
    ]
  },
  {
    id: 'q4',
    question: '투자금이 일시적으로 손실난다면 어느 정도까지 감수할 수 있나요?',
    options: [
      { text: '손실은 절대 안 됨', score: 1 },
      { text: '-5%', score: 2 },
      { text: '-10%', score: 3 },
      { text: '-20%', score: 4 },
      { text: '-30% 이상도 가능', score: 5 }
    ]
  },
  {
    id: 'q5',
    question: '1개월 만에 15% 손실이 발생했다면?',
    options: [
      { text: '즉시 전부 매도한다', score: 1 },
      { text: '일부 매도한다', score: 2 },
      { text: '상황을 지켜본다', score: 3 },
      { text: '추가 매수한다', score: 4 },
      { text: '좋은 기회라고 생각한다', score: 5 }
    ]
  },
  {
    id: 'q6',
    question: '선호하는 투자 상품은?',
    options: [
      { text: '예금·적금', score: 1 },
      { text: '채권', score: 2 },
      { text: 'ETF', score: 3 },
      { text: '개별 주식', score: 4 },
      { text: '코인·레버리지 상품', score: 5 }
    ]
  },
  {
    id: 'q7',
    question: '연간 기대 수익률은?',
    options: [
      { text: '3% 이하', score: 1 },
      { text: '3~5%', score: 2 },
      { text: '5~10%', score: 3 },
      { text: '10~20%', score: 4 },
      { text: '20% 이상', score: 5 }
    ]
  },
  {
    id: 'q8',
    question: '어떤 투자 방식이 가장 마음에 드나요?',
    options: [
      { text: '안전이 가장 중요하다', score: 1 },
      { text: '안정성과 수익의 균형', score: 2 },
      { text: '적절한 위험 감수', score: 3 },
      { text: '높은 수익을 위해 위험 감수', score: 4 },
      { text: '큰 변동성도 감수 가능', score: 5 }
    ]
  },
  {
    id: 'q9',
    question: '현재 보유 자산 중 투자금이 차지하는 비율은?',
    options: [
      { text: '10% 미만', score: 1 },
      { text: '10~30%', score: 2 },
      { text: '30~50%', score: 3 },
      { text: '50~70%', score: 4 },
      { text: '70% 이상', score: 5 }
    ]
  },
  {
    id: 'q10',
    question: '보유 종목이 하루 만에 10% 하락했다면?',
    options: [
      { text: '잠이 안 온다', score: 1 },
      { text: '매우 불안하다', score: 2 },
      { text: '조금 걱정된다', score: 3 },
      { text: '크게 신경 쓰지 않는다', score: 4 },
      { text: '오히려 추가 매수를 고민한다', score: 5 }
    ]
  }
]

function getInvestType(score) {
  if (score >= 10 && score <= 17) return '안정형'
  if (score >= 18 && score <= 25) return '안정추구형'
  if (score >= 26 && score <= 33) return '위험중립형'
  if (score >= 34 && score <= 41) return '적극투자형'
  if (score >= 42 && score <= 50) return '공격투자형'
  return '미정'
}

function InvestmentSurveyModal({ onClose, onSuccess, onLogout, isMandatory = false }) {
  const [answers, setAnswers] = useState({})
  const [loading, setLoading] = useState(false)

  const handleSelect = (questionId, score) => {
    setAnswers((prev) => ({
      ...prev,
      [questionId]: score
    }))
  }

  const totalScore = Object.values(answers).reduce((sum, score) => sum + score, 0)
  const answeredCount = Object.keys(answers).length

  const handleSave = async () => {
    if (answeredCount < SURVEY_QUESTIONS.length) {
      alert('모든 질문에 응답을 완료해주세요.')
      return
    }

    setLoading(true)
    try {
      const { data: { user }, error: userError } = await supabase.auth.getUser()
      if (userError || !user) {
        alert('로그인이 필요합니다.')
        return
      }

      const investmentType = getInvestType(totalScore)

      // profiles 테이블의 사용자 행에 설문 결과 저장 (updated_at 도 갱신)
      const { error } = await supabase
        .from('profiles')
        .update({
          invest_score: totalScore,
          invest_type: investmentType,
          survey_answers: answers,
          updated_at: new Date().toISOString()
        })
        .eq('id', user.id)

      if (error) throw error

      alert(`설문 분석 완료! 귀하의 투자 성향은 [${investmentType}] 입니다.`)

      console.log("1. onSuccess 호출 전");
      
      if (onSuccess) {
        onSuccess(investmentType, totalScore, answers)
      }
    } catch (error) {
      console.error('설문 저장 실패:', error)
      alert(`저장 실패: ${error.message || '알 수 없는 오류'}`)
    } finally {
      setLoading(false)
    }
  }

  // 닫기 핸들러 (필수 설문일 경우 무시)
  const handleClose = () => {
    if (isMandatory) return
    if (onClose) onClose()
  }

  return (
    <div 
      className="fixed inset-0 bg-[#07080c]/90 backdrop-blur-sm flex items-center justify-center z-50 p-4"
      onClick={handleClose}
    >
      <div 
        className="bg-[#0c0e15] border border-slate-700 w-full max-w-2xl h-[85vh] flex flex-col rounded-xl overflow-hidden shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* 모달 헤더 */}
        <div className="flex items-center justify-between px-6 py-5 border-b border-slate-800">
          <div className="flex flex-col gap-1">
            <h2 className="text-lg font-bold text-white tracking-wider uppercase">
              INVESTMENT RISK PROFILE (투자 성향 분석)
            </h2>
            <p className="text-xs text-slate-400">
              안전하고 성향에 맞는 투자를 제안하기 위해 설문을 작성해 주세요.
            </p>
          </div>
          <span className="text-xs font-mono font-bold text-ai-cyan bg-ai-cyan/10 px-2.5 py-1 rounded">
            진행도: {answeredCount} / {SURVEY_QUESTIONS.length}
          </span>
        </div>

        {/* 설문 질문 영역 (스크롤 가능) */}
        <div className="flex-1 overflow-y-auto px-6 py-6 space-y-6">
          {SURVEY_QUESTIONS.map((q, qIdx) => (
            <div key={q.id} className="bg-[#11131a]/40 border border-slate-800/60 p-5 rounded-lg">
              <h3 className="text-sm font-bold text-white leading-6 mb-4">
                Q{qIdx + 1}. {q.question}
              </h3>
              <div className="grid gap-2">
                {q.options.map((option, optIdx) => {
                  const isSelected = answers[q.id] === option.score
                  return (
                    <button
                      key={optIdx}
                      type="button"
                      onClick={() => handleSelect(q.id, option.score)}
                      className={`w-full text-left px-4 py-3 rounded text-xs font-semibold border transition-all cursor-pointer ${
                        isSelected
                          ? 'bg-ai-cyan/15 border-ai-cyan text-ai-cyan shadow-[0_0_15px_rgba(0,242,254,0.05)]'
                          : 'bg-[#11131a] border-slate-800/80 text-slate-300 hover:border-slate-700 hover:bg-[#151822]'
                      }`}
                    >
                      <div className="flex items-center gap-3">
                        <span className={`w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-mono font-bold border ${
                          isSelected ? 'border-ai-cyan bg-ai-cyan text-[#07080c]' : 'border-slate-600 text-slate-500'
                        }`}>
                          {optIdx + 1}
                        </span>
                        <span>{option.text}</span>
                      </div>
                    </button>
                  )
                })}
              </div>
            </div>
          ))}
        </div>

        {/* 모달 하단 버튼 */}
        <div className="flex gap-3 px-6 py-5 border-t border-slate-800 bg-[#0e1017]">
          <button
            type="button"
            onClick={handleSave}
            disabled={loading || answeredCount < SURVEY_QUESTIONS.length}
            className="flex-1 bg-gradient-to-r from-blue-700 to-ai-cyan hover:opacity-90 active:scale-[0.99] py-3 rounded text-white text-xs font-bold transition-all cursor-pointer disabled:opacity-30 disabled:scale-100"
          >
            {loading ? '제출 중...' : '설문 제출 및 진단 완료'}
          </button>

          {!isMandatory ? (
            <button
              type="button"
              onClick={handleClose}
              className="flex-1 bg-slate-800 hover:bg-slate-700 active:scale-[0.99] py-3 rounded text-slate-300 text-xs font-bold transition-all cursor-pointer"
            >
              닫기
            </button>
          ) : onLogout ? (
            <button
              type="button"
              onClick={onLogout}
              className="flex-1 bg-slate-800 hover:bg-slate-700 active:scale-[0.99] py-3 rounded text-red-400 hover:text-red-300 text-xs font-bold transition-all cursor-pointer"
            >
              중단 및 로그아웃
            </button>
          ) : null}
        </div>
      </div>
    </div>
  )
}

export default InvestmentSurveyModal