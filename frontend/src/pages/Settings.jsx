import React, { useState, useEffect } from 'react'
import { supabase } from '../supabaseClient'
import Header from '../components/Header.jsx'

export default function Settings({ isLoggedIn, userEmail, handleLogout, userProfile, hideHeader }) {
  // 브로커 연동 현황 상태
  const [status, setStatus] = useState({
    TOSS: { registered: false },
    KIS: { registered: false },
    COINONE: { registered: false },
    BINANCE: { registered: false }
  })
  
  const [activeTab, setActiveTab] = useState('TOSS') // TOSS | KIS | COINONE | BINANCE
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState({ text: '', isError: false })
  
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

  // KIS 폼 상태
  const [kisForm, setKisForm] = useState({
    appkey: '',
    appsecret: '',
    cano: '',
    acnt_prdt_cd: '01',
    broker_env: 'MOCK'
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

  // 세션 헤더 획득 헬퍼 함수
  const getAuthHeader = async () => {
    const { data: { session } } = await supabase.auth.getSession()
    if (!session) return null
    return `Bearer ${session.access_token}`
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
      if (resData.success) {
        setStatus(resData.data)
      }
    } catch (error) {
      console.error('연동 현황 로드 실패:', error.message)
    }
  }

  useEffect(() => {
    if (isLoggedIn) {
      loadKeysStatus()
    }
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
      payload = {
        ...payload,
        appkey: kisForm.appkey,
        appsecret: kisForm.appsecret,
        cano: kisForm.cano,
        acnt_prdt_cd: kisForm.acnt_prdt_cd,
        broker_env: kisForm.broker_env
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
        setMessage({ text: resData.message || '연결 테스트에 실패했습니다.', isError: true })
      }
    } catch (error) {
      setMessage({ text: `서버 통신 실패: ${error.message}`, isError: true })
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
        setMessage({ text: resData.message || '저장에 실패했습니다.', isError: true })
      }
    } catch (error) {
      setMessage({ text: `서버 저장 실패: ${error.message}`, isError: true })
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
      if (!kisForm.appkey || !kisForm.appsecret || !kisForm.cano) {
        setMessage({ text: 'KIS AppKey, Secret, 계좌번호를 모두 입력해 주세요.', isError: true })
        setLoading(false)
        return
      }
      payload = {
        ...payload,
        appkey: kisForm.appkey,
        appsecret: kisForm.appsecret,
        cano: kisForm.cano,
        acnt_prdt_cd: kisForm.acnt_prdt_cd,
        broker_env: kisForm.broker_env
      }
      testPayload = {
        exchange,
        appkey: kisForm.appkey,
        appsecret: kisForm.appsecret,
        cano: kisForm.cano,
        acnt_prdt_cd: kisForm.acnt_prdt_cd,
        broker_env: kisForm.broker_env
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
        setMessage({ text: resData.message || 'Toss 계좌 조회 실패.', isError: true })
      }
    } catch (error) {
      setMessage({ text: `계좌 조회 중 오류: ${error.message}`, isError: true })
    } finally {
      setTossAccLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-obsidian-bg text-[#e2e2ec] font-inter px-6 py-8">
      {/* 공통 상단 네비게이션 헤더 */}
      {!hideHeader && <Header isLoggedIn={isLoggedIn} userEmail={userEmail} handleLogout={handleLogout} userProfile={userProfile} />}

      <main className="max-w-4xl mx-auto flex flex-col gap-8 mt-6">
        
        {/* 브로커 API 연동 현황판 */}
        <section className="ai-glass rounded-lg p-6 flex flex-col gap-4">
          <h2 className="text-lg font-bold text-white flex items-center gap-2 uppercase tracking-wider border-b border-slate-800 pb-2">
            <span className="w-2.5 h-2.5 rounded-full bg-ai-cyan" />
            API Key Connection Status (브로커 인증 연동 현황)
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            
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

            {/* KIS 현황 */}
            <div className={`p-4 rounded border transition-all ${status.KIS.registered ? 'bg-[#0e211e]/50 border-emerald-900/60' : 'bg-[#0e0f14]/80 border-slate-800'}`}>
              <div className="flex justify-between items-center mb-2">
                <span className="text-sm font-bold text-white font-mono">KIS (한국투자)</span>
                <span className={`text-[10px] px-2 py-0.5 rounded font-extrabold ${status.KIS.registered ? 'bg-emerald-950 text-emerald-400 border border-emerald-800/80' : 'bg-slate-900 text-slate-500 border border-slate-800'}`}>
                  {status.KIS.registered ? `등록됨 (${status.KIS.broker_env})` : '미등록'}
                </span>
              </div>
              {status.KIS.registered && (
                <div className="text-[11px] font-mono text-slate-400 flex flex-col gap-1">
                  <div><span className="text-ai-cyan font-bold">appkey:</span> {status.KIS.access_key}</div>
                  <div><span className="text-ai-cyan font-bold">계좌번호:</span> {status.KIS.kis_account_no || '미등록'}</div>
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
              {status.BINANCE && status.BINANCE.registered && (
                <div className="text-[11px] font-mono text-slate-400 flex flex-col gap-1">
                  <div><span className="text-ai-cyan font-bold">api_key:</span> {status.BINANCE.access_key}</div>
                </div>
              )}
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
                className={`px-6 py-2.5 text-xs font-extrabold tracking-widest transition-all cursor-pointer border-b-2 ${
                  activeTab === tab
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
            <div className={`p-3 rounded text-xs border transition-all ${
              message.isError 
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
              <div>
                <label className="block text-[10px] font-bold text-slate-400 mb-1">APP KEY</label>
                <input
                  type="text"
                  value={kisForm.appkey}
                  onChange={(e) => setKisForm(prev => ({ ...prev, appkey: e.target.value }))}
                  placeholder="KIS AppKey 입력"
                  className="w-full bg-[#0F172A] border border-slate-700 rounded px-3 py-2 text-sm font-mono text-white focus:outline-none focus:border-ai-cyan"
                />
              </div>

              <div>
                <label className="block text-[10px] font-bold text-slate-400 mb-1">APP SECRET</label>
                <input
                  type="password"
                  value={kisForm.appsecret}
                  onChange={(e) => setKisForm(prev => ({ ...prev, appsecret: e.target.value }))}
                  placeholder="KIS AppSecret 입력"
                  className="w-full bg-[#0F172A] border border-slate-700 rounded px-3 py-2 text-sm font-mono text-white focus:outline-none focus:border-ai-cyan"
                />
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div>
                  <label className="block text-[10px] font-bold text-slate-400 mb-1">CANO (계좌번호)</label>
                  <input
                    type="text"
                    value={kisForm.cano}
                    onChange={(e) => setKisForm(prev => ({ ...prev, cano: e.target.value }))}
                    placeholder="8자리 계좌번호"
                    className="w-full bg-[#0F172A] border border-slate-700 rounded px-3 py-2 text-sm font-mono text-white focus:outline-none focus:border-ai-cyan"
                  />
                </div>
                <div>
                  <label className="block text-[10px] font-bold text-slate-400 mb-1">계좌코드</label>
                  <input
                    type="text"
                    value={kisForm.acnt_prdt_cd}
                    onChange={(e) => setKisForm(prev => ({ ...prev, acnt_prdt_cd: e.target.value }))}
                    placeholder="기본값 01"
                    className="w-full bg-[#0F172A] border border-slate-700 rounded px-3 py-2 text-sm font-mono text-white focus:outline-none focus:border-ai-cyan"
                  />
                </div>
                <div>
                  <label className="block text-[10px] font-bold text-slate-400 mb-1">ENVIRONMENT</label>
                  <select
                    value={kisForm.broker_env}
                    onChange={(e) => setKisForm(prev => ({ ...prev, broker_env: e.target.value }))}
                    className="w-full bg-[#0F172A] border border-slate-700 rounded px-3 py-2 text-sm font-bold text-white focus:outline-none focus:border-ai-cyan cursor-pointer"
                  >
                    <option value="MOCK">MOCK (모의)</option>
                    <option value="REAL">REAL (실전)</option>
                  </select>
                </div>
              </div>

              <div className="flex gap-4 mt-2">
                <button
                  onClick={() => handleSaveKeys('KIS')}
                  disabled={loading}
                  className="flex-1 bg-gradient-to-r from-emerald-700 to-teal-500 text-white text-xs font-bold py-2.5 rounded transition-all cursor-pointer disabled:opacity-50"
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
                  className="flex-1 bg-gradient-to-r from-sky-700 to-sky-500 text-white text-xs font-bold py-2.5 rounded transition-all cursor-pointer disabled:opacity-50"
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
                  className="flex-1 bg-gradient-to-r from-amber-700 to-amber-500 text-white text-xs font-bold py-2.5 rounded transition-all cursor-pointer disabled:opacity-50"
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

      </main>
    </div>
  )
}
