const test = require("node:test");
const assert = require("node:assert/strict");

const { requestJson } = require("../src/http.js");

test("requestJson wraps non-object JSON responses", async () => {
  const fakeFetch = async () => ({
    status: 200,
    async text() {
      return JSON.stringify(["not", "an", "object"]);
    },
  });

  const res = await requestJson({
    method: "GET",
    baseUrl: "http://example",
    path: "/x",
    payload: null,
    timeoutSeconds: 1,
    fetchImpl: fakeFetch,
  });

  assert.equal(res.ok, true);
  assert.equal(res.payload.status, "error");
  assert.equal(res.payload.error, "Non-object JSON response");
});

test("requestJson wraps invalid JSON", async () => {
  const fakeFetch = async () => ({
    status: 200,
    async text() {
      return "not-json";
    },
  });

  const res = await requestJson({
    method: "GET",
    baseUrl: "http://example",
    path: "/x",
    payload: null,
    timeoutSeconds: 1,
    fetchImpl: fakeFetch,
  });

  assert.equal(res.ok, true);
  assert.equal(res.payload.status, "error");
  assert.equal(res.payload.error, "Response was not valid JSON");
});

