export const siteConfig = {
  url: process.env.NEXT_PUBLIC_BASE_URL ?? "http://localhost:3000",
  currency: "KRW",
  locale: "ko-KR",
} as const
