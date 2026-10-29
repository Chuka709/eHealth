"use client";

import { useTranslations } from "next-intl";
import { type ReactNode, useActionState, useEffect, useRef, useState, useTransition } from "react";

import { Alert, Button, Field, Input, Select } from "@/components/ui";
import { formatDate, minutesSeconds } from "@/lib/dates";
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
    setNow(Date.now());
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [until]);
  return until === null ? 0 : Math.max(0, Math.ceil((until - now) / 1000));
}

/**
 * A countdown everyone can see, announced to screen readers only at a few moments (not every
 * second).
 */
function Countdown({
  text,
  seconds,
  announceAt,
}: {
  text: string;
  seconds: number;
  announceAt: number[];
}) {
  const [said, setSaid] = useState("");
  useEffect(() => {
    if (announceAt.includes(seconds)) setSaid(text);
  }, [seconds, text, announceAt]);
  return (
    <>
      <p aria-hidden="true">{text}</p>
      <p className="sr-only" role="status">
        {said}
      </p>
    </>
  );
}

export function ErrorAlert({ state }: { state: ActionResult<unknown> | null }) {
  const t = useTranslations();
  if (!state || state.ok) return null;
  const fields = state.fields?.length
    ? ` ${t("admin.common.check_fields", { fields: state.fields.map((f) => t(`admin.field.${f}`)).join(", ") })}`
    : "";
  return (
    <Alert tone="danger">
      {t(`error.${state.code}`)}
      {fields}
    </Alert>
  );
}

function ReasonSelect({ id, reasons }: { id: string; reasons: readonly string[] }) {
  const t = useTranslations("admin");
  return (
    <Field label={t("reset.reason")} htmlFor={id}>
      <Select id={id} name="reason" required defaultValue="">
        <option value="" disabled>
          {t("common.choose")}
        </option>
        {reasons.map((r) => (
          <option key={r} value={r}>
            {t(`reason.${r}`)}
          </option>
        ))}
      </Select>
    </Field>
  );
}

/**
 * Two-step submit for actions that sign people out or cannot be undone: the first click asks,
 * the second submits the surrounding form. Focus moves to the question and back.
 */
function ConfirmSubmit({
  label,
  question,
  pending,
  variant = "danger",
  name,
  value,
}: {
  label: string;
  question: ReactNode;
  pending: boolean;
  variant?: "danger" | "primary";
  name?: string;
  value?: string;
}) {
  const t = useTranslations("admin.common");
  const [asking, setAsking] = useState(false);
  const confirmRef = useRef<HTMLButtonElement>(null);
  const askRef = useRef<HTMLButtonElement>(null);
  const wasAsking = useRef(false);
  useEffect(() => {
    if (asking) confirmRef.current?.focus();
    else if (wasAsking.current) askRef.current?.focus();
    wasAsking.current = asking;
  }, [asking]);
  if (!asking) {
    return (
      <Button
        ref={askRef}
        type="button"
        variant={variant}
        className="self-start"
        disabled={pending}
        onClick={(event) => {
          // let the browser check required fields before asking
          if (event.currentTarget.form?.reportValidity() !== false) setAsking(true);
        }}
      >
        {label}
      </Button>
    );
  }
  return (
    <div
      role="alertdialog"
      aria-label={label}
      className="flex flex-col gap-2"
      onKeyDown={(event) => {
        if (event.key === "Escape") setAsking(false);
      }}
    >
      <Alert tone="warn">{question}</Alert>
      <div className="flex gap-2">
        <Button
          ref={confirmRef}
          type="submit"
          name={name}
          value={value}
          variant={variant}
          disabled={pending}
          onClick={() => setTimeout(() => setAsking(false))}
        >
          {t("confirm")}
        </Button>
        <Button type="button" variant="secondary" onClick={() => setAsking(false)}>
          {t("cancel")}
        </Button>
      </div>
    </div>
  );
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
            <Alert tone="info">{t("qr.once")}</Alert>
            {/* biome-ignore lint/performance/noImgElement: a data: URL QR, not an optimisable asset */}
            <img
              src={issued.qr}
              alt={t("qr.alt")}
              width={256}
              height={256}
              className="self-start border"
            />
            <Countdown
              text={t("qr.expires", { time: minutesSeconds(left) })}
              seconds={left}
              announceAt={[60, 10]}
            />
            <Button type="button" variant="secondary" onClick={onHide} className="self-start">
              {t("qr.hide")}
            </Button>
          </>
        ) : (
          <Alert tone="warn">{t("qr.expired")}</Alert>
        )
      ) : (
        <Alert tone="ok">{t("qr.sms_sent", { expires: formatDate(issued.expiresAt, true) })}</Alert>
      )}
    </div>
  );
}

