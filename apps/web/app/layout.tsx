import type { Metadata } from "next";
import "./globals.css";
import { Providers } from "@/components/Providers";
import { Nav } from "@/components/Nav";

export const metadata: Metadata = {
  title: "Upbit Strategy Lab",
  description: "업비트 현물 전략 백테스트 연구 도구",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ko" className="h-full antialiased">
      <body className="min-h-full">
        <Providers>
          <div className="flex min-h-screen">
            <Nav />
            <main className="flex-1 min-w-0 p-4 lg:p-6">{children}</main>
          </div>
          <footer className="border-t border-line px-6 py-3 text-xs text-muted">
            Upbit Strategy Lab은 연구·검증 도구입니다. 표시되는 모든 결과는 과거 데이터 기반
            시뮬레이션이며 투자 추천이 아닙니다. 실제 투자 손실에 대한 책임은 이용자에게 있습니다.
          </footer>
        </Providers>
      </body>
    </html>
  );
}
