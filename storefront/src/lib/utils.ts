import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"
import { siteConfig } from "@/lib/config"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function formatPrice(
  amount: number,
  currency?: string
): string {
  return new Intl.NumberFormat(siteConfig.locale, {
    style: "currency",
    currency: currency ?? siteConfig.currency,
  }).format(amount)
}
