function parseJsonObject(raw, label) {
  let data;
  try {
    data = JSON.parse(String(raw || ""));
  } catch (e) {
    throw new Error(`${label} must be valid JSON`);
  }
  if (!data || typeof data !== "object" || Array.isArray(data)) {
    throw new Error(`${label} must decode to an object`);
  }
  return data;
}

function parseJsonArray(raw, label) {
  let data;
  try {
    data = JSON.parse(String(raw || ""));
  } catch (e) {
    throw new Error(`${label} must be valid JSON`);
  }
  if (!Array.isArray(data)) {
    throw new Error(`${label} must decode to an array`);
  }
  return data;
}

module.exports = { parseJsonArray, parseJsonObject };

