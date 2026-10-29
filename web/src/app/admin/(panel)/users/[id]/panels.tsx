"use client";

import { useTranslations } from "next-intl";
import { useActionState, useEffect, useState, useTransition } from "react";

import { Alert, Button, Field, Input, Select } from "@/components/ui";
import type { ActionResult } from "@/lib/server/api";

import {
  type CheckResult,
  cancelDeletion,
  clearLockout,
  type IssuedToken,
  identityCheck,
  issueToken,
  revealPhone,
  setIdentity,
  setStatus,
} from "../actions";

function useSecondsLeft(until: number | null): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (until === null) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [until]);
  return until === null ? 0 : Math.max(0, Math.ceil((until - now) / 1000));
}

function ErrorAlert({ state }: { state: ActionResult<unknown> | null }) {
  const t = useTranslations();
  return state && !state.ok ? <Alert tone="danger">{t(`error.${state.code}`)}</Alert> : null;
}

/** The QR is shown once, counts down to its expiry and disappears on "hide" or expiry. */
function TokenResult({ issued, onHide }: { issued: IssuedToken; onHide: () => void }) {
  const t = useTranslations("admin");
  const expiresAt = Date.parse(issued.expiresAt);
  const left = useSecondsLeft(issued.qr ? expiresAt : null);
  return (
    <div className="flex flex-col gap-2">
      {issued.qr ? (
        left > 0 ? (
          <>
            {/* biome-ignore lint/performance/noImgElement: a data: URL QR, not an optimisable asset */}
            <img
              src={issued.qr}
              alt={t("qr.alt")}
              width={256}
              height={256}
              className="self-start border"
            />
            <p aria-live="polite">{t("qr.expires", { seconds: left })}</p>
            <Button type="button" variant="secondary" onClick={onHide} className="self-start">
              {t("qr.hide")}
            </Button>
          </>
        ) : (
          <Alert tone="warn">{t("qr.expired")}</Alert>
        )
      ) : (
        <Alert tone="ok">
          {t("qr.sms_sent", {
            expires: new Date(expiresAt).toLocaleString("mn-MN", { timeZone: "Asia/Ulaanbaatar" }),
          })}
        </Alert>
      )}
      {!issued.noticeSent && (issued.qr === null || left > 0) ? (
        <Alert tone="warn">{t("qr.notice_not_sent")}</Alert>
      ) : null}
    </div>
  );
}

export function IssueTokenPanel({
  userId,
  purpose,
  hasPhone,
}: {
  userId: string;
  purpose: "activation" | "admin_reset";
  hasPhone: boolean;
}) {
  const t = useTranslations("admin");
  const [check, checkAction, checking] = useActionState<ActionResult<CheckResult> | null, FormData>(
    identityCheck.bind(null, userId),
    null,
  );
  const [issued, issueAction, issuing] = useActionState<ActionResult<IssuedToken> | null, FormData>(
    issueToken.bind(null, userId),
    null,
  );
  const [hidden, setHidden] = useState(false);
  const matched = check?.ok && check.data.match ? check.data.checkId : null;
  const needsCheck = purpose === "admin_reset";

  return (
    <div className="flex flex-col gap-3">
      {needsCheck ? (
        <form action={checkAction} className="flex flex-wrap items-end gap-2">
          <Field label={t("identity.national_id")} htmlFor={`nid-${purpose}`}>
            <Input
              id={`nid-${purpose}`}
              name="national_id"
              maxLength={10}
              autoComplete="off"
              required
            />
          </Field>
          <Button type="submit" variant="secondary" disabled={checking}>
            {t("identity.check")}
          </Button>
        </form>
      ) : null}
      {check?.ok ? (
        <Alert tone={check.data.match ? "ok" : "danger"}>
          {check.data.match ? t("identity.match") : t("identity.no_match")}
        </Alert>
      ) : (
        <ErrorAlert state={check} />
      )}

      {needsCheck && matched === null ? (
        <p className="text-slate-700">{t("reset.needs_check")}</p>
      ) : (
        <form
          action={(form) => {
            setHidden(false);
            issueAction(form);
          }}
          className="flex flex-col gap-3"
        >
          <input type="hidden" name="purpose" value={purpose} />
          {matched !== null ? (
            <input type="hidden" name="identity_check_id" value={matched} />
          ) : null}
          {needsCheck ? (
            <>
              <p>{t("reset.hint")}</p>
              <Field label={t("reset.reason")} htmlFor="reset-reason">
                <Select id="reset-reason" name="reason" required defaultValue="">
                  <option value="" disabled>
                    —
                  </option>
                  {(
                    ["forgot_password", "lost_device", "suspected_compromise", "other"] as const
                  ).map((r) => (
                    <option key={r} value={r}>
                      {t(`reason.${r}`)}
                    </option>
                  ))}
                </Select>
              </Field>
            </>
          ) : null}
          <div className="flex flex-wrap gap-2">
            <Button type="submit" name="channel" value="in_person_qr" disabled={issuing}>
              {needsCheck ? t("reset.qr") : t("activation.qr")}
            </Button>
            {hasPhone ? (
              <Button
                type="submit"
                name="channel"
                value="sms"
                variant="secondary"
                disabled={issuing}
              >
                {needsCheck ? t("reset.sms") : t("activation.sms")}
              </Button>
            ) : null}
          </div>
        </form>
      )}
      {issued?.ok && !hidden ? (
        <TokenResult issued={issued.data} onHide={() => setHidden(true)} />
      ) : null}
      <ErrorAlert state={issued} />
    </div>
  );
}

