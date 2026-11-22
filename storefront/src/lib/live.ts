import type { Product } from "@/types"
export async function live<T>(path: string, init?: RequestInit): Promise<{data: T; requestId: string | null}> {
  const response = await fetch("/api/live" + path, {...init, cache: "no-store"})
  const data = await response.json()
  if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : `API 오류 (${response.status})`)
  return { data, requestId: response.headers.get("X-Recommendation-Request-ID") }
}
export function session() {
  const userId = sessionStorage.getItem("mm-user") || "U000001"
  let sessionId = sessionStorage.getItem("mm-session")
  if (!sessionId) { sessionId = "shop-" + crypto.randomUUID(); sessionStorage.setItem("mm-session", sessionId) }
  return {userId, sessionId}
}
export async function recordEvent(productId: string, kind: "view" | "cart" | "purchase", exposure?: Product["exposure"], actionId?: string) {
  const {userId, sessionId} = session()
  const key = `mm-pending:${userId}:${sessionId}:${productId}:${kind}`
  let saved = sessionStorage.getItem(key)
  if (!saved) {
    saved = JSON.stringify({payload: {event_id: actionId || crypto.randomUUID(), user_id: userId, product_id: productId, event_type: kind, session_id: sessionId}, requestId: exposure?.userId === userId ? exposure.requestId : undefined})
    sessionStorage.setItem(key, saved)
  }
  const pending = JSON.parse(saved)
  const result = await live(kind === "purchase" ? "/api/feedback" : "/api/event", {
    method: "POST", headers: {"Content-Type": "application/json", ...(pending.requestId ? {"X-Recommendation-Request-ID": pending.requestId} : {})}, body: JSON.stringify(pending.payload),
  })
  sessionStorage.removeItem(key)
  return result
}
export async function enrich(ids: string[]): Promise<Product[]> {
  if (!ids.length) return []
  return (await live<{items: Product[]}>(`/api/storefront/products?limit=100&ids=${encodeURIComponent(ids.join(","))}`)).data.items
}
