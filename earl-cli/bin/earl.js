#!/usr/bin/env node
/* eslint-disable no-console */

const path = require("node:path");

function readVersion() {
  try {
    // When installed from npm, package.json sits next to bin/.
    // When run from the repo, it’s at earl-cli/package.json.
    // eslint-disable-next-line import/no-dynamic-require, global-require
    const pkg = require(path.join(__dirname, "..", "package.json"));
    return pkg && typeof pkg.version === "string" ? pkg.version : "0.0.0";
  } catch {
    return "0.0.0";
  }
}

async function main() {
  // eslint-disable-next-line import/no-dynamic-require, global-require
  const { run } = require(path.join(__dirname, "..", "src", "cli.js"));
  const exitCode = await run(process.argv.slice(2), { version: readVersion() });
  process.exitCode = exitCode;
}

main().catch((err) => {
  console.error(err && err.stack ? err.stack : String(err));
  process.exitCode = 1;
});

