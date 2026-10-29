"use server";

import type { components } from "@labtrack/shared";
import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import QRCode from "qrcode";

import { type ActionResult, adminApi, failure } from "@/lib/server/api";

type Schemas = components["schemas"];

/** A form value narrowed to one of the API's enum members, or null (never a silent default). */
function oneOf<T extends string>(value: string, allowed: readonly T[]): T | null {
  return (allowed as readonly string[]).includes(value) ? (value as T) : null;
}

const invalid = { ok: false, code: "validation" } as const;

const STATUSES = [
  "active",
  "locked",
  "disabled",
] as const satisfies readonly Schemas["StatusRequest"]["status"][];
const STATUS_REASONS = [
  "user_request",
  "identity_verified",
  "suspected_compromise",
  "left_program",
  "other",
] as const satisfies readonly Schemas["StatusRequest"]["reason"][];
const RESET_REASONS = [
  "forgot_password",
  "lost_device",
  "suspected_compromise",
  "other",
] as const satisfies readonly NonNullable<Schemas["TokenRequest"]["reason"]>[];
const CANCEL_REASONS = [
  "user_request",
  "suspected_compromise",
  "other",
] as const satisfies readonly Schemas["CancelDeletionRequest"]["reason"][];

// Every value goes to the API unchanged; the API (and the database behind it) decides what is
// allowed for which admin. Nothing here logs form values.

function field(form: FormData, name: string): string {
  const value = form.get(name);
  return typeof value === "string" ? value.trim() : "";
}

function optional(form: FormData, name: string): string | null {
  return field(form, name) || null;
}

const detailPath = (userId: string) => `/admin/users/${userId}`;

export async function createUser(_: ActionResult | null, form: FormData): Promise<ActionResult> {
  const api = await adminApi();
  const { data, error, response } = await api.POST("/api/v1/admin/users", {
    body: {
      username: field(form, "username").toLowerCase(),
      display_name: field(form, "display_name"),
      role: field(form, "role") === "doctor" ? "doctor" : "user",
      phone: optional(form, "phone"),
      national_id: optional(form, "national_id"),
    },
  });
  if (!data) return failure(error, response.status);
  redirect(detailPath(data.id));
}

export async function setStatus(
  userId: string,
  _: ActionResult | null,
  form: FormData,
): Promise<ActionResult> {
  const status = oneOf(field(form, "status"), STATUSES);
  const reason = oneOf(field(form, "reason"), STATUS_REASONS);
  if (!status || !reason) return invalid;
  const api = await adminApi();
  const { error, response } = await api.POST("/api/v1/admin/users/{user_id}/status", {
    params: { path: { user_id: userId } },
    body: { status, reason },
  });
  if (!response.ok) return failure(error, response.status);
  revalidatePath(detailPath(userId));
  return { ok: true, data: null };
}

export async function clearLockout(userId: string): Promise<ActionResult> {
  const api = await adminApi();
  const { error, response } = await api.POST("/api/v1/admin/users/{user_id}/unlock-login", {
    params: { path: { user_id: userId } },
  });
  return response.ok ? { ok: true, data: null } : failure(error, response.status);
}

export async function revealPhone(userId: string): Promise<ActionResult<string | null>> {
  const api = await adminApi();
  const { data, error, response } = await api.POST("/api/v1/admin/users/{user_id}/phone", {
    params: { path: { user_id: userId } },
  });
  return data ? { ok: true, data: data.phone ?? null } : failure(error, response.status);
}

export type CheckResult = { checkId: number; match: boolean };

export async function identityCheck(
  userId: string,
  _: ActionResult<CheckResult> | null,
  form: FormData,
): Promise<ActionResult<CheckResult>> {
  const api = await adminApi();
  const { data, error, response } = await api.POST("/api/v1/admin/users/{user_id}/identity-check", {
    params: { path: { user_id: userId } },
    body: { national_id: field(form, "national_id") },
  });
  if (!data) return failure(error, response.status);
  revalidatePath(detailPath(userId));
  return { ok: true, data: { checkId: data.check_id, match: data.match } };
}

export async function setIdentity(
  userId: string,
  _: ActionResult | null,
  form: FormData,
): Promise<ActionResult> {
  const api = await adminApi();
  const { error, response } = await api.PUT("/api/v1/admin/users/{user_id}/identity", {
    params: { path: { user_id: userId } },
    body: { national_id: field(form, "national_id") },
  });
  return response.ok ? { ok: true, data: null } : failure(error, response.status);
}

export type IssuedToken = {
  expiresAt: string;
  noticeSent: boolean;
  /** in-person only: the QR as an image (the link itself is never shown as text) */
  qr: string | null;
};

export async function issueToken(
  userId: string,
  _: ActionResult<IssuedToken> | null,
  form: FormData,
): Promise<ActionResult<IssuedToken>> {
  const purpose = field(form, "purpose") === "admin_reset" ? "admin_reset" : "activation";
  const channel = field(form, "channel") === "sms" ? "sms" : "in_person_qr";
  const checkId = Number.parseInt(field(form, "identity_check_id"), 10);
  const reason = purpose === "admin_reset" ? oneOf(field(form, "reason"), RESET_REASONS) : null;
  if (purpose === "admin_reset" && !reason) return invalid;
  const api = await adminApi();
  const { data, error, response } = await api.POST("/api/v1/admin/users/{user_id}/tokens", {
    params: { path: { user_id: userId } },
    body: {
      purpose,
      channel,
      identity_check_id: Number.isFinite(checkId) ? checkId : null,
      reason,
    },
  });
  if (!data) return failure(error, response.status);
  revalidatePath(detailPath(userId));
  const qr = data.link
    ? `data:image/svg+xml;base64,${Buffer.from(
        await QRCode.toString(data.link, { type: "svg", errorCorrectionLevel: "M", margin: 2 }),
      ).toString("base64")}`
    : null;
  return { ok: true, data: { expiresAt: data.expires_at, noticeSent: data.notice_sent, qr } };
}

export async function cancelDeletion(
  userId: string,
  _: ActionResult | null,
  form: FormData,
): Promise<ActionResult> {
  const reason = oneOf(field(form, "reason"), CANCEL_REASONS);
  if (!reason) return invalid;
  const api = await adminApi();
  const { error, response } = await api.POST("/api/v1/admin/users/{user_id}/cancel-deletion", {
    params: { path: { user_id: userId } },
    body: { reason },
  });
  if (!response.ok) return failure(error, response.status);
  revalidatePath(detailPath(userId));
  return { ok: true, data: null };
}
