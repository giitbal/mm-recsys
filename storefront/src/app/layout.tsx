import type { Metadata } from "next"
import { Toaster } from "sonner"
import "./globals.css"
export const metadata: Metadata = { title: "MM Shop · 나를 위한 발견", description: "멀티모달 검색과 개인화 추천 쇼핑 데모" }
export default function Layout({children}: {children: React.ReactNode}) {
  return <html lang="ko" className="h-full antialiased"><body className="min-h-full flex flex-col bg-white">{children}<Toaster richColors position="bottom-right" /></body></html>
}
