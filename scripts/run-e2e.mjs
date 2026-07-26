import { execFileSync, spawn } from "node:child_process";
import { existsSync } from "node:fs";
import process from "node:process";

const isWindows = process.platform === "win32";
const pythonExecutable = isWindows
  ? ".venv\\Scripts\\python.exe"
  : ".venv/bin/python";
const playwrightCli = "node_modules/@playwright/test/cli.js";
const children = [];
const managedListenerPids = new Set();

function failIfMissing(path, instruction) {
  if (!existsSync(path)) {
    throw new Error(`${path} is missing. ${instruction}`);
  }
}

function start(command, args, env) {
  const child = spawn(command, args, {
    cwd: process.cwd(),
    detached: !isWindows,
    env: { ...process.env, ...env },
    stdio: "inherit",
  });
  children.push(child);
  return child;
}

async function waitForUrl(url, child, timeoutMs = 120_000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (child.exitCode !== null) {
      throw new Error(`${url} server exited with code ${child.exitCode}.`);
    }
    try {
      const response = await fetch(url);
      if (response.ok) {
        return;
      }
    } catch {
      // The server is still starting.
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error(`Timed out waiting for ${url}.`);
}

function stopProcessTree(child) {
  if (!child.pid || child.exitCode !== null) {
    return;
  }
  if (isWindows) {
    try {
      process.kill(child.pid, "SIGKILL");
    } catch {
      // The process already exited.
    }
    return;
  }
  try {
    process.kill(-child.pid, "SIGTERM");
  } catch {
    // The process already exited.
  }
}

function findWindowsListenerPids(ports) {
  if (!isWindows) {
    return [];
  }
  const output = execFileSync("netstat", ["-ano", "-p", "tcp"], {
    encoding: "utf8",
  });
  const portSet = new Set(ports.map(String));
  const pids = new Set();
  for (const line of output.split(/\r?\n/)) {
    const fields = line.trim().split(/\s+/);
    if (fields.length < 5 || fields[3] !== "LISTENING") {
      continue;
    }
    const localPort = fields[1]?.split(":").at(-1);
    const pid = Number(fields.at(-1));
    if (localPort && portSet.has(localPort) && Number.isInteger(pid)) {
      pids.add(pid);
    }
  }
  return [...pids];
}

function stopManagedListeners() {
  for (const pid of managedListenerPids) {
    try {
      process.kill(pid, "SIGKILL");
    } catch {
      // The listener already exited.
    }
  }
}

async function main() {
  failIfMissing(
    pythonExecutable,
    "Create the Python virtual environment and install backend dependencies.",
  );
  failIfMissing(playwrightCli, "Run npm install first.");

  const backend = start(
    pythonExecutable,
    [
      "-m",
      "uvicorn",
      "backend.main:app",
      "--host",
      "127.0.0.1",
      "--port",
      "8011",
    ],
    {
      APP_ENV: "test",
      E2E_TEST_MODE: "true",
      ENABLE_MOCK_LLM: "true",
      FRONTEND_ORIGINS: "http://127.0.0.1:4331",
      GENERATOR_TIMEOUT_SECONDS: "1",
      RUN_TIMEOUT_SECONDS: "20",
      MOCK_GENERATOR_DELAY_SECONDS: "0.02",
      MOCK_REVIEWER_DELAY_SECONDS: "0.35",
      MOCK_OPTIMIZER_DELAY_SECONDS: "0.03",
    },
  );
  await waitForUrl("http://127.0.0.1:8011/api/health", backend);
  for (const pid of findWindowsListenerPids([8011])) {
    managedListenerPids.add(pid);
  }

  const frontend = start(
    process.execPath,
    [
      "node_modules/astro/astro.js",
      "dev",
      "--host",
      "127.0.0.1",
      "--port",
      "4331",
    ],
    {
      ASTRO_TELEMETRY_DISABLED: "1",
      E2E_TEST_MODE: "true",
      PUBLIC_API_BASE_URL: "http://127.0.0.1:4331",
      API_PROXY_TARGET: "http://127.0.0.1:8011",
    },
  );
  await waitForUrl("http://127.0.0.1:4331", frontend);
  for (const pid of findWindowsListenerPids([4331])) {
    managedListenerPids.add(pid);
  }

  const playwright = start(
    process.execPath,
    [playwrightCli, "test", ...process.argv.slice(2)],
    { E2E_EXTERNAL_SERVERS: "true" },
  );
  const exitCode = await new Promise((resolve, reject) => {
    playwright.once("error", reject);
    playwright.once("exit", (code) => resolve(code ?? 1));
  });
  process.exitCode = exitCode;
}

try {
  await main();
} finally {
  for (const child of children.reverse()) {
    stopProcessTree(child);
  }
  stopManagedListeners();
}
