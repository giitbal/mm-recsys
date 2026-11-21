"use client"
export default function ErrorPage({reset}: {reset: () => void}) {
  return <div role="alert" className="mx-auto max-w-xl px-6 py-24"><h1 className="text-2xl font-semibold">상품 서비스를 준비하고 있습니다</h1><p className="my-4">API 연결과 데이터 준비 상태를 확인한 후 다시 시도하세요.</p><button onClick={reset} className="rounded-md bg-black px-5 py-3 text-white">다시 시도</button></div>
}
