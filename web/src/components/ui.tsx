/**
 * shadcn/ui-style primitives (copied pattern: cva + tailwind-merge). Touch targets are at least
 * 44 px; focus is always visible; colour never carries meaning alone (Badge takes a glyph).
 */
import { cva, type VariantProps } from "class-variance-authority";
import { type ClassValue, clsx } from "clsx";
import type { ComponentProps, ReactNode } from "react";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

const focus =
  "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-700";

const buttonVariants = cva(
  `inline-flex min-h-11 items-center justify-center gap-2 rounded-md px-4 text-sm font-medium disabled:opacity-60 ${focus}`,
  {
    variants: {
      variant: {
        primary: "bg-blue-800 text-white hover:bg-blue-900",
        secondary: "border border-slate-400 bg-white text-slate-900 hover:bg-slate-100",
        danger: "bg-red-700 text-white hover:bg-red-800",
        link: "min-h-0 px-0 text-blue-800 underline hover:text-blue-950",
      },
    },
    defaultVariants: { variant: "primary" },
  },
);

export function Button({
  className,
  variant,
  ...props
}: ComponentProps<"button"> & VariantProps<typeof buttonVariants>) {
  return <button className={cn(buttonVariants({ variant }), className)} {...props} />;
}

export function Input({ className, ...props }: ComponentProps<"input">) {
  return (
    <input
      className={cn(
        `min-h-11 w-full rounded-md border border-slate-500 bg-white px-3 text-base text-slate-900 ${focus}`,
        className,
      )}
      {...props}
    />
  );
}

export function Select({ className, ...props }: ComponentProps<"select">) {
  return (
    <select
      className={cn(
        `min-h-11 w-full rounded-md border border-slate-500 bg-white px-3 text-base text-slate-900 ${focus}`,
        className,
      )}
      {...props}
    />
  );
}

export function Label({ className, ...props }: ComponentProps<"label">) {
  // biome-ignore lint/a11y/noLabelWithoutControl: callers pass htmlFor or wrap the control
  return <label className={cn("text-sm font-medium text-slate-900", className)} {...props} />;
}

export function Field({
  label,
  htmlFor,
  children,
}: {
  label: string;
  htmlFor: string;
  children: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1">
      <Label htmlFor={htmlFor}>{label}</Label>
      {children}
    </div>
  );
}

export function Card({
  title,
  children,
  className,
}: {
  title?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={cn("rounded-lg border border-slate-300 bg-white p-4", className)}>
      {title ? <h2 className="mb-3 text-lg font-semibold text-slate-900">{title}</h2> : null}
      <div className="flex flex-col gap-3">{children}</div>
    </section>
  );
}

const tones = {
  ok: "bg-green-100 text-green-900",
  info: "bg-blue-100 text-blue-900",
  warn: "bg-amber-100 text-amber-950",
  danger: "bg-red-100 text-red-900",
  neutral: "bg-slate-100 text-slate-900",
} as const;
export type Tone = keyof typeof tones;

export function Badge({
  tone,
  glyph,
  children,
}: {
  tone: Tone;
  glyph: string;
  children: ReactNode;
}) {
  return (
    <span className={cn("inline-flex items-center gap-1 rounded px-2 py-0.5 text-sm", tones[tone])}>
      <span aria-hidden="true">{glyph}</span>
      {children}
    </span>
  );
}

export function Alert({ tone, children }: { tone: Tone; children: ReactNode }) {
  const glyph = tone === "ok" ? "✓" : tone === "danger" ? "⚠" : tone === "warn" ? "⚠" : "ℹ";
  return (
    <p
      role={tone === "danger" || tone === "warn" ? "alert" : "status"}
      className={cn("flex gap-2 rounded-md p-3", tones[tone])}
    >
      <span aria-hidden="true">{glyph}</span>
      <span>{children}</span>
    </p>
  );
}
