// PostToolUse hook: format the edited file. Cross-platform (Windows/macOS/Linux), no jq needed.
// Silent on success and on missing tools — never blocks the edit.
import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";

let input = "";
for await (const chunk of process.stdin) input += chunk;

let file;
try {
  file = JSON.parse(input)?.tool_input?.file_path;
} catch {
  process.exit(0);
}
if (!file) process.exit(0);

const root = process.env.CLAUDE_PROJECT_DIR || process.cwd();
const abs = path.resolve(root, file);
const rel = path.relative(root, abs).split(path.sep).join("/");
if (rel.startsWith("..") || rel.startsWith("_archive/") || rel.startsWith("seed/")) process.exit(0);

// No shell: the file path is passed as a plain argv entry, so shell metacharacters in it are inert.
// uv is a real executable (uv.exe on Windows); biome is run through node to avoid the pnpm .cmd shim.
const run = (cmd, args, cwd) =>
  spawnSync(cmd, args, { cwd, stdio: "ignore", shell: false, timeout: 20000 });

const biome = path.join(root, "node_modules", "@biomejs", "biome", "bin", "biome");
if (/\.pyi?$/.test(abs) && existsSync(path.join(root, "backend", "pyproject.toml"))) {
  const cwd = path.join(root, "backend");
  run("uv", ["run", "ruff", "format", "--", abs], cwd);
  run("uv", ["run", "ruff", "check", "--fix", "--", abs], cwd);
} else if (
  /\.(ts|tsx|js|jsx|mjs|json|jsonc)$/.test(abs) &&
  existsSync(path.join(root, "biome.json")) &&
  existsSync(biome)
) {
  run(process.execPath, [biome, "check", "--write", "--no-errors-on-unmatched", abs], root);
}
process.exit(0);
