function stableStringify(obj) {
  return JSON.stringify(obj, null, 2);
}

function printResult(payload, outputMode = "human") {
  const mode = String(outputMode || "human").toLowerCase() === "json" ? "json" : "human";
  const data = payload && typeof payload === "object" ? payload : { status: "error", error: "Invalid payload" };

  if (mode === "json") {
    // eslint-disable-next-line no-console
    console.log(stableStringify(data));
    return;
  }

  const handled = new Set();
  const status = data.status;
  if (status != null) handled.add("status");
  if (status === "ok") {
    // eslint-disable-next-line no-console
    console.log("ok");
  } else if (status != null) {
    // eslint-disable-next-line no-console
    console.log(String(status));
  }

  if (Object.prototype.hasOwnProperty.call(data, "response")) {
    handled.add("response");
    // eslint-disable-next-line no-console
    console.log(String(data.response));
  }

  if (Object.prototype.hasOwnProperty.call(data, "error")) {
    handled.add("error");
    // eslint-disable-next-line no-console
    console.log(`error: ${String(data.error)}`);
  }

  const run = data.run;
  if (run && typeof run === "object" && !Array.isArray(run)) {
    handled.add("run");
    const runId = run.id || "<unknown>";
    const runStatus = run.status || "unknown";
    const completed = run.completed_steps;
    const total = run.total_steps;
    const failureReason = run.failure_reason;
    let progress = "";
    if (completed != null && total != null) progress = ` (${completed}/${total})`;
    // eslint-disable-next-line no-console
    console.log(
      failureReason
        ? `run ${runId}: ${runStatus}${progress}, reason=${failureReason}`
        : `run ${runId}: ${runStatus}${progress}`
    );
  }

  const remaining = {};
  for (const [k, v] of Object.entries(data)) {
    if (!handled.has(k)) remaining[k] = v;
  }
  if (Object.keys(remaining).length > 0) {
    // eslint-disable-next-line no-console
    console.log(stableStringify(remaining));
  }
}

module.exports = { printResult };

