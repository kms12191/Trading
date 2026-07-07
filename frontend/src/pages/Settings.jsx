import { useState, useEffect } from 'react'
import { supabase } from '../supabaseClient'
import Header from '../components/Header.jsx'
import InvestmentSurveyModal from '../components/InvestmentSurveyModal'
import { getApiErrorMessage } from '../lib/apiError.js'

export default function Settings({ isLoggedIn, userEmail, handleLogout, userProfile, setUserProfile, hideHeader }) {
  // 브로커 연동 현황 상태
  const [status, setStatus] = useState({
    TOSS: { registered: false },
    KIS: { registered: false },
    KIS_MOCK: { registered: false },
    KIS_REAL: { registered: false },
    COINONE: { registered: false },
    BINANCE: { registered: false },
    BINANCE_REAL: { registered: false },
    BINANCE_MOCK: { registered: false }
  })

  const [activeTab, setActiveTab] = useState('TOSS') // TOSS | KIS | COINONE | BINANCE
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState({ text: '', isError: false })
  const [showSurveyModal, setShowSurveyModal] = useState(false)
  const [profileForm, setProfileForm] = useState({
    nickname: userProfile?.nickname || '',
  })
  const [profileSaving, setProfileSaving] = useState(false)
  const [profileMessage, setProfileMessage] = useState({ text: '', isError: false })
  

  // Toss 폼 상태
  const [tossForm, setTossForm] = useState({
    client_id: '',
    client_secret: '',
    toss_account_seq: '',
    toss_account_no: '',
    broker_env: 'REAL'
  })
  const [tossAccounts, setTossAccounts] = useState([]) // 계좌 목록 상태
  const [tossAccLoading, setTossAccLoading] = useState(false)

  // KIS 서브 탭 상태
  const [kisSubTab, setKisSubTab] = useState('MOCK') // MOCK | REAL

  // KIS MOCK 폼 상태
  const [kisMockForm, setKisMockForm] = useState({
    appkey: '',
    appsecret: '',
    cano: '',
    acnt_prdt_cd: '01',
    broker_env: 'MOCK'
  })

  // KIS REAL 폼 상태
  const [kisRealForm, setKisRealForm] = useState({
    appkey: '',
    appsecret: '',
    cano: '',
    acnt_prdt_cd: '01',
    broker_env: 'REAL'
  })

  // Coinone 폼 상태
  const [coinoneForm, setCoinoneForm] = useState({
    access_token: '',
    secret_key: '',
    broker_env: 'REAL'
  })

  // Binance 폼 상태
  const [binanceForm, setBinanceForm] = useState({
    api_key: '',
    secret_key: '',
    broker_env: 'REAL'
  })

  //
  // 투자성향분석결과 (나중에 DB 연결하면 하드코딩 제거)
  //



  // 세션 헤더 획득 헬퍼 함수
  const getAuthHeader = async () => {
    const { data: { session } } = await supabase.auth.getSession()
    if (!session) return null
    return `Bearer ${session.access_token}`
  }

  const handleSaveProfile = async (event) => {
    event.preventDefault()
    const nickname = profileForm.nickname.trim()

    if (nickname.length < 2 || nickname.length > 16) {
      setProfileMessage({ text: '닉네임은 2자 이상 16자 이하로 입력해 주세요.', isError: true })
      return
    }

    if (!/^[가-힣a-zA-Z0-9_]+$/.test(nickname)) {
      setProfileMessage({ text: '닉네임은 한글, 영문, 숫자, 밑줄만 사용할 수 있습니다.', isError: true })
      return
    }

    setProfileSaving(true)
    setProfileMessage({ text: '', isError: false })

    try {
      const { data: { session } } = await supabase.auth.getSession()
      if (!session?.user?.id) {
        setProfileMessage({ text: '로그인 세션이 만료되었습니다.', isError: true })
        return
      }

      const updatedAt = new Date().toISOString()
      const { error } = await supabase
        .from('profiles')
        .update({
          nickname,
          updated_at: updatedAt,
        })
        .eq('id', session.user.id)

      if (error) throw error

      setUserProfile?.((prev) => ({
        ...(prev || {}),
        nickname,
        updated_at: updatedAt,
      }))
      setProfileMessage({ text: '닉네임이 저장되었습니다. 커뮤니티 글에도 최신 닉네임이 반영됩니다.', isError: false })
    } catch (error) {
      setProfileMessage({ text: error.message || '닉네임 저장에 실패했습니다.', isError: true })
    } finally {
      setProfileSaving(false)
    }
  }

  // API Key 등록 현황 로드
  const loadKeysStatus = async () => {
    const authHeader = await getAuthHeader()
    if (!authHeader) return

    try {
      const response = await fetch('http://localhost:5050/api/keys/status', {
        method: 'GET',
        headers: {
          'Authorization': authHeader
        }
      })
      const resData = await response.json()
      if (resData.success && resData.data) {
        const raw = resData.data
        const processed = {
          ...raw,
          KIS_MOCK: { registered: false },
          KIS_REAL: { registered: false },
          BINANCE_REAL: { registered: false },
          BINANCE_MOCK: { registered: false }
        }
        if (raw.KIS && raw.KIS.accounts) {
          raw.KIS.accounts.forEach(acc => {
            if (acc.broker_env === 'MOCK') {
              processed.KIS_MOCK = acc
            } else if (acc.broker_env === 'REAL') {
              processed.KIS_REAL = acc
            }
          })
        }
        if (raw.BINANCE && raw.BINANCE.accounts) {
          raw.BINANCE.accounts.forEach(acc => {
            if (acc.broker_env === 'MOCK' || acc.broker_env === 'DEMO' || acc.broker_env === 'TESTNET') {
              processed.BINANCE_MOCK = acc
            } else if (acc.broker_env === 'REAL') {
              processed.BINANCE_REAL = acc
            }
          })
        }
        setStatus(processed)
      }
    } catch (error) {
      console.error('연동 현황 로드 실패:', error.message)
    }
  }

  useEffect(() => {
    if (isLoggedIn) {
      const timerId = window.setTimeout(() => {
        loadKeysStatus()
      }, 0)
      return () => window.clearTimeout(timerId)
    }
    return undefined
  }, [isLoggedIn])

  // 연결 테스트 핸들러
  const handleTestConnection = async (exchange) => {
    setLoading(true)
    setMessage({ text: '', isError: false })
    const authHeader = await getAuthHeader()
    if (!authHeader) {
      setMessage({ text: '로그인 세션이 만료되었습니다.', isError: true })
      setLoading(false)
      return
    }

    let payload = { exchange }
    if (exchange === 'TOSS') {
      payload = {
        ...payload,
        client_id: tossForm.client_id,
        client_secret: tossForm.client_secret,
        toss_account_seq: tossForm.toss_account_seq,
        broker_env: tossForm.broker_env
      }
    } else if (exchange === 'KIS') {
      const form = kisSubTab === 'MOCK' ? kisMockForm : kisRealForm
      payload = {
        ...payload,
        appkey: form.appkey,
        appsecret: form.appsecret,
        cano: form.cano,
        acnt_prdt_cd: form.acnt_prdt_cd,
        broker_env: form.broker_env
      }
    } else if (exchange === 'COINONE') {
      payload = {
        ...payload,
        access_token: coinoneForm.access_token,
        secret_key: coinoneForm.secret_key,
        broker_env: coinoneForm.broker_env
      }
    } else if (exchange === 'BINANCE') {
      payload = {
        ...payload,
        api_key: binanceForm.api_key,
        secret_key: binanceForm.secret_key,
        broker_env: binanceForm.broker_env
      }
    }

    try {
      const response = await fetch('http://localhost:5050/api/keys/test', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': authHeader
        },
        body: JSON.stringify(payload)
      })
      const resData = await response.json()
      if (resData.success) {
        setMessage({ text: resData.message, isError: false })
      } else {
        const message = getApiErrorMessage(resData, '연결 테스트에 실패했습니다.')
        setMessage({ text: message.detail ? `${message.title} ${message.detail}` : message.title, isError: true })
      }
    } catch (error) {
      const message = getApiErrorMessage(error, '서버 통신에 실패했습니다.')
      setMessage({ text: message.detail ? `${message.title} ${message.detail}` : message.title, isError: true })
    } finally {
      setLoading(false)
    }
  }

  // API Key 직접 저장 서브 함수
  const saveKeysDirect = async (authHeader, payload) => {
    setMessage({ text: 'API Key 정보를 암호화 저장하는 중...', isError: false })
    try {
      const response = await fetch('http://localhost:5050/api/keys/save', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': authHeader
        },
        body: JSON.stringify(payload)
      })
      const resData = await response.json()
      if (resData.success) {
        setMessage({ text: resData.message, isError: false })
        loadKeysStatus() // 현황 즉시 갱신
      } else {
        const message = getApiErrorMessage(resData, '저장에 실패했습니다.')
        setMessage({ text: message.detail ? `${message.title} ${message.detail}` : message.title, isError: true })
      }
    } catch (error) {
      const message = getApiErrorMessage(error, '서버 저장에 실패했습니다.')
      setMessage({ text: message.detail ? `${message.title} ${message.detail}` : message.title, isError: true })
    }
  }

  // API Key 저장 핸들러 (연결 테스트 검증 강제)
  const handleSaveKeys = async (exchange) => {
    setLoading(true)
    setMessage({ text: '연결 확인 및 키 정보 검증 중...', isError: false })
    const authHeader = await getAuthHeader()
    if (!authHeader) {
      setMessage({ text: '로그인 세션이 만료되었습니다.', isError: true })
      setLoading(false)
      return
    }

    let payload = { exchange }
    let testPayload = { exchange }

    if (exchange === 'TOSS') {
      if (!tossForm.client_id || !tossForm.client_secret) {
        setMessage({ text: 'Toss Client ID와 Secret을 모두 입력해 주세요.', isError: true })
        setLoading(false)
        return
      }
      payload = {
        ...payload,
        client_id: tossForm.client_id,
        client_secret: tossForm.client_secret,
        toss_account_seq: tossForm.toss_account_seq,
        toss_account_no: tossForm.toss_account_no,
        broker_env: tossForm.broker_env
      }
      testPayload = {
        exchange,
        client_id: tossForm.client_id,
        client_secret: tossForm.client_secret,
        toss_account_seq: tossForm.toss_account_seq,
        broker_env: tossForm.broker_env
      }
    } else if (exchange === 'KIS') {
      const form = kisSubTab === 'MOCK' ? kisMockForm : kisRealForm
      if (!form.appkey || !form.appsecret || !form.cano) {
        setMessage({ text: `KIS ${kisSubTab} AppKey, Secret, 계좌번호를 모두 입력해 주세요.`, isError: true })
        setLoading(false)
        return
      }
      payload = {
        ...payload,
        appkey: form.appkey,
        appsecret: form.appsecret,
        cano: form.cano,
        acnt_prdt_cd: form.acnt_prdt_cd,
        broker_env: form.broker_env
      }
      testPayload = {
        exchange,
        appkey: form.appkey,
        appsecret: form.appsecret,
        cano: form.cano,
        acnt_prdt_cd: form.acnt_prdt_cd,
        broker_env: form.broker_env
      }
    } else if (exchange === 'COINONE') {
      if (!coinoneForm.access_token || !coinoneForm.secret_key) {
        setMessage({ text: 'Coinone Access Token과 Secret Key를 모두 입력해 주세요.', isError: true })
        setLoading(false)
        return
      }
      payload = {
        ...payload,
        access_token: coinoneForm.access_token,
        secret_key: coinoneForm.secret_key,
        broker_env: coinoneForm.broker_env
      }
      testPayload = {
        exchange,
        access_token: coinoneForm.access_token,
        secret_key: coinoneForm.secret_key,
        broker_env: coinoneForm.broker_env
      }
    } else if (exchange === 'BINANCE') {
      if (!binanceForm.api_key || !binanceForm.secret_key) {
        setMessage({ text: 'Binance API Key와 Secret Key를 모두 입력해 주세요.', isError: true })
        setLoading(false)
        return
      }
      payload = {
        ...payload,
        api_key: binanceForm.api_key,
        secret_key: binanceForm.secret_key,
        broker_env: binanceForm.broker_env
      }
      testPayload = {
        exchange,
        api_key: binanceForm.api_key,
        secret_key: binanceForm.secret_key,
        broker_env: binanceForm.broker_env
      }
    }

    try {
      // 1. 연결 테스트 강제 수행
      const testResponse = await fetch('http://localhost:5050/api/keys/test', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': authHeader
        },
        body: JSON.stringify(testPayload)
      })

      const testData = await testResponse.json()

      if (testData.success) {
        // 테스트 통과 시 바로 저장
        await saveKeysDirect(authHeader, payload)
      } else {
        // 테스트 실패 시 에러 타입에 따른 분기
        if (testData.error_type === 'TEMPORARY') {
          const confirmSave = window.confirm(
            `[연결 확인 불가] 현재 거래소 서버 점검 또는 네트워크 오류로 인해 실시간 연결 상태를 검증할 수 없습니다.\n\n오류 내용: ${testData.message}\n\n입력하신 키 정보가 확실하다면 그대로 저장하시겠습니까?`
          )
          if (confirmSave) {
            await saveKeysDirect(authHeader, payload)
          } else {
            setMessage({ text: '저장이 취소되었습니다.', isError: true })
          }
        } else {
          // FATAL(인증 실패 등) 오류 시에는 저장하지 않고 에러 표시
          setMessage({
            text: `[저장 실패] 유효하지 않은 키 정보입니다. 연결 검증에 실패했습니다.\n사유: ${testData.message}`,
            isError: true
          })
        }
      }
    } catch (error) {
      // 통신 자체 오류 시에도 임시 에러(TEMPORARY)에 준하여 저장 의사를 물어봄
      const confirmSave = window.confirm(
        `[네트워크 오류] 검증 서버 통신 실패로 인해 연결 검증을 건너뛰어야 합니다.\n\n오류: ${error.message}\n\n입력한 키 정보로 저장을 강행하시겠습니까?`
      )
      if (confirmSave) {
        await saveKeysDirect(authHeader, payload)
      } else {
        setMessage({ text: '통신 오류로 인해 저장이 중단되었습니다.', isError: true })
      }
    } finally {
      setLoading(false)
    }
  }

  // Toss 계좌 실시간 조회 핸들러
  const handleFetchTossAccounts = async () => {
    setTossAccLoading(true)
    setMessage({ text: '', isError: false })
    const authHeader = await getAuthHeader()
    if (!authHeader) {
      setMessage({ text: '로그인 세션이 만료되었습니다.', isError: true })
      setTossAccLoading(false)
      return
    }

    try {
      const response = await fetch('http://localhost:5050/api/keys/toss/accounts', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': authHeader
        },
        body: JSON.stringify({
          client_id: tossForm.client_id,
          client_secret: tossForm.client_secret,
          broker_env: tossForm.broker_env
        })
      })
      const resData = await response.json()
      if (resData.success) {
        setTossAccounts(resData.data)
        if (resData.data.length > 0) {
          // 첫 번째 계좌 기본 선택
          setTossForm(prev => ({
            ...prev,
            toss_account_seq: resData.data[0].accountSeq,
            toss_account_no: resData.data[0].accountNo
          }))
        }
        setMessage({ text: 'Toss 계좌 목록을 조회했습니다. 아래에서 사용할 계좌를 선택해 주세요.', isError: false })
      } else {
        const message = getApiErrorMessage(resData, 'Toss 계좌 조회에 실패했습니다.')
        setMessage({ text: message.detail ? `${message.title} ${message.detail}` : message.title, isError: true })
      }
    } catch (error) {
      const message = getApiErrorMessage(error, '계좌 조회 중 오류가 발생했습니다.')
      setMessage({ text: message.detail ? `${message.title} ${message.detail}` : message.title, isError: true })
    } finally {
      setTossAccLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-obsidian-bg text-[#e2e2ec] font-inter px-6 py-8">
      {/* 공통 상단 네비게이션 헤더 */}
      {!hideHeader && <Header isLoggedIn={isLoggedIn} userEmail={userEmail} handleLogout={handleLogout} userProfile={userProfile} />}

      <main className="max-w-4xl mx-auto flex flex-col gap-8 mt-6">

        {/* 프로필 설정 */}
        <section className="ai-glass rounded-lg p-6 flex flex-col gap-4">
          <div className="flex flex-col gap-2 border-b border-slate-800 pb-3 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h2 className="flex items-center gap-2 text-lg font-bold uppercase tracking-wider text-white">
                <span className="w-2.5 h-2.5 rounded-full bg-ai-cyan" />
                Profile
              </h2>
              <p className="mt-1 text-xs text-slate-400">
                커뮤니티와 헤더에 표시되는 공개 닉네임을 관리합니다.
              </p>
            </div>
            <span className="w-fit rounded border border-cyan-500/30 bg-cyan-950/20 px-2.5 py-1 text-[10px] font-bold text-cyan-200">
              {userProfile?.role === 'ADMIN' ? 'ADMIN' : 'USER'}
            </span>
          </div>

          <form onSubmit={handleSaveProfile} className="flex flex-col gap-2">
            <label className="text-[10px] font-bold uppercase tracking-widest text-slate-400">닉네임</label>
            <div className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_88px] sm:items-stretch">
              <input
                type="text"
                value={profileForm.nickname}
                onChange={(event) => setProfileForm({ nickname: event.target.value })}
                maxLength={16}
                placeholder="닉네임 입력"
                className="h-10 w-full rounded border border-slate-700 bg-[#11131a] px-4 text-sm text-[#e2e2ec] transition-all focus:border-ai-cyan focus:outline-none focus:ring-1 focus:ring-ai-cyan"
              />
              <button
                type="submit"
                disabled={profileSaving}
                className="h-10 rounded border border-cyan-500/40 bg-cyan-950/30 px-3 text-[11px] font-bold text-cyan-200 transition hover:bg-cyan-900/30 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {profileSaving ? '저장 중...' : '저장'}
              </button>
            </div>
            <p className="text-[11px] leading-5 text-slate-500">한글, 영문, 숫자, 밑줄 조합 2~16자</p>
          </form>

          {profileMessage.text ? (
            <p className={`rounded border px-3 py-2 text-xs ${profileMessage.isError ? 'border-rose-500/30 bg-rose-950/20 text-rose-200' : 'border-cyan-500/30 bg-cyan-950/20 text-cyan-200'}`}>
              {profileMessage.text}
            </p>
          ) : null}
        </section>

        {/* 브로커 API 연동 현황판 */}
        <section className="ai-glass rounded-lg p-6 flex flex-col gap-4">
          <h2 className="text-lg font-bold text-white flex items-center gap-2 uppercase tracking-wider border-b border-slate-800 pb-2">
            <span className="w-2.5 h-2.5 rounded-full bg-ai-cyan" />
            API Key Connection Status (브로커 인증 연동 현황)
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">

            {/* Toss 현황 */}
            <div className={`p-4 rounded border transition-all ${status.TOSS.registered ? 'bg-[#0f1b2b]/50 border-blue-900/60' : 'bg-[#0e0f14]/80 border-slate-800'}`}>
              <div className="flex justify-between items-center mb-2">
                <span className="text-sm font-bold text-white font-mono">TOSS (토스증권)</span>
                <span className={`text-[10px] px-2 py-0.5 rounded font-extrabold ${status.TOSS.registered ? 'bg-blue-950 text-blue-400 border border-blue-800/80' : 'bg-slate-900 text-slate-500 border border-slate-800'}`}>
                  {status.TOSS.registered ? '등록됨' : '미등록'}
                </span>
              </div>
              {status.TOSS.registered && (
                <div className="text-[11px] font-mono text-slate-400 flex flex-col gap-1">
                  <div><span className="text-ai-cyan font-bold">api_key:</span> {status.TOSS.access_key}</div>
                  <div><span className="text-ai-cyan font-bold">계좌번호:</span> {status.TOSS.toss_account_no || '미등록'}</div>
                </div>
              )}
            </div>
            {/* KIS 모의 현황 */}
            <div className={`p-4 rounded border transition-all ${status.KIS_MOCK?.registered ? 'bg-[#0e211e]/50 border-emerald-900/60' : 'bg-[#0e0f14]/80 border-slate-800'}`}>
              <div className="flex justify-between items-center mb-2">
                <span className="text-sm font-bold text-white font-mono">KIS (한투 모의)</span>
                <span className={`text-[10px] px-2 py-0.5 rounded font-extrabold ${status.KIS_MOCK?.registered ? 'bg-emerald-950 text-emerald-400 border border-emerald-800/80' : 'bg-slate-900 text-slate-500 border border-slate-800'}`}>
                  {status.KIS_MOCK?.registered ? '등록됨' : '미등록'}
                </span>
              </div>
              {status.KIS_MOCK?.registered && (
                <div className="text-[11px] font-mono text-slate-400 flex flex-col gap-1">
                  <div><span className="text-ai-cyan font-bold">appkey:</span> {status.KIS_MOCK.access_key}</div>
                  <div><span className="text-ai-cyan font-bold">계좌번호:</span> {status.KIS_MOCK.kis_account_no || '미등록'}</div>
                </div>
              )}
            </div>

            {/* KIS 실전 현황 */}
            <div className={`p-4 rounded border transition-all ${status.KIS_REAL?.registered ? 'bg-[#0e211e]/50 border-emerald-900/60' : 'bg-[#0e0f14]/80 border-slate-800'}`}>
              <div className="flex justify-between items-center mb-2">
                <span className="text-sm font-bold text-white font-mono">KIS (한투 실전)</span>
                <span className={`text-[10px] px-2 py-0.5 rounded font-extrabold ${status.KIS_REAL?.registered ? 'bg-emerald-950 text-emerald-400 border border-emerald-800/80' : 'bg-slate-900 text-slate-500 border border-slate-800'}`}>
                  {status.KIS_REAL?.registered ? '등록됨' : '미등록'}
                </span>
              </div>
              {status.KIS_REAL?.registered && (
                <div className="text-[11px] font-mono text-slate-400 flex flex-col gap-1">
                  <div><span className="text-ai-cyan font-bold">appkey:</span> {status.KIS_REAL.access_key}</div>
                  <div><span className="text-ai-cyan font-bold">계좌번호:</span> {status.KIS_REAL.kis_account_no || '미등록'}</div>
                </div>
              )}
            </div>

            {/* Coinone 현황 */}
            <div className={`p-4 rounded border transition-all ${status.COINONE && status.COINONE.registered ? 'bg-[#0e2230]/50 border-sky-900/60' : 'bg-[#0e0f14]/80 border-slate-800'}`}>
              <div className="flex justify-between items-center mb-2">
                <span className="text-sm font-bold text-white font-mono">COINONE (코인원)</span>
                <span className={`text-[10px] px-2 py-0.5 rounded font-extrabold ${status.COINONE && status.COINONE.registered ? 'bg-sky-950 text-sky-400 border border-sky-800/80' : 'bg-slate-900 text-slate-500 border border-slate-800'}`}>
                  {status.COINONE && status.COINONE.registered ? '등록됨' : '미등록'}
                </span>
              </div>
              {status.COINONE && status.COINONE.registered && (
                <div className="text-[11px] font-mono text-slate-400 flex flex-col gap-1">
                  <div><span className="text-ai-cyan font-bold">access_token:</span> {status.COINONE.access_key}</div>
                </div>
              )}
            </div>

            {/* Binance 현황 */}
            <div className={`p-4 rounded border transition-all ${status.BINANCE && status.BINANCE.registered ? 'bg-[#292215]/50 border-amber-900/60' : 'bg-[#0e0f14]/80 border-slate-800'}`}>
              <div className="flex justify-between items-center mb-2">
                <span className="text-sm font-bold text-white font-mono">BINANCE (바이낸스)</span>
                <span className={`text-[10px] px-2 py-0.5 rounded font-extrabold ${status.BINANCE && status.BINANCE.registered ? 'bg-amber-950 text-amber-400 border border-amber-800/80' : 'bg-slate-900 text-slate-500 border border-slate-800'}`}>
                  {status.BINANCE && status.BINANCE.registered ? '등록됨' : '미등록'}
                </span>
              </div>
              <div className="grid grid-cols-1 gap-2 text-[11px] font-mono text-slate-400 sm:grid-cols-2">
                <div className={`rounded border px-2 py-2 ${status.BINANCE_REAL?.registered ? 'border-amber-800/60 bg-amber-950/20' : 'border-slate-800 bg-slate-950/20'}`}>
                  <div className="mb-1 font-bold text-slate-300">REAL 실거래</div>
                  {status.BINANCE_REAL?.registered ? (
                    <div><span className="text-ai-cyan font-bold">api_key:</span> {status.BINANCE_REAL.access_key}</div>
                  ) : (
                    <div className="text-slate-600">미등록</div>
                  )}
                </div>
                <div className={`rounded border px-2 py-2 ${status.BINANCE_MOCK?.registered ? 'border-emerald-800/60 bg-emerald-950/20' : 'border-slate-800 bg-slate-950/20'}`}>
                  <div className="mb-1 font-bold text-slate-300">MOCK 모의투자</div>
                  {status.BINANCE_MOCK?.registered ? (
                    <div><span className="text-ai-cyan font-bold">api_key:</span> {status.BINANCE_MOCK.access_key}</div>
                  ) : (
                    <div className="text-slate-600">미등록</div>
                  )}
                </div>
              </div>
              <p className="mt-2 text-[10px] leading-4 text-slate-500">
                USD-M 선물은 별도 키 슬롯을 만들지 않고 위 바이낸스 REAL/MOCK 키를 재사용합니다. 선물 REAL 주문은 서버 안전 플래그가 켜져 있을 때만 허용됩니다.
              </p>
            </div>

          </div>
        </section>

        {/* 탭 기반 키 등록 설정 입력창 */}
        <section className="ai-glass rounded-lg p-6 flex flex-col gap-6">
          <div className="flex border-b border-slate-800 gap-2">
            {['TOSS', 'KIS', 'COINONE', 'BINANCE'].map((tab) => (
              <button
                key={tab}
                onClick={() => {
                  setActiveTab(tab)
                  setMessage({ text: '', isError: false })
                }}
                className={`px-6 py-2.5 text-xs font-extrabold tracking-widest transition-all cursor-pointer border-b-2 ${activeTab === tab
                    ? 'border-ai-cyan text-ai-cyan bg-ai-cyan/5'
                    : 'border-transparent text-slate-400 hover:text-white'
                  }`}
                type="button"
              >
                [{tab}]
              </button>
            ))}
          </div>

          {/* 에러/성공 메시지 알림 카드 */}
          {message.text && (
            <div className={`whitespace-pre-line p-3 rounded text-xs border transition-all ${message.isError
                ? 'bg-red-950/20 border-red-800 text-red-300'
                : 'bg-emerald-950/20 border-emerald-800 text-emerald-300'
              }`}>
              {message.text}
            </div>
          )}

          {/* Toss 설정 탭 */}
          {activeTab === 'TOSS' && (
            <div className="flex flex-col gap-4">
              <div>
                <label className="block text-[10px] font-bold text-slate-400 mb-1">API KEY</label>
                <input
                  type="text"
                  value={tossForm.client_id}
                  onChange={(e) => setTossForm(prev => ({ ...prev, client_id: e.target.value }))}
                  placeholder="Toss Open API API Key 입력"
                  className="w-full bg-[#0F172A] border border-slate-700 rounded px-3 py-2 text-sm font-mono text-white focus:outline-none focus:border-ai-cyan"
                />
              </div>

              <div>
                <label className="block text-[10px] font-bold text-slate-400 mb-1">SECRET KEY</label>
                <input
                  type="password"
                  value={tossForm.client_secret}
                  onChange={(e) => setTossForm(prev => ({ ...prev, client_secret: e.target.value }))}
                  placeholder="Toss Open API Secret Key 입력"
                  className="w-full bg-[#0F172A] border border-slate-700 rounded px-3 py-2 text-sm font-mono text-white focus:outline-none focus:border-ai-cyan"
                />
              </div>

              <div className="mt-2">
                <button
                  onClick={handleFetchTossAccounts}
                  disabled={tossAccLoading}
                  className="w-full bg-slate-800 hover:bg-slate-700 border border-slate-700 text-white text-xs font-bold py-2.5 rounded transition-all cursor-pointer disabled:opacity-50"
                >
                  {tossAccLoading ? '계좌 가져오는 중...' : '계좌 조회'}
                </button>
              </div>

              {tossAccounts.length > 0 && (
                <div>
                  <label className="block text-[10px] font-bold text-slate-400 mb-1">사용할 계좌 선택 (accountSeq)</label>
                  <select
                    value={tossForm.toss_account_seq}
                    onChange={(e) => {
                      const selectedAcc = tossAccounts.find(acc => acc.accountSeq === e.target.value)
                      setTossForm(prev => ({
                        ...prev,
                        toss_account_seq: e.target.value,
                        toss_account_no: selectedAcc ? selectedAcc.accountNo : ''
                      }))
                    }}
                    className="w-full bg-[#0F172A] border border-slate-700 rounded px-3 py-2 text-sm font-bold text-white focus:outline-none focus:border-ai-cyan cursor-pointer"
                  >
                    {tossAccounts.map((acc) => (
                      <option key={acc.accountSeq} value={acc.accountSeq}>
                        {acc.accountNo} (식별값: {acc.accountSeq})
                      </option>
                    ))}
                  </select>
                </div>
              )}

              <div className="flex gap-4 mt-2">
                <button
                  onClick={() => handleSaveKeys('TOSS')}
                  disabled={loading}
                  className="flex-1 bg-gradient-to-r from-blue-700 to-ai-cyan text-white text-xs font-bold py-2.5 rounded transition-all cursor-pointer disabled:opacity-50"
                >
                  저장
                </button>
                <button
                  onClick={() => handleTestConnection('TOSS')}
                  disabled={loading}
                  className="flex-1 bg-slate-800 hover:bg-slate-700 border border-slate-700 text-white text-xs font-bold py-2.5 rounded transition-all cursor-pointer disabled:opacity-50"
                >
                  연결 테스트
                </button>
              </div>
            </div>
          )}

          {/* KIS 설정 탭 */}
          {activeTab === 'KIS' && (
            <div className="flex flex-col gap-4">
              {/* KIS 서브 탭 스위처 */}
              <div className="flex border-b border-[#1f2945] gap-2 mb-2">
                {['MOCK', 'REAL'].map((sub) => (
                  <button
                    key={sub}
                    onClick={() => {
                      setKisSubTab(sub)
                      setMessage({ text: '', isError: false })
                    }}
                    className={`px-4 py-1.5 text-[10px] font-extrabold tracking-widest transition-all cursor-pointer border-b-2 ${kisSubTab === sub
                        ? 'border-ai-cyan text-ai-cyan bg-ai-cyan/5'
                        : 'border-transparent text-slate-500 hover:text-white'
                      }`}
                    type="button"
                  >
                    {sub === 'MOCK' ? 'MOCK (모의투자)' : 'REAL (실전거래)'}
                  </button>
                ))}
              </div>

              <div>
                <label className="block text-[10px] font-bold text-slate-400 mb-1">APP KEY ({kisSubTab})</label>
                <input
                  type="text"
                  value={kisSubTab === 'MOCK' ? kisMockForm.appkey : kisRealForm.appkey}
                  onChange={(e) => {
                    const val = e.target.value;
                    if (kisSubTab === 'MOCK') {
                      setKisMockForm(prev => ({ ...prev, appkey: val }));
                    } else {
                      setKisRealForm(prev => ({ ...prev, appkey: val }));
                    }
                  }}
                  placeholder={`KIS ${kisSubTab} AppKey 입력`}
                  className="w-full bg-[#0F172A] border border-slate-700 rounded px-3 py-2 text-sm font-mono text-white focus:outline-none focus:border-ai-cyan"
                />
              </div>

              <div>
                <label className="block text-[10px] font-bold text-slate-400 mb-1">APP SECRET ({kisSubTab})</label>
                <input
                  type="password"
                  value={kisSubTab === 'MOCK' ? kisMockForm.appsecret : kisRealForm.appsecret}
                  onChange={(e) => {
                    const val = e.target.value;
                    if (kisSubTab === 'MOCK') {
                      setKisMockForm(prev => ({ ...prev, appsecret: val }));
                    } else {
                      setKisRealForm(prev => ({ ...prev, appsecret: val }));
                    }
                  }}
                  placeholder={`KIS ${kisSubTab} AppSecret 입력`}
                  className="w-full bg-[#0F172A] border border-slate-700 rounded px-3 py-2 text-sm font-mono text-white focus:outline-none focus:border-ai-cyan"
                />
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-[10px] font-bold text-slate-400 mb-1">CANO (계좌번호) ({kisSubTab})</label>
                  <input
                    type="text"
                    value={kisSubTab === 'MOCK' ? kisMockForm.cano : kisRealForm.cano}
                    onChange={(e) => {
                      const val = e.target.value;
                      if (kisSubTab === 'MOCK') {
                        setKisMockForm(prev => ({ ...prev, cano: val }));
                      } else {
                        setKisRealForm(prev => ({ ...prev, cano: val }));
                      }
                    }}
                    placeholder="8자리 계좌번호"
                    className="w-full bg-[#0F172A] border border-slate-700 rounded px-3 py-2 text-sm font-mono text-white focus:outline-none focus:border-ai-cyan"
                  />
                </div>
                <div>
                  <label className="block text-[10px] font-bold text-slate-400 mb-1">계좌코드 ({kisSubTab})</label>
                  <input
                    type="text"
                    value={kisSubTab === 'MOCK' ? kisMockForm.acnt_prdt_cd : kisRealForm.acnt_prdt_cd}
                    onChange={(e) => {
                      const val = e.target.value;
                      if (kisSubTab === 'MOCK') {
                        setKisMockForm(prev => ({ ...prev, acnt_prdt_cd: val }));
                      } else {
                        setKisRealForm(prev => ({ ...prev, acnt_prdt_cd: val }));
                      }
                    }}
                    placeholder="기본값 01"
                    className="w-full bg-[#0F172A] border border-slate-700 rounded px-3 py-2 text-sm font-mono text-white focus:outline-none focus:border-ai-cyan"
                  />
                </div>
              </div>

              <div className="flex gap-4 mt-2">
                <button
                  onClick={() => handleSaveKeys('KIS')}
                  disabled={loading}
                  className="flex-1 bg-gradient-to-r from-blue-700 to-cyan-400 text-white text-xs font-bold py-2.5 rounded transition-all cursor-pointer disabled:opacity-50"
                >
                  저장
                </button>
                <button
                  onClick={() => handleTestConnection('KIS')}
                  disabled={loading}
                  className="flex-1 bg-slate-800 hover:bg-slate-700 border border-slate-700 text-white text-xs font-bold py-2.5 rounded transition-all cursor-pointer disabled:opacity-50"
                >
                  연결 테스트
                </button>
              </div>
            </div>
          )}

          {/* Coinone 설정 탭 */}
          {activeTab === 'COINONE' && (
            <div className="flex flex-col gap-4">
              <div>
                <label className="block text-[10px] font-bold text-slate-400 mb-1">ACCESS TOKEN</label>
                <input
                  type="text"
                  value={coinoneForm.access_token}
                  onChange={(e) => setCoinoneForm(prev => ({ ...prev, access_token: e.target.value }))}
                  placeholder="코인원 Access Token 입력"
                  className="w-full bg-[#0F172A] border border-slate-700 rounded px-3 py-2 text-sm font-mono text-white focus:outline-none focus:border-ai-cyan"
                />
              </div>

              <div>
                <label className="block text-[10px] font-bold text-slate-400 mb-1">SECRET KEY</label>
                <input
                  type="password"
                  value={coinoneForm.secret_key}
                  onChange={(e) => setCoinoneForm(prev => ({ ...prev, secret_key: e.target.value }))}
                  placeholder="코인원 Secret Key 입력"
                  className="w-full bg-[#0F172A] border border-slate-700 rounded px-3 py-2 text-sm font-mono text-white focus:outline-none focus:border-ai-cyan"
                />
              </div>

              <div className="flex gap-4 mt-2">
                <button
                  onClick={() => handleSaveKeys('COINONE')}
                  disabled={loading}
                  className="flex-1 bg-gradient-to-r from-blue-700 to-cyan-400 text-white text-xs font-bold py-2.5 rounded transition-all cursor-pointer disabled:opacity-50"
                >
                  저장
                </button>
                <button
                  onClick={() => handleTestConnection('COINONE')}
                  disabled={loading}
                  className="flex-1 bg-slate-800 hover:bg-slate-700 border border-slate-700 text-white text-xs font-bold py-2.5 rounded transition-all cursor-pointer disabled:opacity-50"
                >
                  연결 테스트
                </button>
              </div>
            </div>
          )}

          {/* Binance 설정 탭 */}
          {activeTab === 'BINANCE' && (
            <div className="flex flex-col gap-4">
              <div className="grid grid-cols-2 gap-2 rounded-lg border border-slate-800 bg-[#0F172A]/60 p-1">
                {[
                  { key: 'REAL', label: '실거래 REAL', desc: '실제 바이낸스 계정' },
                  { key: 'MOCK', label: '모의 MOCK', desc: 'Binance Demo API' },
                ].map((item) => (
                  <button
                    key={item.key}
                    type="button"
                    onClick={() => setBinanceForm(prev => ({ ...prev, broker_env: item.key }))}
                    className={`rounded px-3 py-2 text-left transition-all ${
                      binanceForm.broker_env === item.key
                        ? 'border border-ai-cyan bg-ai-cyan/10 text-white'
                        : 'border border-transparent text-slate-400 hover:bg-slate-800/60 hover:text-white'
                    }`}
                  >
                    <div className="text-xs font-extrabold">{item.label}</div>
                    <div className="mt-0.5 text-[10px] text-slate-500">{item.desc}</div>
                  </button>
                ))}
              </div>

              {binanceForm.broker_env === 'MOCK' ? (
                <div className="rounded border border-emerald-500/20 bg-emerald-500/10 px-3 py-2 text-[11px] leading-5 text-emerald-100">
                  모의 MOCK은 바이낸스 테스트넷/데모 환경 키를 저장합니다. 현물/선물 모두 동일한 데모 키를 재사용하여 모의 투자를 수행합니다.
                </div>
              ) : (
                <div className="rounded border border-amber-500/20 bg-amber-500/10 px-3 py-2 text-[11px] leading-5 text-amber-100">
                  실거래 키는 실제 바이낸스 계정에 연결됩니다. 현물 잔고/주문 및 USD-M 선물 거래에 공통으로 사용되며, 출금 주소 조회와 입금 추적 역시 이 REAL 키를 사용합니다.
                </div>
              )}

              <div>
                <label className="block text-[10px] font-bold text-slate-400 mb-1">API KEY</label>
                <input
                  type="text"
                  value={binanceForm.api_key}
                  onChange={(e) => setBinanceForm(prev => ({ ...prev, api_key: e.target.value }))}
                  placeholder="바이낸스 API Key 입력"
                  className="w-full bg-[#0F172A] border border-slate-700 rounded px-3 py-2 text-sm font-mono text-white focus:outline-none focus:border-ai-cyan"
                />
              </div>

              <div>
                <label className="block text-[10px] font-bold text-slate-400 mb-1">SECRET KEY</label>
                <input
                  type="password"
                  value={binanceForm.secret_key}
                  onChange={(e) => setBinanceForm(prev => ({ ...prev, secret_key: e.target.value }))}
                  placeholder="바이낸스 Secret Key 입력"
                  className="w-full bg-[#0F172A] border border-slate-700 rounded px-3 py-2 text-sm font-mono text-white focus:outline-none focus:border-ai-cyan"
                />
              </div>

              <div className="flex gap-4 mt-2">
                <button
                  onClick={() => handleSaveKeys('BINANCE')}
                  disabled={loading}
                  className="flex-1 bg-gradient-to-r from-blue-700 to-cyan-400 text-white text-xs font-bold py-2.5 rounded transition-all cursor-pointer disabled:opacity-50"
                >
                  저장
                </button>
                <button
                  onClick={() => handleTestConnection('BINANCE')}
                  disabled={loading}
                  className="flex-1 bg-slate-800 hover:bg-slate-700 border border-slate-700 text-white text-xs font-bold py-2.5 rounded transition-all cursor-pointer disabled:opacity-50"
                >
                  연결 테스트
                </button>
              </div>
            </div>
          )}
        </section>
        
        {/* ================= 투자 성향 ================= */}

        <section className="ai-glass rounded-lg p-6 flex flex-col gap-6">
          <h2 className="text-lg font-bold text-white flex items-center gap-2 uppercase tracking-wider border-b border-slate-800 pb-2">
            <span className="w-2.5 h-2.5 rounded-full bg-ai-cyan" />
            INVESTMENT PROFILE
          </h2>

          <div className="bg-[#0F172A] border border-ai-cyan/40 rounded-lg p-6">
            <div className="text-slate-400 text-xs font-bold">
              현재 투자 성향
            </div>

            <div className="mt-4 text-3xl font-bold text-ai-cyan">
              {userProfile?.invest_type}
            </div>

            <div className="mt-5 text-sm text-slate-300">
              위험 점수 : {userProfile?.invest_score || 0} / 50
            </div>

            <div className="text-sm text-slate-500 mt-2">
              최근 분석일 : {userProfile?.updated_at ? new Date(userProfile.updated_at).toLocaleDateString('ko-KR') : '기록 없음'}
            </div>
          </div>

          <button
            onClick={() => setShowSurveyModal(true)}
            className="flex-1 bg-gradient-to-r from-blue-700 to-cyan-400 text-white text-xs font-bold py-2.5 rounded transition-all cursor-pointer disabled:opacity-50"
          >
            투자 성향 재분석
          </button>
        </section>

        {
          showSurveyModal && (
            <InvestmentSurveyModal
              onClose={() => setShowSurveyModal(false)}
              onSuccess={(type, score) => {
                if (typeof setUserProfile === 'function') {
                  setUserProfile(prev => prev ? {
                    ...prev,
                    invest_type: type,
                    invest_score: score,
                    updated_at: new Date().toISOString()
                  } : null);
                }

                setShowSurveyModal(false);
              }}
                            
            />
          )
        }

      </main>
    </div>
  )


}
