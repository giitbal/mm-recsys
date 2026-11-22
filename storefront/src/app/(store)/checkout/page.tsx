"use client"
import { useRef, useState } from "react"
import { useHydrated } from "@/lib/use-hydrated"
import Link from "next/link"
import { useCartStore } from "@/store/cart"
import { recordEvent } from "@/lib/live"
import { formatPrice } from "@/lib/utils"
import { Button } from "@/components/ui/button"
export default function Checkout() {
  const cart = useCartStore(); const [busy, setBusy] = useState(false), [error, setError] = useState(""), [bought, setBought] = useState(0)
  const mounted = useHydrated()
  const active = useRef(false)
  async function purchase() {
    if (active.current) return; active.current = true; setBusy(true); setError("")
    try {
      for (const item of [...cart.items]) {
        await recordEvent(item.productId, "purchase", item.exposure)
        cart.removeItem(item.variantId); setBought(count => count + 1)
      }
    } catch (e) {setError(e instanceof Error ? e.message : "구매 기록 실패")}
    finally {active.current = false; setBusy(false)}
  }
  return <div className="mx-auto max-w-2xl px-6 py-16"><h1 className="text-3xl font-bold">데모 구매</h1><p className="my-4 text-muted-foreground">실제 결제나 배송 없이 상품별 구매 이벤트를 기록합니다.</p>{mounted && <><div className="my-8 divide-y rounded-xl border px-6">{cart.items.map(item => <div key={item.id} className="flex justify-between gap-4 py-5"><span>{item.name} × {item.quantity}</span><span>{formatPrice(item.lineTotal)}</span></div>)}</div>{cart.items.length > 0 && <><p className="my-4 text-right text-xl font-semibold">합계 {formatPrice(cart.getSubtotal())}</p><Button size="lg" className="w-full" disabled={busy} onClick={purchase}>{busy ? "기록 중…" : "구매 이벤트 기록"}</Button></>}{bought > 0 && <p role="status" className="my-6 rounded-lg bg-green-50 p-4 text-green-800">{bought}개 상품의 구매 기록 완료</p>}{!cart.items.length && !bought && <p>장바구니가 비어 있습니다.</p>}</>}{error && <p role="alert" className="mt-4 text-red-700">{error} · 남은 상품으로 다시 시도하세요.</p>}<Link href="/recommend" className="mt-8 inline-block underline">다시 추천받기 →</Link></div>
}
