import { execFileSync } from "node:child_process";
import { existsSync, readFileSync, rmSync } from "node:fs";
import path from "node:path";

import { AUTH_FILE } from "./global-setup";

/** The run's throwaway admin is disabled (sessions ended) and its credentials file removed. */
export default function globalTeardown() {
  if (!existsSync(AUTH_FILE)) return;
  const { username } = JSON.parse(readFileSync(AUTH_FILE, "utf8")) as { username: string };
  if (/^e2e[0-9a-f]{8}$/.test(username)) {
    const sql =
      `update users set account_status = 'disabled' where username = '${username}';` +
      ` update admin_sessions set revoked_at = now(), revoked_reason = 'logout'` +
      ` where revoked_at is null and admin_id = (select id from users where username = '${username}');`;
    execFileSync(
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
        "-v",
        "ON_ERROR_STOP=1",
        "-qc",
        sql,
      ],
      { cwd: path.join(process.cwd(), ".."), stdio: ["ignore", "ignore", "inherit"] },
    );
  }
  rmSync(AUTH_FILE, { force: true });
}
