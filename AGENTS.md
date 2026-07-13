# Orion — Guidance for AI Agents and LLMs

This file contains rules and context for AI agents and LLMs contributing to or generating configurations for Orion. These rules supplement the project documentation and exist to prevent known anti-patterns.

## Configuration Anti-Patterns

### Do not combine `.keyword` fields with `wildcard:`

The `wildcard:` section in Orion configs generates OpenSearch wildcard queries for pattern/glob matching. The `.keyword` suffix on a field name denotes an exact-match (not-analyzed) field in OpenSearch. Placing a `.keyword` field under `wildcard:` is contradictory and **will be rejected by config validation**.

**Rules:**

- `.keyword` fields belong in **top-level metadata** for exact matching — never under `wildcard:`.
- `wildcard:` is **only** for fields that genuinely need glob/pattern matching (e.g., version prefixes like `ocpVersion: "4.17*"`).
- Do not use `wildcard:` as a general-purpose filter. If the value is known exactly, use top-level metadata with an exact match.

```yaml
# WRONG — rejected by validation
metadata:
  wildcard:
    upstreamJob.keyword: "*my-job-name*"

# CORRECT — exact match on a keyword field
metadata:
  upstreamJob.keyword: periodic-ci-my-exact-job-name

# CORRECT — pattern match on a non-keyword field
metadata:
  wildcard:
    ocpVersion: "4.17*"
```

See `docs/configuration.md` (Wildcard Matching section) for full documentation.
