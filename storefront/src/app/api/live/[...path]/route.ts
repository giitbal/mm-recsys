import { apiOrigin } from "@/lib/backend"
type Context = { params: Promise<{path: string[]}> }
async function proxy(request: Request, context: Context) {
  const { path: segments } = await context.params
  const path = "/" + segments.map(encodeURIComponent).join("/")
  const getAllowed = /^\/(health|ready|api\/recommend|api\/storefront\/(products|categories|operations|products\/[\w-]+|images\/[\w-]+))$/.test(path)
  const postAllowed = ["/api/search", "/api/event", "/api/feedback"].includes(path)
  if (!(request.method === "GET" ? getAllowed : postAllowed)) return Response.json({detail: "허용되지 않은 경로"}, {status: 404})
  if (request.method === "POST") {
    const origin = request.headers.get("origin")
    // Standalone Next.js uses the container port in request.url. Host retains the browser's published port.
    const expectedOrigin = `${new URL(request.url).protocol}//${request.headers.get("host")}`
    if (origin && origin !== expectedOrigin) return Response.json({detail: "다른 출처의 요청은 허용하지 않습니다."}, {status: 403})
  }
  const headers = new Headers({"Content-Type": "application/json"})
  const attribution = request.headers.get("X-Recommendation-Request-ID")
  if (attribution) headers.set("X-Recommendation-Request-ID", attribution)
  try {
    let body: string | undefined
    if (request.method === "POST") {
      const limit = 7_000_000
      if (Number(request.headers.get("content-length")) > limit) return new Response(null, {status: 413})
      const reader = request.body?.getReader()
      const chunks: Uint8Array[] = []; let bytes = 0
      if (reader) while (true) {
        const {done, value} = await reader.read(); if (done) break
        bytes += value.byteLength
        if (bytes > limit) { await reader.cancel(); return new Response(null, {status: 413}) }
        chunks.push(value)
      }
      body = Buffer.concat(chunks).toString("utf8")
    }
    const result = await fetch(apiOrigin() + path + new URL(request.url).search, {
      method: request.method, headers, body, cache: "no-store", signal: AbortSignal.timeout(60000), redirect: "error",
    })
    const returned = new Headers({"Cache-Control": "no-store"})
    for (const key of ["Content-Type", "X-Recommendation-Request-ID"]) {
      const value = result.headers.get(key); if (value) returned.set(key, value)
    }
    return new Response(result.body, {status: result.status, headers: returned})
  } catch {
    return Response.json({detail: "검색·추천 API에 연결할 수 없습니다. 서비스 준비 상태를 확인하세요."}, {status: 503})
  }
}
export const GET = proxy
export const POST = proxy
