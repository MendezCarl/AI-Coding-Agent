const { ApiClient } = require("./client.js");
const { loadEnvFromCwd, resolveConfig } = require("./config.js");
const { parseJsonArray, parseJsonObject } = require("./json.js");
const { printResult } = require("./output.js");
const { sleep } = require("./time.js");
const { parseKnownOptions, parseOptionsStrict, usageText } = require("./parse.js");

const TERMINAL_STATUSES = new Set(["succeeded", "failed", "cancelled"]);

function normalizeOutputMode(value) {
  return String(value || "human").toLowerCase() === "json" ? "json" : "human";
}

function help({ version }) {
  return usageText({ version });
}

function toBool(value, fallback) {
  if (typeof value === "boolean") return value;
  return fallback;
}

async function handleWorkflowGet({
  client,
  outputMode,
  args,
  showProgressDefault,
  showEventsDefault,
}) {
  const defs = {
    "run-id": { type: "string", required: true },
    watch: { type: "boolean", default: false },
    "poll-interval": { type: "number", default: 1.0 },
    "max-polls": { type: "number", default: 120 },
    progress: { type: "boolean", default: showProgressDefault },
    events: { type: "boolean", default: showEventsDefault },
    help: { type: "boolean", default: false },
  };
  const { options, positionals } = parseOptionsStrict(args, defs);
  if (options.help) return { exitCode: 0, printed: true, text: "" };
  if (positionals.length !== 0) {
    return { exitCode: 1, printed: false, error: "Unexpected extra arguments" };
  }

  const runId = options["run-id"];
  const watch = Boolean(options.watch);

  const humanWatch = outputMode === "human";
  const showProgress = humanWatch ? toBool(options.progress, true) : false;
  const showEvents = humanWatch ? toBool(options.events, true) : false;

  async function fetchOnce() {
    return client.post("/get_workflow_run", { run_id: runId });
  }

  if (!watch) {
    const result = await fetchOnce();
    printResult(result.payload, outputMode);
    return { exitCode: result.ok ? 0 : 1 };
  }

  let attempts = 0;
  let lastStatus = null;
  let lastCompleted = null;
  const seenEventIds = new Set();
  const start = Date.now();
  const maxPolls = Number(options["max-polls"]);
  const pollIntervalSeconds = Number(options["poll-interval"]);

  // Poll loop
  while (attempts < maxPolls) {
    attempts += 1;
    const result = await fetchOnce();
    if (!result.ok) {
      printResult(result.payload, outputMode);
      return { exitCode: 1 };
    }

    const payload = result.payload || {};
    const run = payload.run && typeof payload.run === "object" ? payload.run : {};
    const status = run.status;

    if (showProgress) {
      const completed = run.completed_steps;
      const total = run.total_steps;
      const changed =
        attempts === 1 || status !== lastStatus || completed !== lastCompleted;
      if (changed) {
        const elapsedSeconds = (Date.now() - start) / 1000;
        let progress = "";
        if (completed != null && total != null) {
          progress = ` (${completed}/${total})`;
        }
        // eslint-disable-next-line no-console
        console.log(
          `watch attempt=${attempts} status=${status}${progress} elapsed=${elapsedSeconds.toFixed(
            1
          )}s`
        );
      }
      lastStatus = status;
      lastCompleted = completed;
    }

    if (showEvents) {
      const events = Array.isArray(payload.events) ? payload.events : [];
      for (const event of events) {
        if (!event || typeof event !== "object") continue;
        const eventId = event.id;
        if (eventId && seenEventIds.has(eventId)) continue;
        if (eventId) seenEventIds.add(eventId);
        const eventType = event.event_type || "event";
        const message = event.message || "";
        // eslint-disable-next-line no-console
        console.log(`event:${eventType} ${message}`);
      }
    }

    if (TERMINAL_STATUSES.has(status)) {
      printResult(payload, outputMode);
      return { exitCode: 0 };
    }

    await sleep(pollIntervalSeconds);
  }

  const elapsedSeconds = (Date.now() - start) / 1000;
  printResult(
    {
      status: "error",
      error: "Watch polling timed out before terminal workflow status",
      attempts,
      run_id: runId,
      elapsed_seconds: Math.round(elapsedSeconds * 1000) / 1000,
    },
    outputMode
  );
  return { exitCode: 1 };
}