export function RevealPhonePanel({ userId }: { userId: string }) {
  const t = useTranslations("admin");
  const [confirming, setConfirming] = useState(false);
  const [result, setResult] = useState<ActionResult<string | null> | null>(null);
  const [until, setUntil] = useState<number | null>(null);
  const [pending, startTransition] = useTransition();
  const left = useSecondsLeft(until);
  const shown = result?.ok && until !== null && left > 0;
  return (
    <div className="flex flex-col gap-3">
      {shown ? (
        <>
          <p className="text-2xl font-semibold tracking-wider">{result.data ?? t("phone.none")}</p>
          <p aria-live="polite">{t("phone.hidden_in", { seconds: left })}</p>
        </>
      ) : confirming ? (
        <>
          <Alert tone="warn">{t("phone.confirm")}</Alert>
          <div className="flex gap-2">
            <Button
              type="button"
              disabled={pending}
              onClick={() =>
                startTransition(async () => {
                  const r = await revealPhone(userId);
                  setResult(r);
                  setUntil(r.ok ? Date.now() + 60_000 : null);
                  setConfirming(false);
                })
              }
            >
              {t("common.confirm")}
            </Button>
            <Button type="button" variant="secondary" onClick={() => setConfirming(false)}>
              {t("common.cancel")}
            </Button>
          </div>
        </>
      ) : (
        <Button
          type="button"
          variant="secondary"
          className="self-start"
          onClick={() => setConfirming(true)}
        >
          {t("phone.reveal")}
        </Button>
      )}
      <ErrorAlert state={result} />
    </div>
  );
}

export function ClearLockoutPanel({ userId }: { userId: string }) {
  const t = useTranslations("admin");
  const [result, setResult] = useState<ActionResult | null>(null);
  const [pending, startTransition] = useTransition();
  return (
    <div className="flex flex-col gap-2">
      <Button
        type="button"
        variant="secondary"
        className="self-start"
        disabled={pending}
        onClick={() => startTransition(async () => setResult(await clearLockout(userId)))}
      >
        {t("unlock.submit")}
      </Button>
      {result?.ok ? <Alert tone="ok">{t("unlock.done")}</Alert> : <ErrorAlert state={result} />}
    </div>
  );
}

const STATUS_REASONS = [
  "user_request",
  "identity_verified",
  "suspected_compromise",
  "left_program",
  "other",
] as const;

export function StatusPanel({
  userId,
  current,
  isSuper,
}: {
  userId: string;
  current: string;
  isSuper: boolean;
}) {
  const t = useTranslations("admin");
  const [state, action, pending] = useActionState(setStatus.bind(null, userId), null);
  // Support may only unlock; the API enforces it, the form just does not offer the rest.
  const targets = (
    isSuper ? ["active", "locked", "disabled"] : current === "locked" ? ["active"] : []
  ).filter((s) => s !== current);
  if (targets.length === 0) return <p className="text-slate-700">—</p>;
  return (
    <form action={action} className="flex flex-col gap-3">
      <Field label={t("status_change.to")} htmlFor="status-to">
        <Select id="status-to" name="status" required defaultValue="">
          <option value="" disabled>
            —
          </option>
          {targets.map((s) => (
            <option key={s} value={s}>
              {t(`status.${s}`)}
            </option>
          ))}
        </Select>
      </Field>
      <Field label={t("reset.reason")} htmlFor="status-reason">
        <Select id="status-reason" name="reason" required defaultValue="">
          <option value="" disabled>
            —
          </option>
          {STATUS_REASONS.map((r) => (
            <option key={r} value={r}>
              {t(`reason.${r}`)}
            </option>
          ))}
        </Select>
      </Field>
      <Button type="submit" disabled={pending} className="self-start">
        {t("status_change.submit")}
      </Button>
      {state?.ok ? (
        <Alert tone="ok">{t("status_change.done")}</Alert>
      ) : (
        <ErrorAlert state={state} />
      )}
    </form>
  );
}

export function EnrolIdentityPanel({ userId }: { userId: string }) {
  const t = useTranslations("admin");
  const [state, action, pending] = useActionState(setIdentity.bind(null, userId), null);
  return (
    <form action={action} className="flex flex-wrap items-end gap-2">
      <Field label={t("identity.national_id")} htmlFor="enrol-nid">
        <Input id="enrol-nid" name="national_id" maxLength={10} autoComplete="off" required />
      </Field>
      <Button type="submit" variant="secondary" disabled={pending}>
        {t("identity.enrol")}
      </Button>
      <div className="basis-full">
        {state?.ok ? (
          <Alert tone="ok">{t("identity.enrolled")}</Alert>
        ) : (
          <ErrorAlert state={state} />
        )}
      </div>
    </form>
  );
}

export function CancelDeletionPanel({ userId }: { userId: string }) {
  const t = useTranslations("admin");
  const [state, action, pending] = useActionState(cancelDeletion.bind(null, userId), null);
  return (
    <form
      action={action}
      className="flex max-w-lg flex-col gap-3 rounded-lg border border-slate-300 bg-white p-4"
    >
      <h2 className="text-lg font-semibold">{t("deletion.cancel_title")}</h2>
      <p>{t("deletion.cancel_hint")}</p>
      <Field label={t("reset.reason")} htmlFor="cancel-reason">
        <Select id="cancel-reason" name="reason" required defaultValue="">
          <option value="" disabled>
            —
          </option>
          {(["user_request", "suspected_compromise", "other"] as const).map((r) => (
            <option key={r} value={r}>
              {t(`reason.${r}`)}
            </option>
          ))}
        </Select>
      </Field>
      <Button type="submit" variant="danger" disabled={pending} className="self-start">
        {t("deletion.cancel")}
      </Button>
      {state?.ok ? (
        <Alert tone="ok">{t("deletion.cancelled")}</Alert>
      ) : (
        <ErrorAlert state={state} />
      )}
    </form>
  );
}
