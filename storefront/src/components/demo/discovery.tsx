"use client"
import { useEffect, useRef, useState } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { ProductGrid } from "@/components/products/product-grid"
import { enrich, live, session } from "@/lib/live"
import { useCartStore } from "@/store/cart"
import type { Product } from "@/types"
type Recommendation = {recommendations: {product_id: string; reason: string}[]; pipeline_latency: {total_ms: number}; session_context: {session_interest?: string}}
type Search = {results: {product_id: string}[]; latency_ms: number; search_type: string}
export function Discovery({mode, initialQuery = ""}: {mode: "search" | "recommend"; initialQuery?: string}) {
  const [user, setUser] = useState("U000001"), [query, setQuery] = useState(initialQuery)
  const [file, setFile] = useState<File | null>(null), [products, setProducts] = useState<Product[]>([])
  const [busy, setBusy] = useState(false), [error, setError] = useState(""), [info, setInfo] = useState("")
  const [done, setDone] = useState(false)
  const active = useRef(false)
  const form = useRef<HTMLFormElement>(null)
  const submitted = useRef(false)
  useEffect(() => {
    if (initialQuery && !submitted.current) {
      submitted.current = true
      form.current?.requestSubmit()
    }
  }, [initialQuery])
  useEffect(() => {setUser(session().userId)}, [])
  async function run(event: React.FormEvent) {
    event.preventDefault(); if (active.current) return; active.current = true
    setBusy(true); setError(""); setProducts([]); setInfo(""); setDone(false)
    try {
      if (mode === "recommend") {
        const uid = user.trim()
        if (!uid) throw new Error("사용자 ID를 입력하세요.")
        if (session().userId !== uid) { useCartStore.getState().clearCart(); sessionStorage.setItem("mm-user", uid); sessionStorage.removeItem("mm-session") }
        const {data, requestId} = await live<Recommendation>(`/api/recommend?user_id=${encodeURIComponent(uid)}&top_n=12`)
        const rows = await enrich(data.recommendations.map(item => item.product_id))
        setProducts(rows.map(item => ({...item, exposure: requestId ? {requestId, userId: uid} : undefined})))
        setInfo(`추천 ${rows.length}개 · API 처리 ${data.pipeline_latency.total_ms.toFixed(1)}ms · 세션 관심: ${data.session_context.session_interest || "아직 없음"}${requestId ? " · 노출 기록됨" : " · CT 노출 기록 비활성"}`)
      } else {
        if (!query.trim() && !file) throw new Error("검색어나 이미지를 입력하세요.")
        const payload: {query_text?: string; query_image?: string; top_k: number} = {top_k: 24}
        if (query.trim()) payload.query_text = query.trim()
        if (file) {
          if (file.size > 5_000_000) throw new Error("이미지는 5MB 이하로 선택하세요.")
          payload.query_image = await new Promise<string>((resolve, reject) => {const reader = new FileReader(); reader.onload = () => resolve(String(reader.result)); reader.onerror = () => reject(new Error("이미지를 읽을 수 없습니다.")); reader.readAsDataURL(file)})
        }
        const {data} = await live<Search>("/api/search", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(payload)})
        setProducts(await enrich(data.results.map(item => item.product_id)))
        setInfo(`${{text: "텍스트", image: "이미지", hybrid: "복합"}[data.search_type] || data.search_type} 검색 · API 처리 ${data.latency_ms.toFixed(1)}ms`)
      }
      setDone(true)
    } catch (e) { setError(e instanceof Error ? e.message : "요청 실패") }
    finally {setBusy(false); active.current = false}
  }
  return <div className="mx-auto max-w-[1440px] px-4 py-12 sm:px-6 lg:px-8"><h1 className="text-3xl font-bold">{mode === "search" ? "어떤 상품을 찾으세요?" : "나를 위한 추천"}</h1><p className="mt-3 text-muted-foreground">{mode === "search" ? "검색어, 사진, 또는 두 가지를 함께 사용해 보세요." : "상품을 살펴보고 다시 추천받으면 현재 행동을 반영한 결과를 비교할 수 있습니다."}</p>
    <form ref={form} onSubmit={run} className="my-8 flex flex-wrap items-end gap-4 rounded-xl border bg-neutral-50 p-6">
      {mode === "recommend" ? <label className="flex-1 space-y-2 text-sm">사용자 ID<Input value={user} maxLength={100} onChange={e => setUser(e.target.value)} disabled={busy}/></label> : <><label className="min-w-48 flex-1 space-y-2 text-sm">검색어<Input value={query} onChange={e => setQuery(e.target.value)} placeholder="예: 검정 가방" disabled={busy}/></label><label className="space-y-2 text-sm">검색 이미지<Input type="file" accept="image/*" disabled={busy} onChange={e => setFile(e.target.files?.[0] || null)}/></label></>}
      <Button type="submit" size="lg" disabled={busy}>{busy ? "불러오는 중…" : mode === "search" ? "검색하기" : "추천받기"}</Button>
    </form>
    {error && <p role="alert" className="mb-6 rounded-lg border border-red-200 bg-red-50 p-4 text-red-800">{error}</p>}
    {info && <div role="status" className="mb-6 text-sm text-muted-foreground">{info}<span className="ml-2">(이번 요청의 처리 시간)</span></div>}
    {busy ? <div role="status" className="py-20 text-center text-muted-foreground">상품을 찾고 있습니다…</div> : done ? <ProductGrid products={products}/> : <div className="rounded-xl border border-dashed py-20 text-center text-muted-foreground">{mode === "search" ? "검색하면 실제 상품 결과가 여기에 표시됩니다." : "사용자를 선택하고 추천받기를 눌러 주세요."}</div>}
  </div>
}
