import { useTranslations } from "next-intl";

import { Badge, type Tone } from "@/components/ui";

// Colour + glyph + text (CLAUDE.md): status is never shown by colour alone.
const look: Record<string, { tone: Tone; glyph: string }> = {
  pending_activation: { tone: "warn", glyph: "◔" },
  active: { tone: "ok", glyph: "●" },
  locked: { tone: "danger", glyph: "⊘" },
  disabled: { tone: "neutral", glyph: "○" },
  deletion_pending: { tone: "danger", glyph: "✕" },
};

export function StatusBadge({
  status,
  deletionPending,
}: {
  status: string;
  deletionPending: boolean;
}) {
  const t = useTranslations("admin.status");
  const key = deletionPending ? "deletion_pending" : status;
  const { tone, glyph } = look[key] ?? { tone: "neutral" as const, glyph: "?" };
  return (
    <Badge tone={tone} glyph={glyph}>
      {t(key)}
    </Badge>
  );
}
