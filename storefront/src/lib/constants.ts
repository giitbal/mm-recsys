// A missing catalog image also needs to render in the standalone Docker build.
export const PLACEHOLDER_IMAGE = "data:image/svg+xml," + encodeURIComponent(
  '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 160 160"><rect width="160" height="160" fill="#f5f5f5"/><text x="80" y="84" text-anchor="middle" font-size="14" fill="#555">이미지 없음</text></svg>'
)
