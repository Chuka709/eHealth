import { execFileSync } from "node:child_process";
import { randomBytes } from "node:crypto";
import { readFileSync, rmSync, writeFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";

import { expect, type Page, test } from "@playwright/test";

import { AUTH_FILE } from "./global-setup";
import { totp } from "./totp";

type Admin = { username: string; password: string; secret: string };
const admin = (): Admin => JSON.parse(readFileSync(AUTH_FILE, "utf8")) as Admin;

const root = path.join(process.cwd(), "..");
function sql(query: string): string {
  return execFileSync(
    "docker",
    [
      "compose",
      "-f",
      "infra/docker-compose.yml",
      "--env-file",
      ".env",
      "exec",
      "-T",
      "postgres",
      "psql",
      "-U",
      "postgres",
      "-d",
      "labtrack",
      "-tAc",
      query,
    ],
    { cwd: root, encoding: "utf8" },
  ).trim();
}

/** Waits for a fresh TOTP step: each code is accepted once. */
async function signIn(page: Page, code?: string) {
  const a = admin();
  await page.goto("/admin/users");
  await expect(page).toHaveURL(/\/admin\/login$/);
  await page.getByLabel("Хэрэглэгчийн нэр").fill(a.username);
  await page.getByLabel("Нууц үг").fill(a.password);
  await page.getByLabel("Баталгаажуулах код (6 орон)").fill(code ?? totp(a.secret));
  await page.getByRole("button", { name: "Нэвтрэх" }).click();
}

test("a wrong code is refused with the generic message", async ({ page }) => {
  await signIn(page, "000000");
  await expect(page.getByText("Нэр, нууц үг эсвэл баталгаажуулах код буруу байна.")).toBeVisible();
  await expect(page).toHaveURL(/\/admin\/login$/);
});

test("register, activation QR, login card, phone, CSV import, security, sign out", async ({
  page,
}) => {
  const cspViolations: string[] = [];
  page.on("console", (m) => {
    if (m.type() === "error" && m.text().includes("Content Security Policy"))
      cspViolations.push(m.text());
  });

  await signIn(page);
  await expect(page).toHaveURL(/\/admin\/users$/);
  await expect(page.getByRole("heading", { name: "Хэрэглэгчид" })).toBeVisible();

  // register
  const username = `e2eu${randomBytes(3).toString("hex")}`;
  await page.getByRole("link", { name: "Шинэ хэрэглэгч" }).click();
  await page.getByLabel("Хэрэглэгчийн нэр (a-z 0-9 . _)").fill(username);
  await page.getByLabel("Харуулах нэр").fill("Туршилт Болд");
  await page.getByLabel("Холбоо барих утас (8 оронтой, сонголттой)").fill("9911 2233");
  await page.getByRole("button", { name: "Бүртгэх" }).click();
  await expect(page.getByRole("heading", { name: "Туршилт Болд" })).toBeVisible();
  await expect(page.getByText("Идэвхжүүлээгүй")).toBeVisible();

  // activation QR: shown once with a countdown, gone on hide
  await page.getByRole("button", { name: "Идэвхжүүлэх QR үүсгэх" }).click();
  const qr = page.getByRole("img", { name: "Идэвхжүүлэх QR код" });
  await expect(qr).toBeVisible();
  await expect(page.getByText(/минутын дараа хүчингүй болно/)).toBeVisible();
  // the API recorded the admin's address, not the web container's (docs/04 §6.1)
  const issuedFrom = sql(
    `select host(t.issued_ip) from activation_tokens t join users u on u.id = t.user_id where u.username = '${username}' order by t.created_at desc limit 1`,
  );
  expect(issuedFrom).not.toBe("");
  expect(issuedFrom).not.toBe("172.30.0.11");
  await page.getByRole("button", { name: "QR нуух" }).click();
  await expect(qr).toHaveCount(0);

  // phone: confirm, then shown for a while
  await page.getByRole("button", { name: "Дугаар харах" }).click();
  await expect(page.getByText(/аудитад бүртгэгдэнэ/)).toBeVisible();
  await page.getByRole("button", { name: "Баталгаажуулах" }).click();
  await expect(page.getByText("99112233")).toBeVisible();

  // login card: username and no secret
  await page.getByRole("link", { name: "Нэвтрэх карт хэвлэх" }).click();
  await expect(page.getByText(username)).toBeVisible();
  await expect(page.getByText(/нууц үг байхгүй/)).toBeVisible();

  // CSV: problems are named by row and field, then a clean file is committed
  const dir = os.tmpdir();
  const bad = path.join(dir, `e2e-bad-${username}.csv`);
  const good = path.join(dir, `e2e-good-${username}.csv`);
  writeFileSync(bad, "username,display_name,phone\nBad Name,Бат,12345\n");
  writeFileSync(
    good,
    `username,display_name,phone\n${username}a,Сараа,88112233\n${username}b,Дорж,\n`,
  );
  await page.getByRole("link", { name: "CSV импорт" }).click();
  await page.getByLabel("CSV файл (UTF-8)").setInputFiles(bad);
  await page.getByRole("button", { name: "Урьдчилан харах" }).click();
  await expect(page.getByText(/Мөр 2: Хэрэглэгчийн нэр буруу/)).toBeVisible();
  await expect(page.getByText(/Мөр 2: Утасны дугаар буруу/)).toBeVisible();
  await page.getByLabel("CSV файл (UTF-8)").setInputFiles(good);
  await page.getByRole("button", { name: "Урьдчилан харах" }).click();
  await expect(page.getByText("2 мөр бүртгэхэд бэлэн")).toBeVisible();
  await page.getByRole("button", { name: "2 хэрэглэгч бүртгэх" }).click();
  await page.getByRole("button", { name: "Баталгаажуулах" }).click();
  await expect(page.getByText(/2 хэрэглэгч бүртгэгдлээ/)).toBeVisible();
  rmSync(bad, { force: true });
  rmSync(good, { force: true });

  await page.getByRole("link", { name: "Аюулгүй байдлын дохио" }).click();
  await expect(page.getByRole("heading", { name: "Аюулгүй байдлын дохио" })).toBeVisible();

  // sign out ends the session
  await page.getByRole("button", { name: "Гарах" }).click();
  await expect(page).toHaveURL(/\/admin\/login$/);
  await page.goto("/admin/users");
  await expect(page).toHaveURL(/\/admin\/login$/);

  expect(cspViolations).toEqual([]);
});
