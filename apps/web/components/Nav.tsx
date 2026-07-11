"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const items = [
  { href: "/", label: "대시보드", icon: "🏠" },
  { href: "/lab", label: "백테스트 연구소", icon: "🧪" },
  { href: "/builder", label: "전략 빌더", icon: "🛠️" },
  { href: "/compare", label: "전략 비교", icon: "📊" },
  { href: "/optimize", label: "파라미터 최적화", icon: "🎯" },
  { href: "/data", label: "데이터 관리", icon: "💾" },
  { href: "/settings", label: "설정", icon: "⚙️" },
];

export function Nav() {
  const pathname = usePathname();
  return (
    <nav className="w-14 lg:w-52 shrink-0 border-r border-line bg-panel flex flex-col">
      <div className="px-3 py-4 border-b border-line">
        <span className="hidden lg:block font-bold text-accent">Upbit Strategy Lab</span>
        <span className="lg:hidden text-xl">📈</span>
        <span className="hidden lg:block text-[10px] text-muted mt-1">연구·검증 도구 (투자 추천 아님)</span>
      </div>
      <ul className="py-2 flex-1">
        {items.map((it) => {
          const active = pathname === it.href;
          return (
            <li key={it.href}>
              <Link
                href={it.href}
                className={`flex items-center gap-2 px-4 py-2.5 text-sm transition-colors ${
                  active ? "bg-panel-2 text-accent border-r-2 border-accent" : "text-muted hover:text-fg"
                }`}
              >
                <span>{it.icon}</span>
                <span className="hidden lg:inline">{it.label}</span>
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
