import { backend } from "@/lib/backend"
import type { Product } from "@/types"
import { ProductDetail } from "@/components/demo/product-detail"
export default async function Page({params, searchParams}: {params: Promise<{id: string}>; searchParams: Promise<{rid?: string; uid?: string}>}) {
  const {id} = await params; const {rid, uid} = await searchParams
  const product = await backend<Product>(`/api/storefront/products/${encodeURIComponent(id)}`)
  return <ProductDetail key={JSON.stringify([id, rid, uid])} product={{...product, exposure: rid && uid ? {requestId: rid, userId: uid} : undefined}}/>
}
