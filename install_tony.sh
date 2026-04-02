#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="${HOME}/.local/bin"
TARGET_PATH="${TARGET_DIR}/tony"

mkdir -p "$TARGET_DIR"
ln -sfn "$ROOT_DIR/tony" "$TARGET_PATH"

echo "Installed: $TARGET_PATH -> $ROOT_DIR/tony"

case ":${PATH}:" in
  *":${TARGET_DIR}:"*)
    echo "PATH already contains ${TARGET_DIR}"
    ;;
  *)
    echo "Add this to your shell profile if needed:"
    echo "export PATH=\"${TARGET_DIR}:\$PATH\""
    ;;
esac
