"use client"
// Adapted from Epic Design Labs Header; original sticky header and action layout retained.
import Link from "next/link"
import { Search, ShoppingBag, Menu } from "lucide-react"
import { useState } from "react"
import { useHydrated } from "@/lib/use-hydrated"
import { useCartStore } from "@/store/cart"
import { Sheet, SheetContent, SheetTitle, SheetTrigger } from "@/components/ui/sheet"
const links = [["전체 상품", "/shop"], ["나를 위한 추천", "/recommend"], ["이미지로 찾기", "/search"], ["A/B · CT 운영", "/operations"]]
export function Header() {
  const mounted = useHydrated()
  const [open, setOpen] = useState(false)
  const cart = useCartStore()
  return <header className="sticky top-0 z-50 w-full border-b bg-white/95 backdrop-blur supports-[backdrop-filter]:bg-white/60">
    <div className="mx-auto flex h-16 max-w-[1440px] items-center justify-between px-4 sm:px-6 lg:px-8">
      <Sheet open={open} onOpenChange={setOpen}><SheetTrigger className="p-2 lg:hidden" aria-label="메뉴 열기"><Menu className="h-5 w-5"/></SheetTrigger><SheetContent side="left"><SheetTitle className="p-6">MM Shop</SheetTitle><nav className="flex flex-col gap-6 px-6">{links.map(([name, href]) => <Link key={href} href={href} onClick={() => setOpen(false)}>{name}</Link>)}</nav></SheetContent></Sheet>
      <Link href="/" className="text-xl font-semibold tracking-tight">MM Shop<span className="ml-1 text-orange-500">.</span></Link>
      <nav className="hidden gap-6 lg:flex">{links.map(([name, href]) => <Link key={href} href={href} className="text-sm font-medium hover:text-neutral-500">{name}</Link>)}</nav>
      <div className="flex items-center"><Link href="/search" className="inline-flex h-10 w-10 items-center justify-center rounded-md hover:bg-accent" aria-label="상품 검색"><Search className="h-5 w-5"/></Link><button onClick={cart.openCart} className="relative inline-flex h-10 w-10 items-center justify-center rounded-md hover:bg-accent" aria-label="장바구니 열기"><ShoppingBag className="h-5 w-5"/>{mounted && cart.getItemCount() > 0 && <span className="absolute -top-0.5 -right-0.5 flex h-4 w-4 items-center justify-center rounded-full bg-foreground text-[10px] text-background">{cart.getItemCount()}</span>}</button></div>
    </div></header>
}
