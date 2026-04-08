const test = require("node:test");
const assert = require("node:assert/strict");

const { parseKnownOptions, parseOptionsStrict } = require("../src/parse.js");

test("parseKnownOptions consumes recognized options and leaves rest", () => {
  const { options, rest } = parseKnownOptions(
    ["--server-url", "http://x", "ask", "hello", "--top-k", "5"],
    { "server-url": { type: "string" } }
  );
  assert.equal(options["server-url"], "http://x");
  assert.deepEqual(rest, ["ask", "hello", "--top-k", "5"]);
});

test("parseOptionsStrict errors on unknown options", () => {
  assert.throws(
    () => parseOptionsStrict(["--nope"], { help: { type: "boolean", default: false } }),
    /Unknown option/
  );
});

