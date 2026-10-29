"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

export function NavLinks({
  items,
  label,
}: {
  items: { href: string; label: string }[];
  label: string;
}) {
  const pathname = usePathname();
  // the most specific match is the current page (/admin/users/new is not also "Users")
  const current = items
    .filter((i) => pathname === i.href || pathname.startsWith(`${i.href}/`))
    .sort((a, b) => b.href.length - a.href.length)[0]?.href;
  return (
    <nav aria-label={label} className="flex flex-wrap gap-4">
      {items.map((item) => (
        <Link
          key={item.href}
          href={item.href}
          aria-current={item.href === current ? "page" : undefined}
          className="inline-flex min-h-11 items-center text-blue-800 underline aria-[current=page]:font-bold aria-[current=page]:no-underline"
        >
          {item.label}
        </Link>
      ))}
    </nav>
  );
}
