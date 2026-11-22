// --- Product ---

export type ProductStatus = "draft" | "active" | "archived"

export interface ProductImage {
  url: string
  alt: string
  width?: number
  height?: number
}

export interface ProductOption {
  name: string // e.g., "Color", "Size"
  value: string // e.g., "Black", "M"
}

export interface VariantInventory {
  quantity: number
  trackInventory: boolean
  allowBackorder: boolean
}

export interface ProductVariant {
  id: string
  productId: string
  sku: string
  name: string
  price: number // in cents
  compareAtPrice?: number // original price for sale display
  currency: string
  inventory: VariantInventory
  options: ProductOption[]
  images: ProductImage[]
  weight?: number
  dimensions?: { length: number; width: number; height: number }
}

export interface Product {
  exposure?: { requestId: string; userId: string }
  id: string
  name: string
  slug: string
  /** Short blurb shown in the product info column (1–2 sentences) */
  description: string
  /** Full HTML description shown below gallery/add-to-cart (.blog-body prose) */
  body?: string
  images: ProductImage[]
  status: ProductStatus
  brandId: string
  categoryIds: string[]
  tags: string[]
  variants: ProductVariant[]
  rating: number
  reviewCount: number
  featured: boolean
  createdAt: string
  updatedAt: string
}

// --- Category ---

export interface Category {
  id: string
  name: string
  slug: string
  description: string
  image?: ProductImage
  parentId?: string
  order: number
}

// --- Cart ---

export interface CartItem {
  exposure?: { requestId: string; userId: string }
  id: string
  variantId: string
  productId: string
  name: string
  variantName: string
  image: ProductImage
  slug: string
  price: number
  quantity: number
  lineTotal: number
}

// --- Pagination ---

export interface PaginationParams {
  page: number
  limit: number
}

export interface PaginationMeta {
  total: number
  page: number
  limit: number
  totalPages: number
  hasNext: boolean
  hasPrev: boolean
}

export interface PaginatedResult<T> {
  items: T[]
  pagination: PaginationMeta
}

// --- Filtering & Sorting ---

export type SortOrder = "asc" | "desc"

export interface SortOption {
  field: string
  order: SortOrder
}