const MATCH_VALID_MS = 10 * 60 * 1000; // admin_issue_token: a successful check counts 10 min

export function IssueTokenPanel({
  userId,
  displayName,
  purpose,
  hasPhone,
}: {
  userId: string;
  displayName: string;
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
  const [matchedAt, setMatchedAt] = useState<number | null>(null);
  useEffect(() => {
    setMatchedAt(check?.ok && check.data.match ? Date.now() : null);
  }, [check]);
  const matchLeft = useSecondsLeft(matchedAt === null ? null : matchedAt + MATCH_VALID_MS);
  const matched = check?.ok && check.data.match && matchLeft > 0 ? check.data.checkId : null;
  const needsCheck = purpose === "admin_reset";
  const issuedOk = issued?.ok ? issued.data : null;

  return (
    <div className="flex flex-col gap-3">
      {needsCheck ? (
        <form action={checkAction} className="flex flex-wrap items-end gap-2">
          <Field label={t("identity.national_id")} htmlFor={`nid-${purpose}`}>
            <Input
              id={`nid-${purpose}`}
              name="national_id"
              maxLength={10}
              pattern="[А-ЯӨҮЁа-яөүё]{2}[0-9]{8}"
              autoComplete="off"
              spellCheck={false}
              required
            />
          </Field>
          <Button type="submit" variant="secondary" disabled={checking}>
            {t("identity.check")}
          </Button>
        </form>
      ) : null}
      {check?.ok ? (
        check.data.match && matchLeft <= 0 ? (
          <Alert tone="warn">{t("identity.match_expired")}</Alert>
        ) : (
          <Alert tone={check.data.match ? "ok" : "danger"}>
            {check.data.match ? t("identity.match") : t("identity.no_match")}
          </Alert>
        )
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
              <ReasonSelect
                id="reset-reason"
                reasons={["forgot_password", "lost_device", "suspected_compromise", "other"]}
              />
              <ConfirmSubmit
                label={t("reset.qr")}
                question={t("reset.confirm", { name: displayName })}
                pending={issuing}
                name="channel"
                value="in_person_qr"
              />
              {hasPhone ? (
                <ConfirmSubmit
                  label={t("reset.sms")}
                  question={t("reset.confirm", { name: displayName })}
                  pending={issuing}
                  name="channel"
                  value="sms"
                />
              ) : null}
            </>
          ) : (
            <div className="flex flex-wrap gap-2">
              <Button type="submit" name="channel" value="in_person_qr" disabled={issuing}>
                {t("activation.qr")}
              </Button>
              {hasPhone ? (
                <Button
                  type="submit"
                  name="channel"
                  value="sms"
                  variant="secondary"
                  disabled={issuing}
                >
                  {t("activation.sms")}
                </Button>
              ) : null}
            </div>
          )}
        </form>
      )}
      {issuedOk && !hidden ? (
        <TokenResult issued={issuedOk} onHide={() => setHidden(true)} />
      ) : null}
      {issuedOk && hidden ? <Alert tone="info">{t("qr.hidden")}</Alert> : null}
      {/* stays after the QR is hidden: the admin still has to tell the user */}
      {issuedOk && !issuedOk.noticeSent ? (
        <Alert tone="warn">{t("qr.notice_not_sent")}</Alert>
      ) : null}
      <ErrorAlert state={issued} />
    </div>
  );
}

