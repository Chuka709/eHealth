import { notFound } from "next/navigation";
import { getTranslations } from "next-intl/server";
import QRCode from "qrcode";

import { adminApi } from "@/lib/server/api";

import { PrintButton } from "./print-button";

const APP_DOWNLOAD_URL = process.env.APP_DOWNLOAD_URL ?? "https://labtrack.mn/app";
const ORG_SUPPORT_PHONE = process.env.ORG_SUPPORT_PHONE ?? "";

/**
 * The printed login card (docs/04 §1 step 5): where to get the app, the username and whom to
 * call. It never carries a password or a token - activation is the separate one-time QR.
 */
export default async function LoginCardPage({ params }: PageProps<"/admin/users/[id]/card">) {
  const { id } = await params;
  const t = await getTranslations("admin.card");
  const api = await adminApi();
  const { data: user } = await api.GET("/api/v1/admin/users/{user_id}", {
    params: { path: { user_id: id } },
  });
  if (!user) notFound();
  const qr = await QRCode.toString(APP_DOWNLOAD_URL, {
    type: "svg",
    errorCorrectionLevel: "M",
    margin: 2,
  });
  const src = `data:image/svg+xml;base64,${Buffer.from(qr).toString("base64")}`;
  return (
    <article className="mx-auto flex w-[85.6mm] flex-col items-center gap-2 rounded-lg border border-slate-400 bg-white p-4 text-center print:border-slate-900">
      <h1 className="text-base font-bold">{t("title")}</h1>
      {/* biome-ignore lint/performance/noImgElement: a data: URL QR */}
      <img src={src} alt={t("download")} width={140} height={140} />
      <p className="text-sm">{t("download")}</p>
      <p className="text-sm">{t("username")}</p>
      <p className="font-mono text-lg font-semibold">{user.username}</p>
      {ORG_SUPPORT_PHONE ? (
        <p className="text-sm">{t("support", { phone: ORG_SUPPORT_PHONE })}</p>
      ) : null}
      <p className="text-xs text-slate-700">{t("note")}</p>
      <PrintButton label={t("print_button")} />
    </article>
  );
}
