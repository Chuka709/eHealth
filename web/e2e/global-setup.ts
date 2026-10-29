import { execFileSync } from "node:child_process";
import { randomBytes } from "node:crypto";
import { mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";

import { randomBase32 } from "./totp";

export const AUTH_FILE = path.join(process.cwd(), "e2e", ".auth", "admin.json");

/**
 * A throwaway super admin for this run, created the way `just create-admin` does (owner role,
 * migrate container). Its password and TOTP secret are random, kept in a gitignored file for
 * the tests and never printed.
 */
export default function globalSetup() {
  const root = path.join(process.cwd(), "..");
  const admin = {
    username: `e2e${randomBytes(4).toString("hex")}`,
    password: `E2E ${randomBytes(12).toString("base64url")} нууц`,
    secret: randomBase32(),
  };
  const script = [
    "import asyncio, os",
    "from labtrack.admin.cli import create_admin",
    "from labtrack.core.security import hash_password",
    "from labtrack.keys import get_key_provider",
    "asyncio.run(create_admin(os.environ['MIGRATION_DATABASE_URL'], get_key_provider(),",
    "  username=os.environ['E2E_USER'], display_name='E2E', role='super_admin',",
    "  password_hash=hash_password(os.environ['E2E_PASSWORD']), totp_secret=os.environ['E2E_SECRET']))",
  ].join("\n");
  execFileSync(
    "docker",
    [
      "compose",
      "-f",
      "infra/docker-compose.yml",
      "--env-file",
      ".env",
      "run",
      "--rm",
      "-e",
      "E2E_USER",
      "-e",
      "E2E_PASSWORD",
      "-e",
      "E2E_SECRET",
      "migrate",
      "python",
      "-c",
      script,
    ],
    {
      cwd: root,
      env: {
        ...process.env,
        E2E_USER: admin.username,
        E2E_PASSWORD: admin.password,
        E2E_SECRET: admin.secret,
      },
      stdio: ["ignore", "ignore", "inherit"],
    },
  );
  mkdirSync(path.dirname(AUTH_FILE), { recursive: true });
  writeFileSync(AUTH_FILE, JSON.stringify(admin), { mode: 0o600 });
}
