import { Header } from "@/components/layout/header"
import { CartDrawer } from "@/components/cart/cart-drawer"
export const dynamic = "force-dynamic"
export default function Layout({children}: {children: React.ReactNode}) {
  return <><a href="#main-content" className="sr-only focus:not-sr-only">본문으로 이동</a>
    <div className="bg-neutral-900 px-4 py-2 text-center text-xs text-white">나의 취향을 발견하는 쇼핑 · 시뮬레이터 상품으로 체험하는 데모 스토어</div>
    <Header/><main id="main-content" className="flex-1">{children}</main><CartDrawer/>
    <footer className="border-t px-6 py-10 text-sm text-muted-foreground"><div className="mx-auto flex max-w-[1440px] flex-wrap justify-between gap-4"><span>MM Shop · 실제 결제 없는 쇼핑 데모</span><a href="https://github.com/Epic-Design-Labs/nextjs-ecommerce-starter" target="_blank" rel="noreferrer">Template by Epic Design Labs · MIT</a></div></footer></>
}
