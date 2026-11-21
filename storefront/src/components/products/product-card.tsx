"use client"

import Link from "next/link"
import Image from "next/image"
import { Heart } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { formatPrice } from "@/lib/utils"
import { PLACEHOLDER_IMAGE } from "@/lib/constants"
import { useWishlistStore } from "@/store/wishlist"
import { useHydrated } from "@/lib/use-hydrated"
import { toast } from "sonner"
import type { Product } from "@/types"

interface ProductCardProps {
  product: Product
}

export function ProductCard({ product }: ProductCardProps) {
  const defaultVariant = product.variants[0]
  const image = product.images[0]

  const wishlistItems = useWishlistStore((s) => s.items)
  const addItem = useWishlistStore((s) => s.addItem)
  const removeItem = useWishlistStore((s) => s.removeItem)

  const mounted = useHydrated()
  const isWishlisted = mounted && wishlistItems.some((i) => i.productId === product.id)
  if (!defaultVariant) return null
  const price = defaultVariant.price
  const compareAtPrice = defaultVariant.compareAtPrice
  const isOnSale = compareAtPrice && compareAtPrice > price

  function handleWishlist(e: React.MouseEvent) {
    e.preventDefault()
    e.stopPropagation()
    if (isWishlisted) {
      removeItem(product.id)
      toast("관심 상품에서 삭제했습니다")
    } else {
      addItem({
        productId: product.id,
        name: product.name,
        slug: product.slug,
        price,
        image: image ?? { url: PLACEHOLDER_IMAGE, alt: product.name },
      })
      toast.success("관심 상품에 추가했습니다")
    }
  }

  return (
    <Link href={`/product/${product.slug}${product.exposure ? `?rid=${encodeURIComponent(product.exposure.requestId)}&uid=${encodeURIComponent(product.exposure.userId)}` : ""}`} className="group">
      <div className="relative aspect-square overflow-hidden rounded-lg bg-neutral-100">
        <Image
          src={image?.url ?? PLACEHOLDER_IMAGE}
          alt={image?.alt ?? product.name}
          fill
          className="object-cover transition-transform duration-300 group-hover:scale-105"
          sizes="(max-width: 768px) 50vw, (max-width: 1200px) 33vw, 25vw"
        />
        {isOnSale && (
          <Badge
            variant="secondary"
            className="absolute top-3 left-3 bg-white text-xs"
          >
            Sale
          </Badge>
        )}
        <button
          onClick={handleWishlist}
          className="absolute top-2 right-2 z-10 flex h-11 w-11 items-center justify-center rounded-full bg-white shadow-sm transition-opacity hover:bg-neutral-50 sm:opacity-0 sm:group-hover:opacity-100"
          aria-label={isWishlisted ? "관심 상품 삭제" : "관심 상품 추가"}
        >
          <Heart
            className={`h-4 w-4 ${isWishlisted ? "fill-current text-wishlist" : "text-neutral-600"}`}
          />
        </button>
      </div>
      <div className="mt-3">
        <p className="text-xs text-muted-foreground">{product.brandId} · {product.tags[0]}</p>
        <h3 className="mt-1 text-sm font-medium text-foreground group-hover:underline">
          {product.name}
        </h3>
        <div className="mt-1 flex items-center gap-2">
          <span className="text-sm font-medium">
            {formatPrice(price, defaultVariant.currency)}
          </span>
          {isOnSale && (
            <span className="text-xs text-muted-foreground line-through">
              {formatPrice(compareAtPrice, defaultVariant.currency)}
            </span>
          )}
        </div>
        {product.variants.length > 1 && (
          <p className="mt-1 text-xs text-muted-foreground">
            {product.variants.length} options
          </p>
        )}
      </div>
    </Link>
  )
}
