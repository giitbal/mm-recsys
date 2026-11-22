import "server-only"
export const apiOrigin = () => (process.env.API_URL || "http://127.0.0.1:8000").replace(/\/$/, "")
export async function backend<T>(path: string): Promise<T> {
  const response = await fetch(apiOrigin() + path, { cache: "no-store", signal: AbortSignal.timeout(30000) })
  if (!response.ok) throw new Error(`API ${response.status}: ${await response.text()}`)
  return response.json()
}