async function run(argv, { version } = {}) {
  loadEnvFromCwd();
  const config = resolveConfig();

  const globalDefs = {
    "server-url": { type: "string" },
    timeout: { type: "number" },
    output: { type: "string" },
    "session-id": { type: "string" },
    "non-interactive": { type: "boolean", default: false },
    help: { type: "boolean", default: false },
    version: { type: "boolean", default: false },
  };

  const { options: globalOptions, rest } = parseKnownOptions(argv, globalDefs);

  if (globalOptions.version) {
    // eslint-disable-next-line no-console
    console.log(version || "0.0.0");
    return 0;
  }

  if (globalOptions.help || rest.length === 0) {
    // eslint-disable-next-line no-console
    console.log(help({ version }));
    return rest.length === 0 ? 0 : 0;
  }

  const serverUrl = (globalOptions["server-url"] || config.serverUrl).replace(
    /\/+$/,
    ""
  );
  const timeoutSeconds =
    globalOptions.timeout != null ? Number(globalOptions.timeout) : config.timeoutSeconds;
  const outputMode = normalizeOutputMode(globalOptions.output || "human");
  const defaultSessionId = globalOptions["session-id"] || null;

  const client = new ApiClient({ baseUrl: serverUrl, timeoutSeconds });

  const command = rest[0];
  const sub = rest[1];
  const tail = rest.slice(1);

  // Top-level commands
  if (command === "health") {
    const result = await client.get("/health");
    let payload = result.payload;
    if (result.ok && payload && typeof payload === "object" && payload.status == null) {
      payload = { status: "ok", ...payload };
    }
    printResult(payload, outputMode);
    return result.ok ? 0 : 1;
  }

  if (command === "ask") {
    const defs = {
      "session-id": { type: "string" },
      "session-context-turns": { type: "number", default: 8 },
      "use-instructions": { type: "boolean", default: true },
      "legacy-instruction-docs": { type: "boolean", default: false },
      "use-retrieval": { type: "boolean", default: true },
      "index-name": { type: "string", default: "knowledge" },
      "top-k": { type: "number", default: 5 },
      help: { type: "boolean", default: false },
    };
    const { options, positionals } = parseOptionsStrict(tail, defs);
    if (options.help) {
      // eslint-disable-next-line no-console
      console.log(usageText({ version, command: "ask" }));
      return 0;
    }
    if (positionals.length < 1) {
      printResult({ status: "error", error: "prompt is required" }, outputMode);
      return 1;
    }
    const prompt = positionals.join(" ");
    const payload = {
      prompt,
      session_id: options["session-id"] || defaultSessionId,
      session_context_turns: Number(options["session-context-turns"]),
      use_instructions: Boolean(options["use-instructions"]),
      include_legacy_instruction_docs: Boolean(options["legacy-instruction-docs"]),
      use_retrieval: Boolean(options["use-retrieval"]),
      index_name: String(options["index-name"]),
      top_k: Number(options["top-k"]),
    };
    const result = await client.post("/ask", payload);
    printResult(result.payload, outputMode);
    return result.ok ? 0 : 1;
  }

  if (command === "do") {
    const defs = {
      "session-id": { type: "string" },
      "max-steps": { type: "number", default: 12 },
      "plan-only": { type: "boolean", default: false },
      async: { type: "boolean", default: false },
      "allow-write": { type: "boolean", default: false },
      "metadata-json": { type: "string", default: "{}" },
      "use-instructions": { type: "boolean", default: true },
      "legacy-instruction-docs": { type: "boolean", default: false },
      "use-retrieval": { type: "boolean", default: true },
      "index-name": { type: "string", default: "knowledge" },
      "top-k": { type: "number", default: 5 },
      help: { type: "boolean", default: false },
    };
    const { options, positionals } = parseOptionsStrict(tail, defs);
    if (options.help) {
      // eslint-disable-next-line no-console
      console.log(usageText({ version, command: "do" }));
      return 0;
    }
    if (positionals.length < 1) {
      printResult({ status: "error", error: "task is required" }, outputMode);
      return 1;
    }

    let metadata;
    try {
      metadata = parseJsonObject(options["metadata-json"], "metadata_json");
    } catch (e) {
      printResult({ status: "error", error: String(e.message || e) }, outputMode);
      return 1;
    }

    const task = positionals.join(" ");
    const payload = {
      task,
      session_id: options["session-id"] || defaultSessionId,
      max_steps: Number(options["max-steps"]),
      plan_only: Boolean(options["plan-only"]),
      run_async: Boolean(options.async),
      allow_write: Boolean(options["allow-write"]),
      metadata,
      use_instructions: Boolean(options["use-instructions"]),
      include_legacy_instruction_docs: Boolean(options["legacy-instruction-docs"]),
      use_retrieval: Boolean(options["use-retrieval"]),
      index_name: String(options["index-name"]),
      top_k: Number(options["top-k"]),
    };
    const result = await client.post("/orchestrate_task", payload);
    printResult(result.payload, outputMode);
    return result.ok ? 0 : 1;
  }

  // Session
  if (command === "session") {
    if (!sub) {
      // eslint-disable-next-line no-console
      console.log(usageText({ version, command: "session" }));
      return 0;
    }
    const args = rest.slice(2);

    if (sub === "create") {
      const defs = {
        "ttl-hours": { type: "number", default: 168 },
        "metadata-json": { type: "string", default: "{}" },
        help: { type: "boolean", default: false },
      };
      const { options, positionals } = parseOptionsStrict(args, defs);
      if (options.help) {
        // eslint-disable-next-line no-console
        console.log(usageText({ version, command: "session create" }));
        return 0;
      }
      if (positionals.length !== 0) {
        printResult({ status: "error", error: "Unexpected extra arguments" }, outputMode);
        return 1;
      }
      let metadata;
      try {
        metadata = parseJsonObject(options["metadata-json"], "metadata_json");
      } catch (e) {
        printResult({ status: "error", error: `Invalid metadata_json: ${e.message}` }, outputMode);
        return 1;
      }
      const result = await client.post("/create_session", {
        ttl_hours: Number(options["ttl-hours"]),
        metadata,
      });
      printResult(result.payload, outputMode);
      return result.ok ? 0 : 1;
    }

    if (sub === "get") {
      const defs = {
        "session-id": { type: "string" },
        "include-messages": { type: "boolean", default: true },
        "include-turns": { type: "boolean", default: true },
        limit: { type: "number", default: 200 },
        offset: { type: "number", default: 0 },
        help: { type: "boolean", default: false },
      };
      const { options, positionals } = parseOptionsStrict(args, defs);
      if (options.help) {
        // eslint-disable-next-line no-console
        console.log(usageText({ version, command: "session get" }));
        return 0;
      }
      if (positionals.length !== 0) {
        printResult({ status: "error", error: "Unexpected extra arguments" }, outputMode);
        return 1;
      }
      const resolved = options["session-id"] || defaultSessionId;
      if (!resolved) {
        printResult({ status: "error", error: "session_id is required" }, outputMode);
        return 1;
      }
      const result = await client.post("/get_session", {
        session_id: resolved,
        include_messages: Boolean(options["include-messages"]),
        include_turns: Boolean(options["include-turns"]),
        limit: Number(options.limit),
        offset: Number(options.offset),
      });
      printResult(result.payload, outputMode);
      return result.ok ? 0 : 1;
    }

    if (sub === "list") {
      const defs = {
        limit: { type: "number", default: 50 },
        offset: { type: "number", default: 0 },
        "include-expired": { type: "boolean", default: false },
        help: { type: "boolean", default: false },
      };
      const { options, positionals } = parseOptionsStrict(args, defs);
      if (options.help) {
        // eslint-disable-next-line no-console
        console.log(usageText({ version, command: "session list" }));
        return 0;
      }
      if (positionals.length !== 0) {
        printResult({ status: "error", error: "Unexpected extra arguments" }, outputMode);
        return 1;
      }
      const result = await client.post("/list_sessions", {
        limit: Number(options.limit),
        offset: Number(options.offset),
        include_expired: Boolean(options["include-expired"]),
      });
      printResult(result.payload, outputMode);
      return result.ok ? 0 : 1;
    }

    if (sub === "cleanup") {
      const result = await client.post("/cleanup_expired_sessions", {});
      printResult(result.payload, outputMode);
      return result.ok ? 0 : 1;
    }

    printResult({ status: "error", error: `Unknown session subcommand: ${sub}` }, outputMode);
    return 1;
  }

  // Workflow
  if (command === "workflow") {
    if (!sub) {
      // eslint-disable-next-line no-console
      console.log(usageText({ version, command: "workflow" }));
      return 0;
    }

    const args = rest.slice(2);

    function parseWorkflowPayload({ stepsJson, metadataJson }) {
      const steps = parseJsonArray(stepsJson, "steps_json");
      for (let i = 0; i < steps.length; i += 1) {
        const item = steps[i];
        if (!item || typeof item !== "object" || Array.isArray(item)) {
          throw new Error(`step ${i + 1} must be an object`);
        }
        if (!("tool" in item)) {
          throw new Error(`step ${i + 1} must include 'tool'`);
        }
      }
      const metadata = parseJsonObject(metadataJson, "metadata_json");
      return { steps, metadata };
    }

    if (sub === "sync" || sub === "async") {
      const defs = {
        "steps-json": { type: "string", required: true },
        "metadata-json": { type: "string", default: "{}" },
        "session-id": { type: "string" },
        help: { type: "boolean", default: false },
      };
      const { options, positionals } = parseOptionsStrict(args, defs);
      if (options.help) {
        // eslint-disable-next-line no-console
        console.log(usageText({ version, command: `workflow ${sub}` }));
        return 0;
      }
      if (positionals.length !== 0) {
        printResult({ status: "error", error: "Unexpected extra arguments" }, outputMode);
        return 1;
      }

      let steps;
      let metadata;
      try {
        ({ steps, metadata } = parseWorkflowPayload({
          stepsJson: options["steps-json"],
          metadataJson: options["metadata-json"],
        }));
      } catch (e) {
        printResult({ status: "error", error: `Invalid workflow payload: ${e.message}` }, outputMode);
        return 1;
      }

      const payload = {
        steps,
        session_id: options["session-id"] || defaultSessionId,
        metadata,
      };
      const path = sub === "sync" ? "/execute_workflow_sync" : "/execute_workflow_async";
      const result = await client.post(path, payload);
      printResult(result.payload, outputMode);
      return result.ok ? 0 : 1;
    }

    if (sub === "get") {
      const result = await handleWorkflowGet({
        client,
        outputMode,
        args,
        showProgressDefault: true,
        showEventsDefault: true,
      });
      if (result.text) {
        // eslint-disable-next-line no-console
        console.log(result.text);
      }
      if (result.error) {
        printResult({ status: "error", error: result.error }, outputMode);
      }
      return result.exitCode;
    }

    printResult({ status: "error", error: `Unknown workflow subcommand: ${sub}` }, outputMode);
    return 1;
  }

  // Tools
  if (command === "tools") {
    if (!sub) {
      // eslint-disable-next-line no-console
      console.log(usageText({ version, command: "tools" }));
      return 0;
    }

    const args = rest.slice(2);
    async function simplePost(path, defs, buildPayload) {
      const { options, positionals } = parseOptionsStrict(args, defs);
      if (options.help) {
        // eslint-disable-next-line no-console
        console.log(usageText({ version, command: `tools ${sub}` }));
        return 0;
      }
      if (positionals.length !== 0) {
        printResult({ status: "error", error: "Unexpected extra arguments" }, outputMode);
        return 1;
      }
      const result = await client.post(path, buildPayload(options));
      printResult(result.payload, outputMode);
      return result.ok ? 0 : 1;
    }

    if (sub === "run") {
      return simplePost(
        "/run",
        {
          command: { type: "string", required: true },
          cwd: { type: "string" },
          timeout: { type: "number", default: 30 },
          help: { type: "boolean", default: false },
        },
        (o) => ({ command: o.command, cwd: o.cwd || null, timeout: Number(o.timeout) })
      );
    }
    if (sub === "read") {
      return simplePost(
        "/read",
        {
          path: { type: "string", required: true },
          "start-line": { type: "number" },
          "end-line": { type: "number" },
          help: { type: "boolean", default: false },
        },
        (o) => ({
          path: o.path,
          start_line: o["start-line"] != null ? Number(o["start-line"]) : null,
          end_line: o["end-line"] != null ? Number(o["end-line"]) : null,
        })
      );
    }
    if (sub === "write") {
      return simplePost(
        "/write",
        {
          path: { type: "string", required: true },
          content: { type: "string", required: true },
          "make-backup": { type: "boolean", default: true },
          "create-parents": { type: "boolean", default: true },
          help: { type: "boolean", default: false },
        },
        (o) => ({
          path: o.path,
          content: o.content,
          make_backup: Boolean(o["make-backup"]),
          create_parents: Boolean(o["create-parents"]),
        })
      );
    }
    if (sub === "list-dir") {
      return simplePost(
        "/list_dir",
        {
          path: { type: "string", default: "." },
          "include-hidden": { type: "boolean", default: false },
          help: { type: "boolean", default: false },
        },
        (o) => ({ path: o.path, include_hidden: Boolean(o["include-hidden"]) })
      );
    }
    if (sub === "grep-search") {
      return simplePost(
        "/grep_search",
        {
          query: { type: "string", required: true },
          path: { type: "string", default: "." },
          regex: { type: "boolean", default: false },
          "case-sensitive": { type: "boolean", default: false },
          "max-results": { type: "number", default: 200 },
          "include-hidden": { type: "boolean", default: false },
          help: { type: "boolean", default: false },
        },
        (o) => ({
          query: o.query,
          path: o.path,
          is_regex: Boolean(o.regex),
          case_sensitive: Boolean(o["case-sensitive"]),
          max_results: Number(o["max-results"]),
          include_hidden: Boolean(o["include-hidden"]),
        })
      );
    }
    if (sub === "diagnostics") {
      return simplePost(
        "/diagnostics",
        {
          path: { type: "string", default: "." },
          "include-hidden": { type: "boolean", default: false },
          help: { type: "boolean", default: false },
        },
        (o) => ({ path: o.path, include_hidden: Boolean(o["include-hidden"]) })
      );
    }
    if (sub === "git-status") {
      return simplePost(
        "/git_status",
        {
          path: { type: "string", default: "." },
          help: { type: "boolean", default: false },
        },
        (o) => ({ path: o.path })
      );
    }
    if (sub === "git-diff") {
      return simplePost(
        "/git_diff",
        {
          path: { type: "string", default: "." },
          staged: { type: "boolean", default: false },
          help: { type: "boolean", default: false },
        },
        (o) => ({ path: o.path, staged: Boolean(o.staged) })
      );
    }
    if (sub === "apply-patch") {
      return simplePost(
        "/apply_patch",
        {
          path: { type: "string", required: true },
          "old-text": { type: "string", required: true },
          "new-text": { type: "string", required: true },
          "replace-all": { type: "boolean", default: false },
          "create-backup": { type: "boolean", default: true },
          help: { type: "boolean", default: false },
        },
        (o) => ({
          path: o.path,
          old_text: o["old-text"],
          new_text: o["new-text"],
          replace_all: Boolean(o["replace-all"]),
          create_backup: Boolean(o["create-backup"]),
        })
      );
    }
    if (sub === "query-index") {
      return simplePost(
        "/query_index",
        {
          query: { type: "string", required: true },
          "index-name": { type: "string", default: "knowledge" },
          "top-k": { type: "number", default: 5 },
          topic: { type: "string" },
          help: { type: "boolean", default: false },
        },
        (o) => ({
          index_name: o["index-name"],
          query: o.query,
          top_k: Number(o["top-k"]),
          topic: o.topic || null,
        })
      );
    }

    printResult({ status: "error", error: `Unknown tools subcommand: ${sub}` }, outputMode);
    return 1;
  }

  // Fix
  if (command === "fix") {
    if (!sub) {
      // eslint-disable-next-line no-console
      console.log(usageText({ version, command: "fix" }));
      return 0;
    }
    const args = rest.slice(2);

    if (sub === "analyze-failure") {
      const defs = {
        "error-output": { type: "string", required: true },
        path: { type: "string" },
        "include-hidden": { type: "boolean", default: false },
        "max-search-results": { type: "number", default: 20 },
        help: { type: "boolean", default: false },
      };
      const { options, positionals } = parseOptionsStrict(args, defs);
      if (options.help) {
        // eslint-disable-next-line no-console
        console.log(usageText({ version, command: "fix analyze-failure" }));
        return 0;
      }
      if (positionals.length !== 0) {
        printResult({ status: "error", error: "Unexpected extra arguments" }, outputMode);
        return 1;
      }
      const result = await client.post("/analyze_failure", {
        error_output: options["error-output"],
        path: options.path || null,
        include_hidden: Boolean(options["include-hidden"]),
        max_search_results: Number(options["max-search-results"]),
      });
      printResult(result.payload, outputMode);
      return result.ok ? 0 : 1;
    }

    if (sub === "assisted-fix") {
      const defs = {
        path: { type: "string", required: true },
        "old-text": { type: "string", required: true },
        "new-text": { type: "string", required: true },
        approve: { type: "boolean", default: false },
        "create-backup": { type: "boolean", default: true },
        "verify-command": { type: "string" },
        "verify-cwd": { type: "string" },
        "verify-timeout": { type: "number", default: 60 },
        help: { type: "boolean", default: false },
      };
      const { options, positionals } = parseOptionsStrict(args, defs);
      if (options.help) {
        // eslint-disable-next-line no-console
        console.log(usageText({ version, command: "fix assisted-fix" }));
        return 0;
      }
      if (positionals.length !== 0) {
        printResult({ status: "error", error: "Unexpected extra arguments" }, outputMode);
        return 1;
      }
      if (!options.approve) {
        printResult({ status: "error", error: "assisted-fix requires --approve to proceed" }, outputMode);
        return 1;
      }
      const result = await client.post("/assisted_fix", {
        path: options.path,
        old_text: options["old-text"],
        new_text: options["new-text"],
        approved: true,
        create_backup: Boolean(options["create-backup"]),
        verify_command: options["verify-command"] || null,
        verify_cwd: options["verify-cwd"] || null,
        verify_timeout: Number(options["verify-timeout"]),
      });
      printResult(result.payload, outputMode);
      return result.ok ? 0 : 1;
    }

    printResult({ status: "error", error: `Unknown fix subcommand: ${sub}` }, outputMode);
    return 1;
  }

  printResult({ status: "error", error: `Unknown command: ${command}` }, outputMode);
  return 1;
}

module.exports = { run };
