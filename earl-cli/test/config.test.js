const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const { findDotEnv, parseDotEnv, applyEnv, resolveConfig } = require("../src/config.js");

test("findDotEnv searches parents", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "earl-config-"));
  const child = path.join(root, "a", "b");
  fs.mkdirSync(child, { recursive: true });
  fs.writeFileSync(path.join(root, ".env"), "AI_AGENT_SERVER_URL=http://example\n");

  const found = findDotEnv(child);
  assert.equal(found, path.join(root, ".env"));
});

test("parseDotEnv parses simple key/value lines", () => {
  const parsed = parseDotEnv(`
# comment
AI_AGENT_SERVER_URL=http://x
export AI_AGENT_TIMEOUT=42
QUOTED="hello world"
`);
  assert.equal(parsed.AI_AGENT_SERVER_URL, "http://x");
  assert.equal(parsed.AI_AGENT_TIMEOUT, "42");
  assert.equal(parsed.QUOTED, "hello world");
});

test("applyEnv does not override existing by default", () => {
  const env = { AI_AGENT_TIMEOUT: "10" };
  applyEnv({ AI_AGENT_TIMEOUT: "99", AI_AGENT_SERVER_URL: "http://y" }, env, { override: false });
  assert.equal(env.AI_AGENT_TIMEOUT, "10");
  assert.equal(env.AI_AGENT_SERVER_URL, "http://y");
});

test("resolveConfig defaults and parses timeout", () => {
  const cfg = resolveConfig({ AI_AGENT_SERVER_URL: "", AI_AGENT_TIMEOUT: "not-a-number" });
  assert.equal(cfg.serverUrl, "http://127.0.0.1:8000");
  assert.equal(cfg.timeoutSeconds, 30);
});

