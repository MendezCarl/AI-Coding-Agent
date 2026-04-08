const fs = require("node:fs");
const path = require("node:path");

const DEFAULT_SERVER_URL = "http://127.0.0.1:8000";
const DEFAULT_TIMEOUT_SECONDS = 30;

function findDotEnv(startDir) {
  let dir = path.resolve(startDir || process.cwd());
  while (true) {
    const candidate = path.join(dir, ".env");
    if (fs.existsSync(candidate) && fs.statSync(candidate).isFile()) return candidate;
    const parent = path.dirname(dir);
    if (parent === dir) return null;
    dir = parent;
  }
}

function parseDotEnv(contents) {
  const out = {};
  const lines = String(contents || "").split(/\r?\n/);
  for (const raw of lines) {
    const line = raw.trim();
    if (!line || line.startsWith("#")) continue;
    const cleaned = line.startsWith("export ") ? line.slice(7).trim() : line;
    const idx = cleaned.indexOf("=");
    if (idx <= 0) continue;
    const key = cleaned.slice(0, idx).trim();
    let value = cleaned.slice(idx + 1).trim();
    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    }
    if (key) out[key] = value;
  }
  return out;
}

function applyEnv(parsed, env, { override = false } = {}) {
  const target = env || process.env;
  for (const [k, v] of Object.entries(parsed || {})) {
    if (!override && target[k] != null && String(target[k]).length > 0) continue;
    target[k] = String(v);
  }
}

function loadEnvFromCwd() {
  const envPath = findDotEnv(process.cwd());
  if (!envPath) return { loaded: false, path: null };
  const contents = fs.readFileSync(envPath, "utf8");
  const parsed = parseDotEnv(contents);
  applyEnv(parsed, process.env, { override: false });
  return { loaded: true, path: envPath };
}

function resolveConfig(env) {
  const e = env || process.env;
  const rawUrl = (e.AI_AGENT_SERVER_URL || DEFAULT_SERVER_URL).trim();
  const serverUrl = rawUrl || DEFAULT_SERVER_URL;
  const rawTimeout = (e.AI_AGENT_TIMEOUT || String(DEFAULT_TIMEOUT_SECONDS)).trim();
  let timeoutSeconds = DEFAULT_TIMEOUT_SECONDS;
  const parsed = Number(rawTimeout);
  if (Number.isFinite(parsed) && parsed > 0) timeoutSeconds = parsed;
  return { serverUrl, timeoutSeconds };
}

module.exports = {
  DEFAULT_SERVER_URL,
  DEFAULT_TIMEOUT_SECONDS,
  findDotEnv,
  parseDotEnv,
  applyEnv,
  loadEnvFromCwd,
  resolveConfig,
};

