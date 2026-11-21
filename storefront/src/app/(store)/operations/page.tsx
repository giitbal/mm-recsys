"use client"
import { useEffect, useState } from "react"
import { live } from "@/lib/live"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
type Arm = {users: number; ctr: number | null; cvr: number | null}
type Operations = {
  data_fingerprint: string; search_ready: boolean; recommend_ready: boolean
  ab: {status: string; reason?: string; days?: number; source?: string; arms?: Record<string, Arm>; inference?: {cvr: {relative_lift: number | null; difference_ci95?: number[]; z_p_value?: number | null}}}
  ct: {enabled: boolean; serving_version: string; active?: string; new_events?: number; threshold?: number; logs?: {rows: Record<string, unknown>[]; invalid_lines: number}; versions?: {version: string; status: string; date: string}[]}
}
const percent = (value: number | null | undefined) => value == null ? "미측정" : `${(value*100).toFixed(2)}%`
const labels: Record<string, string> = {initialized: "초기 모델 등록", training_started: "재학습 시작", registered: "후보 모델 등록", promoted: "새 모델 승격", retained: "기존 모델 유지", reloaded: "API 모델 교체", rollback: "이전 모델 복구", training_failed: "재학습 실패", monitor: "모니터링", WAITING_FOR_LABELS: "학습 라벨 대기", WAITING: "이벤트 누적 대기"}
export default function OperationsPage() {
  const [data, setData] = useState<Operations | null>(null), [error, setError] = useState(""), [busy, setBusy] = useState(false), [at, setAt] = useState("")
  async function refresh() {
    setBusy(true)
    try {setData((await live<Operations>("/api/storefront/operations")).data); setAt(new Date().toLocaleTimeString("ko-KR")); setError("")}
    catch (e) {setError(e instanceof Error ? e.message : "상태 조회 실패")}
    finally {setBusy(false)}
  }
  useEffect(() => {void refresh()}, [])
  const lift = data?.ab.inference?.cvr.relative_lift
  return <div className="mx-auto max-w-[1440px] px-4 py-12 sm:px-6 lg:px-8"><div className="flex flex-wrap items-center justify-between gap-4"><div><h1 className="text-3xl font-bold">스토어 운영</h1><p className="mt-2 text-muted-foreground">A/B 실험 결과와 현재 CT 실행 상태</p></div><Button onClick={refresh} disabled={busy}>{busy ? "조회 중…" : "상태 새로고침"}</Button></div>{error && <p role="alert" className="my-6 rounded-lg bg-red-50 p-4 text-red-800">{error} {data && "아래는 마지막으로 성공한 조회 결과입니다."}</p>}
    {data && <><p className="mt-4 text-xs text-muted-foreground">마지막 조회 {at} · 현재 API 상태와 저장된 실험 결과는 측정 시점이 다릅니다.</p>
      <div className="my-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">{[["검색 API", data.search_ready ? "준비됨" : "준비 중"], ["추천 API", data.recommend_ready ? "준비됨" : "준비 중"], ["서비스 모델", data.ct.serving_version], ["CT 신규 이벤트", data.ct.enabled ? (data.ct.new_events || 0).toLocaleString() : "비활성"]].map(([title, value]) => <Card key={title}><CardHeader><CardTitle className="text-sm text-muted-foreground">{title}</CardTitle></CardHeader><CardContent className="text-2xl font-semibold">{value}</CardContent></Card>)}</div>
      <Card className="mb-8"><CardHeader><CardTitle>A/B 실험 · 저장된 합성 실험</CardTitle></CardHeader><CardContent>
        {data.ab.status !== "MEASURED" ? <p className="text-muted-foreground">{data.ab.reason || "미측정"}</p> : <><p className="mb-6 text-sm text-muted-foreground">{data.ab.days}일 실험 · CTR = 클릭/노출 · CVR = 구매/노출</p><div className="grid gap-8 md:grid-cols-2">{Object.entries(data.ab.arms || {}).map(([name, arm]) => <div key={name}><h3 className="font-semibold">{name === "control" ? "Control · 대조군" : "Treatment · 실험군"}</h3><p className="my-2 text-sm text-muted-foreground">사용자 {arm.users.toLocaleString()}명</p>{([['CTR', arm.ctr], ['CVR', arm.cvr]] as const).map(([metric, value]) => <div key={metric} className="my-4"><div className="mb-2 flex justify-between text-sm"><span>{metric}</span><span>{percent(value)}</span></div><div className="h-3 rounded bg-neutral-100"><div className={`h-3 rounded ${name === "control" ? "bg-neutral-400" : "bg-orange-500"}`} style={{width: `${Math.max(0, Math.min(100, (value || 0)*100))}%`}}/></div></div>)}</div>)}</div><div className="mt-6 border-t pt-6"><p className="text-lg font-semibold">CVR 상대 변화 {percent(lift)}</p><p className="mt-2 text-sm text-muted-foreground">{lift != null && lift < 0 ? "실험군의 CVR이 낮았습니다. 개선으로 표시하지 않습니다." : "합성 실험 결과이며 실제 고객 대상 효과를 의미하지 않습니다."}</p>{data.ab.inference?.cvr.difference_ci95 && <p className="mt-2 text-sm">CVR 차이 95% 신뢰구간: {data.ab.inference.cvr.difference_ci95.map(value => `${(value*100).toFixed(3)}%p`).join(" ~ ")} · p-value: {data.ab.inference.cvr.z_p_value ?? "미측정"}</p>}</div></>}
      </CardContent></Card>
      <Card><CardHeader><CardTitle>CT · 수집에서 모델 교체까지</CardTitle></CardHeader><CardContent>{data.ct.enabled ? <><div className="mb-6 flex flex-wrap gap-3 text-sm">{["행동 수집", "라벨·학습 조건 확인", "재학습·평가", "승격 또는 유지", "API 교체"].map((name, index) => <span key={name} className="rounded-full border px-4 py-2">{index+1}. {name}</span>)}</div><p className="text-sm">신규 이벤트 {data.ct.new_events?.toLocaleString()} / 트리거 기준 {data.ct.threshold?.toLocaleString()}</p><p className="my-3 text-sm text-muted-foreground">이벤트 수 외에 시간 분할과 양성·음성 라벨 조건을 충족해야 학습할 수 있습니다. 승격은 평가 결과에 따라 결정됩니다.</p><div className="my-5 flex flex-wrap gap-3">{data.ct.versions?.map(version => <span key={version.version} className="rounded-lg bg-neutral-100 px-4 py-3 text-sm">{version.version} · {version.status}</span>)}</div><ol className="divide-y">{[...(data.ct.logs?.rows || [])].reverse().map((row, index) => <li key={index} className="flex flex-wrap justify-between gap-3 py-4 text-sm"><span>{labels[String(row.event)] || labels[String(row.status)] || String(row.event || row.status || "기록")} {String(row.version || "")}</span><time className="text-muted-foreground">{row.at ? new Date(String(row.at)).toLocaleString("ko-KR") : "시각 없음"}</time><details className="w-full text-xs text-muted-foreground"><summary className="cursor-pointer">실행 근거</summary><pre className="mt-3 max-h-64 overflow-auto whitespace-pre-wrap break-all">{JSON.stringify(row, null, 2)}</pre></details></li>)}</ol>{!data.ct.logs?.rows.length && <p>CT 실행 기록이 아직 없습니다.</p>}{!!data.ct.logs?.invalid_lines && <p role="alert">읽을 수 없는 로그 {data.ct.logs.invalid_lines}개가 있습니다.</p>}</> : <p>현재 API의 CT가 비활성화되어 있습니다.</p>}</CardContent></Card>
      <details className="mt-8 text-xs text-muted-foreground"><summary>배포·측정 근거</summary><p className="mt-3 break-all">상품 데이터 fingerprint: {data.data_fingerprint}</p><p className="break-all">A/B 결과: {data.ab.source || "연결된 결과 없음"}</p><p>CT registry 활성 버전: {data.ct.active || "없음"}</p></details>
    </>}
  </div>
}