export function RevealPhonePanel({ userId }: { userId: string }) {
  const t = useTranslations("admin");
  const [stage, setStage] = useState<"idle" | "confirming" | "shown">("idle");
  const [result, setResult] = useState<ActionResult<string | null> | null>(null);
  const [until, setUntil] = useState<number | null>(null);
  const [pending, startTransition] = useTransition();
  const left = useSecondsLeft(until);
  const revealRef = useRef<HTMLButtonElement>(null);
  const confirmRef = useRef<HTMLButtonElement>(null);
  const numberRef = useRef<HTMLParagraphElement>(null);
  const [announce, setAnnounce] = useState("");

  useEffect(() => {
    if (stage === "shown" && left === 0 && until !== null) {
      setStage("idle");
      setUntil(null);
      setAnnounce(t("phone.hidden"));
    }
  }, [stage, left, until, t]);
  useEffect(() => {
    if (stage === "confirming") confirmRef.current?.focus();
    else if (stage === "shown") numberRef.current?.focus();
  }, [stage]);

  return (
    <div className="flex flex-col gap-3">
      <p className="sr-only" role="status">
        {announce}
      </p>
      {stage === "shown" && result?.ok ? (
        <>
          <p
            ref={numberRef}
            tabIndex={-1}
            className="select-all text-2xl font-semibold tracking-wider"
          >
            {result.data ?? t("phone.none")}
          </p>
          <Countdown
            text={t("phone.hidden_in", { seconds: left })}
            seconds={left}
            announceAt={[10]}
          />
        </>
      ) : stage === "confirming" ? (
        <div
          role="alertdialog"
          aria-label={t("phone.title")}
          className="flex flex-col gap-2"
          onKeyDown={(event) => {
            if (event.key === "Escape") setStage("idle");
          }}
        >
          <Alert tone="warn">{t("phone.confirm")}</Alert>
          <div className="flex gap-2">
            <Button
              ref={confirmRef}
              type="button"
              disabled={pending}
              onClick={() =>
                startTransition(async () => {
                  const r = await revealPhone(userId);
                  setResult(r);
                  setAnnounce("");
                  if (r.ok) {
                    setUntil(Date.now() + 60_000);
                    setStage("shown");
                  } else {
                    setStage("idle");
                  }
                })
              }
            >
              {t("common.confirm")}
            </Button>
            <Button type="button" variant="secondary" onClick={() => setStage("idle")}>
              {t("common.cancel")}
            </Button>
          </div>
        </div>
      ) : (
        <Button
          ref={revealRef}
          type="button"
          variant="secondary"
          className="self-start"
          onClick={() => setStage("confirming")}
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
  displayName,
  current,
  isSuper,
}: {
  userId: string;
  displayName: string;
  current: string;
  isSuper: boolean;
}) {
  const t = useTranslations("admin");
  const [state, action, pending] = useActionState(setStatus.bind(null, userId), null);
  const [target, setTarget] = useState("");
  // Support may only unlock; the API enforces it, the form just does not offer the rest.
  const targets = (
    isSuper ? ["active", "locked", "disabled"] : current === "locked" ? ["active"] : []
  ).filter((s) => s !== current);
  if (targets.length === 0) return <p className="text-slate-700">{t("status_change.none")}</p>;
  const signsOut = target === "locked" || target === "disabled";
  return (
    <form action={action} className="flex flex-col gap-3">
      <Field label={t("status_change.to")} htmlFor="status-to">
        <Select
          id="status-to"
          name="status"
          required
          value={target}
          onChange={(event) => setTarget(event.currentTarget.value)}
        >
          <option value="" disabled>
            {t("common.choose")}
          </option>
          {targets.map((s) => (
            <option key={s} value={s}>
              {t(`status.${s}`)}
            </option>
          ))}
        </Select>
      </Field>
      <ReasonSelect id="status-reason" reasons={STATUS_REASONS} />
      {signsOut ? (
        <ConfirmSubmit
          label={t("status_change.submit")}
          question={t("status_change.confirm", {
            name: displayName,
            status: t(`status.${target}`),
          })}
          pending={pending}
        />
      ) : (
        <Button type="submit" disabled={pending} className="self-start">
          {t("status_change.submit")}
        </Button>
      )}
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
        <Input
          id="enrol-nid"
          name="national_id"
          maxLength={10}
          pattern="[А-ЯӨҮЁа-яөүё]{2}[0-9]{8}"
          autoComplete="off"
          spellCheck={false}
          required
        />
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

export function CancelDeletionPanel({
  userId,
  displayName,
}: {
  userId: string;
  displayName: string;
}) {
  const t = useTranslations("admin");
  const [state, action, pending] = useActionState(cancelDeletion.bind(null, userId), null);
  return (
    <form
      action={action}
      className="flex max-w-lg flex-col gap-3 rounded-lg border border-slate-300 bg-white p-4"
    >
      <h2 className="text-lg font-semibold">{t("deletion.cancel_title")}</h2>
      <p>{t("deletion.cancel_hint")}</p>
      <ReasonSelect
        id="cancel-reason"
        reasons={["user_request", "suspected_compromise", "other"]}
      />
      <ConfirmSubmit
        label={t("deletion.cancel")}
        question={t("deletion.confirm", { name: displayName })}
        pending={pending}
      />
      {state?.ok ? (
        <Alert tone="ok">{t("deletion.cancelled")}</Alert>
      ) : (
        <ErrorAlert state={state} />
      )}
    </form>
  );
}
