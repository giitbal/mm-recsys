"use client"
// Original template gallery/info columns and cart interaction, connected to API events.
import { useCallback, useEffect, useRef, useState } from "react"
import Link from "next/link"
import { ShoppingBag } from "lucide-react"
import { ProductGallery } from "@/components/products/product-gallery"
import { Button } from "@/components/ui/button"
import { Separator } from "@/components/ui/separator"
import { useCartStore } from "@/store/cart"
import { recordEvent } from "@/lib/live"
import { formatPrice } from "@/lib/utils"
import type { Product } from "@/types"
export function ProductDetail({product}: {product: Product}) {
  const [error, setError] = useState(""), [busy, setBusy] = useState(false), [viewed, setViewed] = useState(false)
  const viewId = useRef<string | null>(null), adding = useRef(false)
  const cart = useCartStore(); const variant = product.variants[0]
  const view = useCallback(async () => {
    if (!viewId.current) viewId.current = crypto.randomUUID()
    try { await recordEvent(product.id, "view", product.exposure, viewId.current); setViewed(true); setError("") }
    catch (e) {setError(e instanceof Error ? e.message : "조회 기록 실패")}
  }, [product.id, product.exposure])
  useEffect(() => {void view()}, [view])
  async function add() {
    if (adding.current) return; adding.current = true; setBusy(true); setError("")
    try {
      await recordEvent(product.id, "cart", product.exposure)
      cart.addItem({productId: product.id, variantId: variant.id, name: product.name, variantName: variant.name, slug: product.slug, image: product.images[0], price: variant.price, exposure: product.exposure})
      cart.openCart()
    } catch (e) {setError(e instanceof Error ? e.message : "장바구니 기록 실패")}
    finally {adding.current = false; setBusy(false)}
  }
  return <div className="mx-auto max-w-[1440px] px-4 py-8 sm:px-6 lg:px-8"><Link href="/shop" className="text-sm text-muted-foreground">전체 상품 / {product.tags[0]}</Link><div className="mt-4 grid gap-8 lg:grid-cols-2 lg:gap-16"><ProductGallery images={product.images} productName={product.name}/><div className="flex flex-col"><p className="text-sm text-muted-foreground">{product.brandId}</p><h1 className="mt-2 text-2xl font-bold tracking-tight sm:text-3xl">{product.name}</h1><p className="mt-4 text-2xl font-semibold">{formatPrice(variant.price)}</p><p className="my-6 text-muted-foreground">{product.description}</p><div className="mb-6 flex flex-wrap gap-2">{product.tags.map(tag => <span key={tag} className="rounded-full bg-neutral-100 px-3 py-1 text-xs">{tag}</span>)}</div><Button size="lg" disabled={busy} onClick={add}><ShoppingBag className="mr-2 h-4 w-4"/>{busy ? "기록 중…" : "장바구니 담기"}</Button><Separator className="my-6"/><p className="text-sm text-muted-foreground">시뮬레이터가 만든 상품입니다. 구매는 실제 결제 없이 데모 이벤트로 기록됩니다.</p>{viewed && <p className="mt-3 text-sm text-muted-foreground">상품 조회가 기록되었습니다.</p>}{error && <div role="alert" className="mt-4 text-red-700">{error}{!viewed && <button onClick={view} className="ml-3 underline">조회 기록 재시도</button>}</div>}<Link href="/recommend" className="mt-6 text-sm underline">현재 행동으로 다시 추천받기 →</Link></div></div></div>
}
