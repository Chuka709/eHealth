"use client";

import { useTranslations } from "next-intl";
import { type FormEvent, startTransition, useActionState, useState } from "react";

import { Alert, Button, Field, Input } from "@/components/ui";

import { importCsv } from "./actions";

type Problem = { row: number; field: string };

function Problems({ problems }: { problems: Problem[] }) {
  const t = useTranslations();
  return (
    <div className="flex flex-col gap-2">
      <h2 className="text-lg font-semibold">{t("admin.import.problems")}</h2>
      <ul className="flex flex-col gap-1">
        {problems.map((p) => (
          <li key={`${p.row}-${p.field}`} className="rounded bg-red-50 p-2 text-red-900">
            <span aria-hidden="true">⚠ </span>
            {p.row === 0 ? t("admin.import.whole_file") : t("admin.import.row", { row: p.row })}:{" "}
            {t(`import.problem.${p.field}`)}
          </li>
        ))}
      </ul>
    </div>
  );
}

export function ImportForm() {
  const t = useTranslations();
  const [state, action, pending] = useActionState(importCsv, null);
  // The preview's sha256 belongs to the file that was chosen when it was made; picking another
  // file means previewing again. Submitting by hand keeps the chosen file (React resets a form
  // after a form action).
  const [fileVersion, setFileVersion] = useState(0);
  const [previewedVersion, setPreviewedVersion] = useState(-1);
  const outcome = state?.ok ? state.data : null;
  const preview = outcome?.kind === "preview" ? outcome.preview : null;
  const ready =
    preview !== null &&
    previewedVersion === fileVersion &&
    preview.problems.length === 0 &&
    preview.rows.length > 0;

  function submit(event: FormEvent<HTMLFormElement>, commit: boolean) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    if (commit && preview) data.set("sha256", preview.sha256);
    else setPreviewedVersion(fileVersion);
    startTransition(() => action(data));
  }

  return (
    <form
      onSubmit={(event) => {
        const submitter = (event.nativeEvent as SubmitEvent).submitter as HTMLButtonElement | null;
        submit(event, submitter?.value === "commit");
      }}
      className="flex flex-col gap-4"
    >
      <Field label={t("admin.import.file")} htmlFor="file">
        <Input
          id="file"
          name="file"
          type="file"
          accept=".csv,text/csv"
          required
          onChange={() => setFileVersion((v) => v + 1)}
        />
      </Field>
      <Button
        type="submit"
        name="intent"
        value="preview"
        variant={ready ? "secondary" : "primary"}
        disabled={pending}
        className="self-start"
      >
        {t("admin.import.preview")}
      </Button>

      {state && !state.ok ? <Alert tone="danger">{t(`error.${state.code}`)}</Alert> : null}
      {outcome?.kind === "done" ? (
        <Alert tone="ok">{t("admin.import.done", { count: outcome.created })}</Alert>
      ) : null}
      {outcome?.kind === "invalid" ? (
        <>
          <Alert tone="danger">{t("error.admin.import_invalid")}</Alert>
          <Problems problems={outcome.problems} />
        </>
      ) : null}
      {preview ? (
        <>
          {preview.problems.length > 0 ? <Problems problems={preview.problems} /> : null}
          <p>{t("admin.import.rows", { count: preview.rows.length })}</p>
          <div className="overflow-x-auto rounded-lg border border-slate-300 bg-white">
            <table className="w-full text-left text-sm">
              <thead className="bg-slate-100">
                <tr>
                  <th scope="col" className="p-2">
                    #
                  </th>
                  <th scope="col" className="p-2">
                    {t("admin.users.col.username")}
                  </th>
                  <th scope="col" className="p-2">
                    {t("admin.users.col.name")}
                  </th>
                  <th scope="col" className="p-2">
                    {t("admin.users.col.role")}
                  </th>
                  <th scope="col" className="p-2">
                    {t("admin.users.col.phone")}
                  </th>
                </tr>
              </thead>
              <tbody>
                {preview.rows.map((r) => (
                  <tr key={r.row} className="border-t border-slate-200">
                    <td className="p-2">{r.row}</td>
                    <td className="p-2">{r.username}</td>
                    <td className="p-2">{r.display_name}</td>
                    <td className="p-2">{t(`admin.role.${r.role}`)}</td>
                    <td className="p-2">{r.phone_last4 ? `••••${r.phone_last4}` : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {ready ? (
            <Button
              type="submit"
              name="intent"
              value="commit"
              disabled={pending}
              className="self-start"
            >
              {t("admin.import.commit", { count: preview.rows.length })}
            </Button>
          ) : null}
        </>
      ) : null}
    </form>
  );
}
