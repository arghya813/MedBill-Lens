#!/usr/bin/env node
/**
 * One command to run the whole app in development.
 *
 * Starts the FastAPI backend and the Vite frontend in a single terminal with
 * prefixed output, waits until both actually answer, then opens the browser.
 * Both already hot reload:
 *   - uvicorn --reload restarts on a change under backend/app
 *   - vite's HMR pushes CSS and React updates to the open tab
 *
 * Ctrl+C stops both. There are no dependencies beyond Node itself, which is
 * already required to build the frontend.
 *
 * Usage:
 *   node scripts/dev.mjs            start both, open the browser
 *   node scripts/dev.mjs --no-open  start both, leave the browser alone
 *   node scripts/dev.mjs --api-only start only the backend
 *   node scripts/dev.mjs --web-only start only the frontend
 */

import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import net from "node:net";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const BACKEND = path.join(ROOT, "backend");
const FRONTEND = path.join(ROOT, "frontend");

const API_PORT = 8000;
const WEB_PORT = 5173;
const WEB_URL = `http://localhost:${WEB_PORT}`;
const API_HEALTH = `http://127.0.0.1:${API_PORT}/api/health`;

const IS_WINDOWS = process.platform === "win32";
const PYTHON = path.join(BACKEND, ".venv", "Scripts", "python.exe");
const VITE_BIN = path.join(FRONTEND, "node_modules", "vite", "bin", "vite.js");

const args = new Set(process.argv.slice(2));
const OPEN_BROWSER = !args.has("--no-open");
const API_ONLY = args.has("--api-only");
const WEB_ONLY = args.has("--web-only");

const COLORS = {
  api: "\u001b[36m", // cyan
  web: "\u001b[35m", // magenta
  dim: "\u001b[2m",
  red: "\u001b[31m",
  green: "\u001b[32m",
  yellow: "\u001b[33m",
  reset: "\u001b[0m",
};

const paint = (color, text) => `${COLORS[color]}${text}${COLORS.reset}`;

// The readiness spinner rewrites one line in place, so any tagged log line has
// to erase it first or the two end up interleaved.
let progressActive = false;

function clearProgress() {
  if (!progressActive) return;
  process.stdout.write(`\r${" ".repeat(60)}\r`);
  progressActive = false;
}

/** Wraps a byte stream so every complete line carries the same tag. */
function pipeWithPrefix(source, stream, tag, color) {
  let carry = "";
  const emit = (text) => {
    if (stream === process.stdout) clearProgress();
    stream.write(text);
  };
  source.on("data", (chunk) => {
    const text = carry + chunk.toString();
    const lines = text.split(/\r?\n/);
    carry = lines.pop() ?? "";
    for (const line of lines) emit(`${paint(color, `[${tag}]`)} ${line}\n`);
    if (carry.length > 4096) {
      emit(`${paint(color, `[${tag}]`)} ${carry}\n`);
      carry = "";
    }
  });
  source.on("end", () => {
    if (carry.trim()) emit(`${paint(color, `[${tag}]`)} ${carry}\n`);
  });
}

/** Resolves true if one probe server can bind `port` on `host`. */
function canBind(port, host) {
  return new Promise((resolve) => {
    const probe = net.createServer();
    probe.once("error", () => resolve(false));
    probe.once("listening", () => probe.close(() => resolve(true)));
    probe.listen({ port, host });
  });
}

// Each address is probed separately on purpose. Windows and Linux will happily
// let a bind on :: succeed while another process holds 0.0.0.0 on the same port,
// and Vite may listen on ::1 while uvicorn listens on 127.0.0.1. A port is only
// free when every one of these can be bound.
const PROBE_HOSTS = ["127.0.0.1", "::1", "0.0.0.0"];

async function portIsFree(port) {
  const outcomes = await Promise.all(PROBE_HOSTS.map((host) => canBind(port, host)));
  return outcomes.every(Boolean);
}

/** Polls until `check` resolves truthy or the timeout expires. */
async function waitFor(label, timeoutMs, check) {
  const deadline = Date.now() + timeoutMs;
  let dots = 0;
  while (Date.now() < deadline) {
    if (await check()) {
      clearProgress();
      return true;
    }
    dots = (dots + 1) % 4;
    process.stdout.write(
      `${paint("dim", `   waiting for ${label}${".".repeat(dots)}`)}\r`,
    );
    progressActive = true;
    await new Promise((resolve) => setTimeout(resolve, 350));
  }
  clearProgress();
  return false;
}

async function responds(url) {
  try {
    const response = await fetch(url, { signal: AbortSignal.timeout(2000) });
    return response.ok;
  } catch {
    return false;
  }
}

function openInBrowser(url) {
  const [command, cmdArgs] =
    IS_WINDOWS
      ? ["cmd", ["/c", "start", "", url]]
      : process.platform === "darwin"
        ? ["open", [url]]
        : ["xdg-open", [url]];
  try {
    const child = spawn(command, cmdArgs, { stdio: "ignore", detached: true });
    child.on("error", () => {});
    child.unref();
  } catch {
    // A missing opener is not worth failing over; the URL is printed regardless.
  }
}

function fail(message, hint) {
  console.error(`\n${paint("red", "Cannot start:")} ${message}`);
  if (hint) console.error(`${paint("dim", hint)}`);
  console.error("");
  process.exit(1);
}

const children = [];
let shuttingDown = false;

