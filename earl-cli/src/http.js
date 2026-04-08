async function requestJson({
  method,
  baseUrl,
  path,
  payload,
  timeoutSeconds,
  fetchImpl,
}) {
  const url = `${String(baseUrl || "").replace(/\/+$/, "")}${path}`;
  const controller = new AbortController();
  const ms = Math.max(1, Number(timeoutSeconds || 30)) * 1000;
  const timer = setTimeout(() => controller.abort(), ms);
  const fetchFn = fetchImpl || globalThis.fetch;

  try {
    const init = {
      method,
      signal: controller.signal,
      headers: {},
    };
    if (method !== "GET") {
      init.headers["content-type"] = "application/json";
      init.body = JSON.stringify(payload || {});
    }

    const response = await fetchFn(url, init);
    const statusCode = response.status;
    const text = await response.text();

    let data;
    try {
      data = text ? JSON.parse(text) : {};
      if (!data || typeof data !== "object" || Array.isArray(data)) {
        data = { status: "error", error: "Non-object JSON response", data };
      }
    } catch {
      data = { status: "error", error: "Response was not valid JSON", raw: text };
    }

    return { ok: statusCode >= 200 && statusCode < 300, statusCode, payload: data };
  } catch (e) {
    const msg = e && e.name === "AbortError" ? "Request timed out" : String(e && e.message ? e.message : e);
    return { ok: false, statusCode: 0, payload: { status: "error", error: msg } };
  } finally {
    clearTimeout(timer);
  }
}

module.exports = { requestJson };

