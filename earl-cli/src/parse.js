function usageText({ version, command } = {}) {
  const v = version ? ` v${version}` : "";
  if (command && command !== "ask" && command !== "session" && command !== "workflow" && command !== "tools" && command !== "fix") {
    // Keep detailed help lightweight; top-level help is the source of truth.
    return `earl${v}\n\nRun \`earl --help\` for full usage.\n`;
  }

  return (
    `earl${v} - CLI for the AI Agent Server\n\n` +
    `Usage:\n` +
    `  earl [global options] <command> [subcommand] [options]\n\n` +
    `Global options:\n` +
    `  --server-url <url>     Agent server base URL (default: http://127.0.0.1:8000)\n` +
    `  --timeout <seconds>    HTTP timeout in seconds (default: 30)\n` +
    `  --output <human|json>  Output mode (default: human)\n` +
    `  --session-id <id>      Default session id for commands\n` +
    `  --help                 Show help\n` +
    `  --version              Show version\n\n` +
    `Commands:\n` +
    `  health\n` +
    `  ask <prompt>\n` +
    `  session create|get|list|cleanup\n` +
    `  workflow sync|async|get\n` +
    `  tools run|read|write|list-dir|grep-search|diagnostics|git-status|git-diff|apply-patch|query-index\n` +
    `  fix analyze-failure|assisted-fix\n\n` +
    `Environment:\n` +
    `  AI_AGENT_SERVER_URL, AI_AGENT_TIMEOUT are loaded from a .env in the current directory (or a parent).\n`
  );
}

function isLongOpt(token) {
  return typeof token === "string" && token.startsWith("--") && token.length > 2;
}

function coerceValue(type, raw, name) {
  if (type === "string") return String(raw);
  if (type === "number") {
    const n = Number(raw);
    if (!Number.isFinite(n)) throw new Error(`Invalid number for --${name}`);
    return n;
  }
  if (type === "boolean") return Boolean(raw);
  return raw;
}

function parseKnownOptions(argv, defs) {
  const options = {};
  const rest = [];
  const known = new Set(Object.keys(defs || {}));
  for (const [k, v] of Object.entries(defs || {})) {
    if (Object.prototype.hasOwnProperty.call(v, "default")) options[k] = v.default;
  }

  for (let i = 0; i < argv.length; i += 1) {
    const token = argv[i];
    if (!isLongOpt(token)) {
      rest.push(token);
      continue;
    }
    if (token === "--") {
      rest.push(...argv.slice(i + 1));
      break;
    }

    const isNo = token.startsWith("--no-");
    const eqIdx = token.indexOf("=");
    const flagPart = eqIdx >= 0 ? token.slice(0, eqIdx) : token;
    const inlineValue = eqIdx >= 0 ? token.slice(eqIdx + 1) : null;
    const nameRaw = isNo ? flagPart.slice(5) : flagPart.slice(2);
    const def = defs[nameRaw];
    if (!known.has(nameRaw) || !def) {
      rest.push(token);
      continue;
    }

    if (def.type === "boolean") {
      options[nameRaw] = isNo ? false : true;
      continue;
    }

    let value = null;
    if (inlineValue !== null) {
      value = inlineValue;
    } else {
      i += 1;
      if (i >= argv.length) throw new Error(`Missing value for --${nameRaw}`);
      value = argv[i];
    }
    options[nameRaw] = coerceValue(def.type, value, nameRaw);
  }

  return { options, rest };
}

function parseOptionsStrict(argv, defs) {
  const options = {};
  const positionals = [];
  const known = new Set(Object.keys(defs || {}));
  for (const [k, v] of Object.entries(defs || {})) {
    if (Object.prototype.hasOwnProperty.call(v, "default")) options[k] = v.default;
  }

  for (let i = 0; i < argv.length; i += 1) {
    const token = argv[i];
    if (!isLongOpt(token)) {
      positionals.push(token);
      continue;
    }
    if (token === "--") {
      positionals.push(...argv.slice(i + 1));
      break;
    }

    const isNo = token.startsWith("--no-");
    const eqIdx = token.indexOf("=");
    const flagPart = eqIdx >= 0 ? token.slice(0, eqIdx) : token;
    const inlineValue = eqIdx >= 0 ? token.slice(eqIdx + 1) : null;
    const nameRaw = isNo ? flagPart.slice(5) : flagPart.slice(2);
    const def = defs[nameRaw];
    if (!known.has(nameRaw) || !def) {
      throw new Error(`Unknown option: ${token}`);
    }

    if (def.type === "boolean") {
      options[nameRaw] = isNo ? false : true;
      continue;
    }

    let value = null;
    if (inlineValue !== null) {
      value = inlineValue;
    } else {
      i += 1;
      if (i >= argv.length) throw new Error(`Missing value for --${nameRaw}`);
      value = argv[i];
    }
    options[nameRaw] = coerceValue(def.type, value, nameRaw);
  }

  for (const [k, v] of Object.entries(defs || {})) {
    if (v && v.required && (options[k] == null || options[k] === "")) {
      throw new Error(`Missing required option: --${k}`);
    }
  }

  return { options, positionals };
}

module.exports = { parseKnownOptions, parseOptionsStrict, usageText };
