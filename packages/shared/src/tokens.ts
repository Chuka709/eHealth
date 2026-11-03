/**
 * Design tokens shared by mobile and web (docs/06, docs/11 §7).
 * Flags are never colour-only: every flag also has an icon and a text label (see `flagGlyph`).
 * Colour pairs were chosen for WCAG 2.2 AA text contrast (≥ 4.5:1) on their background.
 */

export type Scheme = "light" | "dark";
export type Flag = "normal" | "low" | "high" | "critical" | "abnormal" | "no_reference";

interface Palette {
  background: string;
  surface: string;
  text: string;
  textMuted: string;
  border: string;
  primary: string;
  onPrimary: string;
  /** Destructive actions (sign out, delete). Not a clinical flag colour. */
  danger: string;
  flag: Record<Flag, { fg: string; bg: string }>;
}

export const colors: Record<Scheme, Palette> = {
  light: {
    background: "#FFFFFF",
    surface: "#F4F6F8",
    text: "#111827",
    textMuted: "#4B5563",
    border: "#D1D5DB",
    primary: "#0B5FA5",
    onPrimary: "#FFFFFF",
    danger: "#9F1239",
    flag: {
      normal: { fg: "#166534", bg: "#DCFCE7" },
      low: { fg: "#1E40AF", bg: "#DBEAFE" },
      high: { fg: "#9A3412", bg: "#FFEDD5" },
      critical: { fg: "#FFFFFF", bg: "#B91C1C" },
      abnormal: { fg: "#9A3412", bg: "#FFEDD5" },
      no_reference: { fg: "#374151", bg: "#E5E7EB" },
    },
  },
  dark: {
    background: "#0B0F14",
    surface: "#161B22",
    text: "#F3F4F6",
    textMuted: "#A1A1AA",
    border: "#30363D",
    primary: "#60A5FA",
    onPrimary: "#0B0F14",
    danger: "#FDA4AF",
    flag: {
      normal: { fg: "#86EFAC", bg: "#14301F" },
      low: { fg: "#93C5FD", bg: "#172554" },
      high: { fg: "#FDBA74", bg: "#3B1D0B" },
      critical: { fg: "#FFFFFF", bg: "#B91C1C" },
      abnormal: { fg: "#FDBA74", bg: "#3B1D0B" },
      no_reference: { fg: "#D1D5DB", bg: "#262B33" },
    },
  },
};

/** Icon shown next to the colour and the text label of every flag. */
export const flagGlyph: Record<Flag, string> = {
  normal: "●",
  low: "↓",
  high: "↑",
  critical: "⚠",
  abnormal: "◆",
  no_reference: "○",
};

/** 4-pt spacing scale. */
export const space = { xs: 4, sm: 8, md: 12, lg: 16, xl: 24, xxl: 32 } as const;

/** Body text ≥ 16pt; sizes scale with the OS font setting (Dynamic Type / font scale). */
export const fontSize = { caption: 13, body: 16, bodyLarge: 18, title: 22, display: 28 } as const;

/** Minimum touch target: 44pt (iOS) / 48dp (Android). */
export const minTouchTarget = { ios: 44, android: 48 } as const;

export const radius = { sm: 6, md: 10, lg: 16 } as const;
