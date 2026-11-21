import { backend } from "@/lib/backend"
import type { Category, PaginatedResult, PaginationParams, Product, SortOption } from "@/types"

export const categoryRepository = { list: () => backend<Category[]>("/api/storefront/categories") }

async function list(category?: string, sort?: SortOption, pagination?: PaginationParams) {
  const query = new URLSearchParams({ page: String(pagination?.page ?? 1), limit: String(pagination?.limit ?? 24) })
  if (category) query.set("category", category)
  if (sort) query.set("sort", sort.field === "price" ? `price-${sort.order}` : sort.field === "name" ? "name" : "newest")
  return backend<PaginatedResult<Product>>(`/api/storefront/products?${query}`)
}

export const productRepository = {
  list,
  async getFeatured(limit = 4) { return (await list(undefined, undefined, {page: 1, limit})).items },
}
