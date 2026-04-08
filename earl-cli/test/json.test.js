const test = require("node:test");
const assert = require("node:assert/strict");

const { parseJsonArray, parseJsonObject } = require("../src/json.js");

test("parseJsonObject rejects arrays", () => {
  assert.throws(() => parseJsonObject("[]", "metadata_json"), /must decode to an object/);
});

test("parseJsonArray rejects objects", () => {
  assert.throws(() => parseJsonArray("{}", "steps_json"), /must decode to an array/);
});

