import { useState } from 'react'
import { supabase } from '../supabaseClient'

const questions = [
    {
        question: "Q1. 주식·ETF·코인 등 투자 경험은?",
        options: [
            { text: "없음", score: 1 },
            { text: "1년 미만", score: 2 },
            { text: "1~3년", score: 3 },
            { text: "3~5년", score: 4 },
            { text: "5년 이상", score: 5 }
        ]
    },

    {
        question: "Q2. 투자하는 가장 큰 이유는?",
        options: [
            { text: "원금 보존", score: 1 },
            { text: "예금보다 높은 수익", score: 2 },
            { text: "적절한 수익 추구", score: 3 },
            { text: "높은 수익 추구", score: 4 },
            { text: "매우 높은 수익 추구", score: 5 }
        ]
    },

    {
        question: "Q3. 투자금을 언제 사용할 예정인가?",
        options: [
            { text: "1년 이내", score: 1 },
            { text: "1~3년", score: 2 },
            { text: "3~5년", score: 3 },
            { text: "5~10년", score: 4 },
            { text: "10년 이상", score: 5 }
        ]
    },

    {
        question: "Q4. 투자금이 일시적으로 손실난다면 어느 정도까지 감수할 수 있나요?",
        options: [
            { text: "손실은 절대 안 됨", score: 1 },
            { text: "-5%", score: 2 },
            { text: "-10%", score: 3 },
            { text: "-20%", score: 4 },
            { text: "-30% 이상도 가능", score: 5 }
        ]
    },

    {
        question: "Q5. 1개월 만에 15% 손실이 발생했다면?",
        options: [
            { text: "즉시 전부 매도한다", score: 1 },
            { text: "일부 매도한다", score: 2 },
            { text: "상황을 지켜본다", score: 3 },
            { text: "추가 매수한다", score: 4 },
            { text: "좋은 기회라고 생각한다", score: 5 }
        ]
    },

    {
        question: "Q6. 선호하는 투자 상품은?",
        options: [
            { text: "예금·적금", score: 1 },
            { text: "채권", score: 2 },
            { text: "ETF", score: 3 },
            { text: "개별 주식", score: 4 },
            { text: "코인·레버리지 상품", score: 5 }
        ]
    },

    {
        question: "Q7. 연간 기대 수익률은?",
        options: [
            { text: "3% 이하", score: 1 },
            { text: "3~5%", score: 2 },
            { text: "5~10%", score: 3 },
            { text: "10~20%", score: 4 },
            { text: "20% 이상", score: 5 }
        ]
    },

    {
        question: "Q8. 어떤 투자 방식이 가장 마음에 드나요?",
        options: [
            { text: "안전이 가장 중요하다", score: 1 },
            { text: "안정성과 수익의 균형", score: 2 },
            { text: "적절한 위험 감수", score: 3 },
            { text: "높은 수익을 위해 위험 감수", score: 4 },
            { text: "큰 변동성도 감수 가능", score: 5 }
        ]
    },

    {
        question: "Q9. 현재 보유 자산 중 투자금이 차지하는 비율은?",
        options: [
            { text: "10% 미만", score: 1 },
            { text: "10~30%", score: 2 },
            { text: "30~50%", score: 3 },
            { text: "50~70%", score: 4 },
            { text: "70% 이상", score: 5 }
        ]
    },

    {
        question: "Q10. 보유 종목이 하루 만에 10% 하락했다면?",
        options: [
            { text: "잠이 안 온다", score: 1 },
            { text: "매우 불안하다", score: 2 },
            { text: "조금 걱정된다", score: 3 },
            { text: "크게 신경 쓰지 않는다", score: 4 },
            { text: "오히려 추가 매수를 고민한다", score: 5 }
        ]
    }
]

function InvestmentSurveyModal({ onClose, user, userProfile }) {

    const [answers, setAnswers] = useState({})

    const handleSelect = (index, score) => {
        setAnswers(prev => ({
            ...prev,
            [index]: score
        }))
    }

    const totalScore = Object.values(answers).reduce((sum, score) => sum + score, 0)

    function getInvestmentType(score) {
        if (score <= 17) return "안정형"
        if (score <= 25) return "안정추구형"
        if (score <= 33) return "위험중립형"
        if (score <= 41) return "적극투자형"
        return "공격투자형"
    }

    // const handleSave = async () => {
    //     const investmentType = getInvestmentType(totalScore)
    //     const currentUser = user || userProfile
    //     if (!currentUser?.id) {
    //         alert('유저 정보가 없습니다.')
    //         return
    //     }

    //     // DB 저장
    //     const { error } = await supabase
    //         .from('users')
    //         .upsert(
    //             {
    //                 user_id: currentUser.id,
    //                 invest_score: totalScore,
    //                 invest_type: investmentType
    //             },
    //             {
    //                 onConflict: 'user_id'
    //             }
    //         )

    //     if (error) {
    //         console.log(error)
    //         alert('저장 실패')
    //         return
    //     }

    //     alert('투자 성향이 갱신되었습니다.')
    //     onClose()
    // }

    const handleSave = async () => {
        const { data: { user }, error: userError } = await supabase.auth.getUser()

        if (userError || !user) {
            alert('로그인이 필요합니다.')
            return
        }

        const investmentType = getInvestmentType(totalScore)

        const { error } = await supabase
            .from('users')
            .upsert(
                {
                    user_id: user.id,
                    invest_score: totalScore,
                    invest_type: investmentType
                },
                {
                    onConflict: 'user_id'
                }
            )

        if (error) {
            console.log(error)
            alert('저장 실패')
            return
        }

        alert('투자 성향이 갱신되었습니다.')
        onClose()
    }

    return (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50">

            <div className="bg-slate-800 w-[900px] h-[800px] overflow-y-auto rounded-xl p-8">

                <h2 className="text-2xl text-white font-bold mb-8">
                    투자 성향 재분석
                </h2>

                {questions.map((question, index) => (

                    <div key={index} className="mb-8">

                        <h3 className="text-white font-bold mb-4">
                            {question.question}
                        </h3>

                        <div className="flex flex-col gap-2">

                            {question.options.map(option => (

                                <button
                                    key={option.text}
                                    onClick={() => handleSelect(index, option.score)}
                                    className={`rounded p-3 text-left text-white transition
                                            ${answers[index] === option.score
                                            ? "bg-cyan-600"
                                            : "bg-slate-700 hover:bg-cyan-700"
                                        }`}
                                >
                                    {option.text}
                                </button>

                            ))}

                        </div>

                    </div>

                ))}

                <div className="mt-8 flex gap-4">

                    <button
                        onClick={handleSave}
                        className="flex-1 bg-gradient-to-r from-blue-700 to-cyan-400 py-3 rounded text-white font-bold"
                    >
                        저장
                    </button>

                    <button
                        onClick={onClose}
                        className="flex-1 bg-slate-700 py-3 rounded text-white"
                    >
                        닫기
                    </button>

                </div>

            </div>

        </div>
    )
}

export default InvestmentSurveyModal