function shutdown(code = 0) {
  if (shuttingDown) return;
  shuttingDown = true;
  console.log(`\n${paint("yellow", "Stopping")} backend and frontend...`);
  for (const child of children) {
    if (child.exitCode === null && child.signalCode === null) {
      // uvicorn's reloader spawns a child, so signal the whole job on Windows.
      if (IS_WINDOWS && child.pid) {
        try {
          spawn("taskkill", ["/pid", String(child.pid), "/T", "/F"], { stdio: "ignore" });
        } catch {
          child.kill("SIGTERM");
        }
      } else {
        child.kill("SIGTERM");
      }
    }
  }
  setTimeout(() => process.exit(code), 600).unref();
}

process.on("SIGINT", () => shutdown(0));
process.on("SIGTERM", () => shutdown(0));

function launch(tag, color, command, commandArgs, cwd) {
  const child = spawn(command, commandArgs, {
    cwd,
    env: { ...process.env, PYTHONUNBUFFERED: "1", FORCE_COLOR: "1" },
    stdio: ["inherit", "pipe", "pipe"],
    // Node refuses to spawn a .cmd/.bat without a shell, so only reach for one
    // when the command genuinely is a batch file.
    shell: IS_WINDOWS && /\.(cmd|bat)$/i.test(command),
  });
  children.push(child);
  pipeWithPrefix(child.stdout, process.stdout, tag, color);
  pipeWithPrefix(child.stderr, process.stderr, tag, color);
  child.on("exit", (code, signal) => {
    if (shuttingDown) return;
    const reason = signal ? `signal ${signal}` : `code ${code}`;
    console.error(`\n${paint("red", `[${tag}] exited with ${reason}.`)} Shutting down.`);
    shutdown(code === 0 ? 1 : (code ?? 1));
  });
  return child;
}

async function main() {
  console.log("");
  console.log(`  ${paint("green", "MedBill Lens")} ${paint("dim", "development servers")}`);
  console.log("");

  if (!existsSync(PYTHON)) {
    fail(
      `backend virtual environment not found at ${path.relative(ROOT, PYTHON)}`,
      "Create it first:\n     cd backend\n     python -m venv .venv\n     .venv\\Scripts\\pip install -r requirements.txt",
    );
  }

  if (!existsSync(path.join(FRONTEND, "node_modules"))) {
    fail(
      "frontend/node_modules is missing",
      "Install it first:\n     cd frontend\n     npm install",
    );
  }

  if (!API_ONLY && (await portIsFree(WEB_PORT)) === false) {
    fail(
      `port ${WEB_PORT} is already in use`,
      `Something is already serving on ${WEB_PORT}.\n     npx kill-port ${WEB_PORT}`,
    );
  }

  if (!WEB_ONLY && (await portIsFree(API_PORT)) === false) {
    fail(
      `port ${API_PORT} is already in use`,
      `Another copy of the backend is probably still running.\n     npx kill-port ${API_PORT}`,
    );
  }

  if (!WEB_ONLY) {
    launch("api", "api", PYTHON, [
      "-m",
      "uvicorn",
      "app.main:app",
      "--reload",
      "--host",
      "127.0.0.1",
      "--port",
      String(API_PORT),
    ], BACKEND);
    console.log(`  ${paint("api", "[api]")} starting FastAPI on port ${API_PORT}`);
  }

  if (!API_ONLY) {
    // Running Vite's entry through Node avoids `npm.cmd`, which cannot be
    // spawned directly on modern Node, and keeps the log free of npm noise.
    const webArgs = ["--port", String(WEB_PORT), "--strictPort"];
    launch(
      "web",
      "web",
      existsSync(VITE_BIN) ? process.execPath : (IS_WINDOWS ? "npm.cmd" : "npm"),
      existsSync(VITE_BIN) ? [VITE_BIN, ...webArgs] : ["run", "dev", "--", ...webArgs],
      FRONTEND,
    );
    console.log(`  ${paint("web", "[web]")} starting Vite on port ${WEB_PORT}`);
  }

  console.log("");
  const results = [];
  if (!WEB_ONLY) {
    results.push(["backend", await waitFor("the backend", 60_000, () => responds(API_HEALTH))]);
  }
  if (!API_ONLY) {
    results.push(["frontend", await waitFor("the frontend", 60_000, () => responds(WEB_URL))]);
  }

  const slow = results.filter(([, ok]) => !ok).map(([name]) => name);
  if (slow.length > 0) {
    console.error("");
    console.error(`${paint("red", "These did not come up in time:")} ${slow.join(", ")}`);
    console.error(`${paint("dim", "Read the tagged output above for the actual error.")}`);
    console.error("");
    shutdown(1);
    return;
  }

  console.log("");
  console.log(`  ${paint("green", "Ready.")}`);
  if (!WEB_ONLY) console.log(`  ${paint("api", "[api]")}  ${paint("dim", API_HEALTH)}`);
  if (!API_ONLY) console.log(`  ${paint("web", "[web]")}  ${paint("dim", WEB_URL)}`);
  console.log(
    `  ${paint("dim", "Both reload on save. Press Ctrl+C here to stop both.")}`,
  );
  console.log("");

  if (!API_ONLY && OPEN_BROWSER) {
    openInBrowser(WEB_URL);
  }
}

main().catch((error) => {
  console.error(error);
  shutdown(1);
});