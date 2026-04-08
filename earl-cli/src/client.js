const { requestJson } = require("./http.js");

class ApiClient {
  constructor({ baseUrl, timeoutSeconds }) {
    this.baseUrl = String(baseUrl || "").replace(/\/+$/, "");
    this.timeoutSeconds = Number(timeoutSeconds || 30);
  }

  async get(path) {
    return requestJson({
      method: "GET",
      baseUrl: this.baseUrl,
      path,
      payload: null,
      timeoutSeconds: this.timeoutSeconds,
    });
  }

  async post(path, payload) {
    return requestJson({
      method: "POST",
      baseUrl: this.baseUrl,
      path,
      payload: payload || {},
      timeoutSeconds: this.timeoutSeconds,
    });
  }
}

module.exports = { ApiClient };

