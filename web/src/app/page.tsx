import { Suspense } from "react";

import { fetchReadiness, type StatusKey, statusKey } from "@/lib/status";

const API_INTERNAL_URL = process.env.API_INTERNAL_URL ?? "http://localhost:8000";

// Phase 0 placeholder; the admin panel (Phase 1) and share viewer (Phase 7) replace it.
const text: Record<StatusKey, { glyph: string; label: string; className: string }> = {
  ok: {
    glyph: "●",
    label: "Сервер хэвийн ажиллаж байна",
    className: "bg-green-100 text-green-900",
  },
  degraded: {
    glyph: "⚠",
    label: "Серверийн зарим хэсэг ажиллахгүй байна",
    className: "bg-orange-100 text-orange-900",
  },
  unreachable: {
    glyph: "⚠",
    label: "Сервертэй холбогдож чадсангүй",
    className: "bg-red-700 text-white",
  },
};

async function ApiStatus() {
  const t = text[statusKey(await fetchReadiness(API_INTERNAL_URL))];
  return (
    <p role="status" className={`flex items-center gap-2 rounded-lg p-3 ${t.className}`}>
      <span aria-hidden="true">{t.glyph}</span>
      {t.label}
    </p>
  );
}

export default function Home() {
  return (
    <main className="mx-auto flex w-full max-w-xl flex-col gap-6 p-6">
      <h1 className="text-2xl font-bold">LabTrack MN</h1>
      <Suspense fallback={<p role="status">Сервертэй холбогдож байна…</p>}>
        <ApiStatus />
      </Suspense>
    </main>
  );
}
