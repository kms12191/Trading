import {
  formatDisclosureDate,
  formatNewsSource,
  formatRelativeTime as formatTime,
  getDisclosureToneClass,
} from './assetDetailModel.js'

export default function AssetDetailNewsDisclosurePanel({
  activeTab,
  isNewsDisclosureSectionActive = true,
  newsList,
  loadingNews,
  summaryLoadingId,
  selectedNewsId,
  newsSyncing,
  newsSyncMessage,
  disclosureList,
  loadingDisclosures,
  disclosureAnalyses,
  selectedDisclosureId,
  disclosureAnalysisLoadingId,
  disclosureSyncing,
  disclosureSyncMessage,
  onToggleNewsSummary,
  onRequestNewsSync,
  onToggleDisclosureAnalysis,
  onRequestDisclosureSync,
  compactEmptyState = false,
}) {
  const newsEmpty = !loadingNews && newsList.length === 0
  const disclosureEmpty = !loadingDisclosures && disclosureList.length === 0
  const newsScrollClassName = compactEmptyState && newsEmpty
    ? 'overflow-y-auto pr-1'
    : 'max-h-[360px] overflow-y-auto pr-1'
  const disclosureScrollClassName = compactEmptyState && disclosureEmpty
    ? 'overflow-y-auto pr-1'
    : 'max-h-[360px] overflow-y-auto pr-1'
  const newsSectionClassName = compactEmptyState && newsEmpty
    ? 'rounded-lg border border-[#1f2945]/70 bg-[#07111f]/70 p-4'
    : 'min-h-[220px] rounded-lg border border-[#1f2945]/70 bg-[#07111f]/70 p-4'
  const disclosureSectionClassName = compactEmptyState && disclosureEmpty
    ? 'rounded-lg border border-[#1f2945]/70 bg-[#07111f]/70 p-4'
    : 'min-h-[220px] rounded-lg border border-[#1f2945]/70 bg-[#07111f]/70 p-4'
  const loadingClassName = compactEmptyState
    ? 'py-5 text-center text-xs text-cyan-400/80 font-mono animate-pulse'
    : 'py-8 text-center text-xs text-cyan-400/80 font-mono animate-pulse'
  const emptyStateClassName = compactEmptyState
    ? 'flex flex-col items-center gap-3 py-5 text-center'
    : 'flex flex-col items-center gap-3 py-8 text-center'

  return (
    <>
              {isNewsDisclosureSectionActive && activeTab === 'news' && (
                <div className={newsScrollClassName}>
                  <section className={newsSectionClassName}>
                    <div className="mb-3 flex items-center justify-between gap-3 border-b border-[#1f2945]/50 pb-2">
                      <h3 className="text-sm font-bold text-cyan-200">뉴스</h3>
                      <span className="rounded-full border border-cyan-500/30 bg-cyan-950/30 px-2.5 py-1 text-[11px] font-bold text-cyan-100">
                        총 {Math.min(newsList.length, 10)}개
                      </span>
                    </div>

                    <div className="flex flex-col gap-3">
                      {loadingNews ? (
                        <div className={loadingClassName}>
                          뉴스 로드 중...
                        </div>
                      ) : newsList.length > 0 ? (
                        <>
                          {newsList.slice(0, 10).map(item => (
                            <div key={item.id} className="flex flex-col gap-2 border-b border-[#1f2945]/30 px-1 py-2 transition-all hover:bg-slate-800/10">
                              <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                                <button
                                  type="button"
                                  onClick={() => onToggleNewsSummary(item)}
                                  className="min-w-0 text-left text-xs text-[#e2e2ec] hover:text-cyan-200"
                                >
                                  <span className="block w-full max-w-full overflow-hidden text-ellipsis whitespace-nowrap pr-2 font-bold leading-5">
                                    {item.title}
                                  </span>
                                  <span className="mt-1.5 flex flex-wrap items-center gap-1.5">
                                    <span className="rounded border border-cyan-500/25 bg-cyan-950/25 px-1.5 py-0.5 text-[11px] font-bold text-cyan-200">
                                      {formatNewsSource(item.source)}
                                    </span>
                                    <span className="rounded border border-cyan-500/20 bg-cyan-950/10 px-1.5 py-0.5 text-[11px] font-[550] text-white">
                                      {formatTime(item.published_at)}
                                    </span>
                                  </span>
                                </button>
                                <div className="flex shrink-0 items-center gap-2">
                                  <button
                                    type="button"
                                    onClick={() => onToggleNewsSummary(item)}
                                    disabled={summaryLoadingId === item.id}
                                    className="rounded border border-cyan-500/30 px-2 py-1 text-[10px] font-bold text-cyan-300 transition hover:bg-cyan-950/30 disabled:cursor-not-allowed disabled:opacity-60"
                                  >
                                    {summaryLoadingId === item.id ? '\uc0dd\uc131 \uc911' : selectedNewsId === item.id ? '\uc811\uae30' : '\uc694\uc57d \ubcf4\uae30'}
                                  </button>
                                  <a
                                    href={item.url}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="rounded border border-slate-700 px-2 py-1 text-[10px] font-bold text-slate-300 transition hover:border-cyan-500/40 hover:text-white"
                                  >
                                    {'\uc6d0\ubb38 \uc5f4\uae30'}
                                  </a>
                                </div>
                              </div>
                              {selectedNewsId === item.id ? (
                                <p className="rounded border border-cyan-500/20 bg-cyan-950/20 px-3 py-2 text-[11px] leading-5 text-slate-300">
                                  {item.ai_summary || (summaryLoadingId === item.id ? '\uc694\uc57d\uc744 \uc0dd\uc131\ud558\ub294 \uc911\uc785\ub2c8\ub2e4...' : '\uc694\uc57d \ubcf4\uae30 \ubc84\ud2bc\uc744 \ub20c\ub7ec 3\uc904 \uc694\uc57d\uc744 \uc0dd\uc131\ud558\uc138\uc694.')}
                                </p>
                              ) : null}
                            </div>
                          ))}
                        </>
                      ) : (
                        <div className={emptyStateClassName}>
                          <p className="text-xs text-slate-500 font-mono">
                            해당 종목의 저장된 뉴스가 없습니다.
                          </p>
                          <button
                            type="button"
                            onClick={onRequestNewsSync}
                            disabled={newsSyncing}
                            className="rounded-lg border border-cyan-500/40 bg-cyan-950/30 px-3 py-2 text-[11px] font-bold text-cyan-300 transition hover:bg-cyan-900/40 disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            {newsSyncing ? '뉴스 수집 요청 중...' : '뉴스 수집 요청하기'}
                          </button>
                          {newsSyncMessage.text ? (
                            <p className={`max-w-[320px] text-[11px] leading-5 ${newsSyncMessage.isError ? 'text-rose-300' : 'text-cyan-300'}`}>
                              {newsSyncMessage.text}
                            </p>
                          ) : null}
                        </div>
                      )}
                    </div>
                  </section>
                </div>
              )}

              {isNewsDisclosureSectionActive && activeTab === 'disclosure' && (
                <div className={disclosureScrollClassName}>
                  <section className={disclosureSectionClassName}>
                    <div className="mb-3 flex items-center justify-between gap-3 border-b border-[#1f2945]/50 pb-2">
                      <h3 className="text-sm font-bold text-cyan-200">공시</h3>
                      <span className="rounded-full border border-cyan-500/30 bg-cyan-950/30 px-2.5 py-1 text-[11px] font-bold text-cyan-100">
                        총 {Math.min(disclosureList.length, 10)}개
                      </span>
                    </div>
                    <div className="flex flex-col gap-3">
                      {loadingDisclosures ? (
                        <div className={loadingClassName}>
                          DART 공시 로드 중...
                        </div>
                      ) : disclosureList.length > 0 ? (
                        <>
                          {disclosureList.slice(0, 10).map(item => {
                              const analysis = disclosureAnalyses[item.rcept_no]
                              const isOpen = selectedDisclosureId === item.id
                              const isLoadingAnalysis = disclosureAnalysisLoadingId === item.id
                              const risks = Array.isArray(analysis?.risk_points) ? analysis.risk_points : []
                              const metrics = Array.isArray(analysis?.metrics) ? analysis.metrics : []
                              const checkItems = Array.isArray(analysis?.check_items) ? analysis.check_items : []
                              const metricLabels = new Set(metrics.map(metric => metric?.label).filter(Boolean))
                              const duplicateCheckMetricMap = {
                                '계약 규모': ['계약금액', '매출액대비'],
                                '계약 상대': ['계약상대'],
                                '계약 기간': ['계약기간'],
                                '해지 규모': ['해지금액', '매출액대비'],
                                '해지 사유': ['해지사유'],
                                '사채 규모': ['사채의 권면총액'],
                                '전환 조건': ['전환가액', '행사가액', '교환가액', '청구금액'],
                                '청구 기간': ['전환청구기간', '행사청구기간'],
                                '최종 발행가': ['확정발행가액', '발행가액'],
                                '발행 주식 수': ['발행주식수', '신주의 수'],
                                '확정일': ['확정일'],
                                '주식 배정': ['1주당 배정'],
                                '신주 규모': ['보통주 신주', '기타주식 신주'],
                                '상장 일정': ['상장예정일', '배정기준일'],
                                '조정 기준가': ['기준가'],
                                '실시일': ['권리락 실시일'],
                                '권리락 사유': ['사유'],
                                '배당 규모': ['1주당 배당금', '시가배당율', '배당금총액'],
                                '환원 규모': ['취득예정금액', '소각예정금액', '취득예정주식'],
                                '소각 규모': ['소각예정금액', '소각예정주식'],
                                '소각 일정': ['소각예정일'],
                                '처분 규모': ['처분예정금액', '처분예정주식'],
                                '변경 후 대표': ['변경후 대표이사'],
                                '변경 사유': ['변경사유'],
                                '투자 규모': ['투자금액', '자기자본대비'],
                                '투자 목적': ['투자목적', '투자대상'],
                                '정지 규모': ['영업정지금액', '매출액대비'],
                                '정지 사유': ['영업정지사유'],
                                '감자 비율': ['감자비율'],
                                '감자 일정': ['감자기준일', '상장예정일'],
                                '분할 비율': ['분할비율'],
                                '병합 비율': ['병합비율'],
                                '거래정지 일정': ['매매거래정지기간', '신주권상장예정일'],
                                '거래정지 사유': ['거래정지사유'],
                                '정지 기간': ['거래정지일', '해제일시'],
                                '위험 사유': ['위험사유', '상장폐지사유'],
                                '심사 일정': ['심사일정', '개선기간'],
                                '발생 규모': ['발생금액', '자기자본대비'],
                                '회사 대응': ['향후대책', '발생사실'],
                                '신청 사유': ['신청사유'],
                                '법원 일정': ['관할법원', '신청일자', '결정내용'],
                                '새 최대주주': ['변경후 최대주주', '지분율'],
                                '합병 조건': ['합병비율', '합병기일'],
                                '소송 규모': ['소송가액'],
                                '보증 규모': ['채무보증금액', '자기자본대비'],
                                '보증 대상': ['채무자', '채권자'],
                                '보증 기간': ['채무보증기간'],
                                '발행 결과': ['실제발행금액', '실제발행주식수'],
                                '납입 일정': ['납입일', '상장예정일'],
                                '발행 규모': ['발행총액'],
                                '조달 목적': ['자금조달의 목적'],
                                '행사 물량': ['행사주식수', '발행주식총수 대비'],
                                '실적 규모': ['매출액', '영업이익', '당기순이익'],
                                '증감 방향': ['전년동기대비', '직전분기대비'],
                                '변동 규모': ['영업이익', '당기순이익', '전년대비'],
                                '변동 사유': ['변동사유'],
                                '계획 구체성': ['목표지표', '주주환원계획'],
                                '실행 일정': ['이행기간', '공시주기'],
                                '핵심 내용': ['주요내용', '계약금액', '전망매출액'],
                                '실현 가능성': ['추진일정', '계약상대'],
                                '답변 내용': ['답변내용', '진행사항'],
                                '후속 일정': ['답변일', '조회공시요구일'],
                              }
                              const visibleCheckItems = checkItems.filter((check) => {
                                const duplicateMetricLabels = duplicateCheckMetricMap[check?.question] || []
                                if (duplicateMetricLabels.some(label => metricLabels.has(label))) return false
                                return check?.answer && check.answer !== '확인 필요'
                              })

                              return (
                                <div key={item.id} className="flex flex-col gap-2 border-b border-[#1f2945]/30 px-1 py-2 transition-all hover:bg-slate-800/10">
                                  <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                                    <button
                                      type="button"
                                      onClick={() => onToggleDisclosureAnalysis(item)}
                                      className="min-w-0 text-left text-xs text-[#e2e2ec] hover:text-cyan-200"
                                    >
                                      <span className="block w-full max-w-full overflow-hidden text-ellipsis whitespace-nowrap pr-2 font-bold leading-5">
                                        {item.report_nm}
                                      </span>
                                      <span className="mt-1.5 flex flex-wrap items-center gap-1.5">
                                        <span className="rounded border border-cyan-500/25 bg-cyan-950/25 px-1.5 py-0.5 text-[11px] font-bold text-cyan-200">
                                          {item.corp_name || 'DART'}
                                        </span>
                                        <span className="rounded border border-cyan-500/20 bg-cyan-950/10 px-1.5 py-0.5 text-[11px] font-[550] text-white">
                                          {formatDisclosureDate(item.rcept_dt)}
                                        </span>
                                      </span>
                                    </button>
                                    <div className="flex shrink-0 items-center gap-2">
                                      <button
                                        type="button"
                                        onClick={() => onToggleDisclosureAnalysis(item)}
                                        disabled={isLoadingAnalysis}
                                        className="rounded border border-cyan-500/30 px-2 py-1 text-[10px] font-bold text-cyan-300 transition hover:bg-cyan-950/30 disabled:cursor-not-allowed disabled:opacity-60"
                                      >
                                        {isLoadingAnalysis ? '분석 중' : isOpen ? '접기' : '요약 보기'}
                                      </button>
                                      <a
                                        href={item.url}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="rounded border border-slate-700 px-2 py-1 text-[10px] font-bold text-slate-300 transition hover:border-cyan-500/40 hover:text-white"
                                      >
                                        원문 열기
                                      </a>
                                    </div>
                                  </div>
                                  {isOpen ? (
                                    <div className="rounded border border-cyan-500/20 bg-cyan-950/20 px-3 py-2 text-[11px] leading-5 text-slate-300">
                                      {isLoadingAnalysis && !analysis ? (
                                        <p className="text-cyan-300">DART 상세 공시를 확인하는 중입니다...</p>
                                      ) : analysis ? (
                                        <div className="space-y-2">
                                          <div className="flex flex-wrap items-center gap-1.5">
                                            <span className={`rounded border px-2 py-0.5 text-[11px] font-bold ${getDisclosureToneClass(analysis.sentiment)}`}>
                                              {analysis.sentiment_label || '정보'}
                                            </span>
                                            <span className="rounded border border-slate-600/60 bg-slate-900/50 px-2 py-0.5 text-[10px] font-medium text-slate-200">
                                              신뢰도 {analysis.confidence === 'high' ? '높음' : analysis.confidence === 'medium' ? '보통' : '낮음'}
                                            </span>
                                            <span className="text-[10px] text-slate-500">
                                              {analysis.analysis_source === 'OPENDART_DOCUMENT' ? 'DART 상세 기반' : '제목 기반'}
                                            </span>
                                          </div>
                                          <p className="font-bold text-slate-100">{analysis.headline}</p>
                                          {analysis.plain_summary ? (
                                            <p className="rounded border border-[#1f2945]/60 bg-slate-950/30 px-2 py-1.5 text-[11px] leading-5 text-slate-200">
                                              {analysis.plain_summary}
                                            </p>
                                          ) : null}
                                          {metrics.length > 0 ? (
                                            <div className="grid gap-1 sm:grid-cols-2">
                                              {metrics.slice(0, 6).map((metric, index) => (
                                                <div key={`${metric.label}-${index}`} className="rounded border border-[#1f2945]/60 bg-slate-950/30 px-2 py-1">
                                                  <span className="text-cyan-200">{metric.label}</span>
                                                  <span className="mx-1 text-slate-600">·</span>
                                                  <span className="text-white">{String(metric.value || '').length > 28 ? `${String(metric.value).slice(0, 28)}...` : metric.value}</span>
                                                </div>
                                              ))}
                                            </div>
                                          ) : null}
                                          {visibleCheckItems.length > 0 ? (
                                            <div className="grid gap-1 sm:grid-cols-2">
                                              {visibleCheckItems.slice(0, 3).map((check, index) => (
                                                <div key={`${check.question}-${index}`} className="rounded border border-[#1f2945]/60 bg-[#07111f]/70 px-2 py-1">
                                                  <span className="text-cyan-200">{check.question}</span>
                                                  <span className="mx-1 text-slate-600">·</span>
                                                  <span className="text-slate-100">{String(check.answer || '').length > 24 ? `${String(check.answer).slice(0, 24)}...` : check.answer}</span>
                                                </div>
                                              ))}
                                            </div>
                                          ) : null}
                                          {risks.length > 0 ? (
                                            <p className="text-amber-200/90">확인 포인트: {risks[0]}</p>
                                          ) : null}
                                        </div>
                                      ) : (
                                        <p>{item.summary || item.report_nm || '저장된 요약이 없습니다.'}</p>
                                      )}
                                    </div>
                                  ) : null}
                                </div>
                              )
                          })}
                        </>
                      ) : (
                        <div className={emptyStateClassName}>
                          <p className="text-xs text-slate-500 font-mono">
                            해당 종목의 저장된 DART 공시가 없습니다.
                          </p>
                          <button
                            type="button"
                            onClick={onRequestDisclosureSync}
                            disabled={disclosureSyncing}
                            className="rounded-lg border border-cyan-500/40 bg-cyan-950/30 px-3 py-2 text-[11px] font-bold text-cyan-300 transition hover:bg-cyan-900/40 disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            {disclosureSyncing ? '공시 수집 요청 중...' : '최근 공시 수집 요청하기'}
                          </button>
                          {disclosureSyncMessage.text ? (
                            <p className={`max-w-[320px] text-[11px] leading-5 ${disclosureSyncMessage.isError ? 'text-rose-300' : 'text-cyan-300'}`}>
                              {disclosureSyncMessage.text}
                            </p>
                          ) : null}
                        </div>
                      )}
                    </div>
                  </section>
                </div>
              )}
    </>
  )
}
