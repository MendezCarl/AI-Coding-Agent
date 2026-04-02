# Instruction System

## Source Directory

Instruction documents live in docs/instructions/.

General project docs under docs/ are not model-facing by default.

## Hard-Truth Convention

- If a markdown filename is ALL-CAPS, it is a hard-truth file.
- Hard truths are non-negotiable guidance.
- docs/README.md is excluded from instruction loading.

Examples:
- docs/instructions/SECURITY_RULES.md -> hard truth
- docs/instructions/style.md -> normal guidance

## Planned Assembly Order

1. Hard truths (ALL-CAPS docs)
2. Normal docs guidance
3. Retrieved repository context
4. User request

## Implementation Notes

- AskRequest includes use_instructions (default true).
- AskRequest includes include_legacy_instruction_docs (default false) for compatibility with previous docs-wide behavior.
- Instruction loading uses a lightweight in-memory cache keyed by file path, mtime, and size.
- Cache invalidates automatically when docs markdown files change.
- Response includes instruction-source metadata for traceability.

## Traceability

Responses should include instruction-source metadata so behavior can be audited.
