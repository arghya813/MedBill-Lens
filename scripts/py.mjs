#!/usr/bin/env node
/**
 * Runs a command with the backend's virtualenv Python.
 *
 * npm's script runner goes through cmd.exe on Windows, which will not accept a
 * forward-slash path to an executable. Rather than hardcode `\\` separators and
 * lose the ability to run anywhere else, the npm scripts call this instead.
 *
 * Usage:
 *   node scripts/py.mjs -m pytest -q          cwd is backend/
 *   node scripts/py.mjs --cwd=root scripts/serve_dist.py
 *   node scripts/py.mjs --cwd=backend scripts/fullstack_check.py
 */

import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const BACKEND = path.join(ROOT, "backend");

const IS_WINDOWS = process.platform === "win32";

function venvPython() {
  const candidates = IS_WINDOWS
    ? [path.join(BACKEND, ".venv", "Scripts", "python.exe")]
    : [path.join(BACKEND, ".venv", "bin", "python"), path.join(BACKEND, ".venv", "bin", "python3")];
  for (const candidate of candidates) {
    if (existsSync(candidate)) return candidate;
  }
  return null;
}

const raw = process.argv.slice(2);
let cwd = BACKEND;
const rest = [];
for (const arg of raw) {
  if (arg === "--cwd=root") cwd = ROOT;
  else if (arg.startsWith("--cwd=")) cwd = path.resolve(ROOT, arg.slice(6));
  else rest.push(arg);
}

const python = venvPython();
if (!python) {
  console.error("Backend virtualenv not found. Create it with:");
  console.error("  cd backend");
  console.error("  python -m venv .venv");
  console.error("  .venv/Scripts/pip install -r requirements.txt");
  process.exit(1);
}

// Running `python scripts/foo.py` puts backend/scripts on sys.path, not
// backend/, so `import app` needs the project root on PYTHONPATH.
const existing = process.env.PYTHONPATH ?? "";
const pythonPath = [BACKEND, existing].filter(Boolean).join(IS_WINDOWS ? ";" : ":");

const child = spawn(python, rest, {
  cwd,
  env: {
    ...process.env,
    PYTHONUNBUFFERED: "1",
    PYTHONIOENCODING: "utf-8",
    PYTHONPATH: pythonPath,
  },
  stdio: "inherit",
  shell: false,
});

child.on("error", (error) => {
  console.error(`Failed to run ${python}: ${error.message}`);
  process.exit(1);
});

child.on("exit", (code, signal) => {
  process.exit(signal ? 1 : (code ?? 0));
});