# Orion — Guidance for AI Agents and LLMs

This file contains rules and context for AI agents and LLMs contributing to or generating configurations for Orion. These rules supplement the project documentation and exist to prevent known anti-patterns.

## Configuration Anti-Patterns

### Avoid leading `*` on `.keyword` fields under `wildcard:`

Do not use a leading `*` on `.keyword` fields in the `wildcard:` section. Prefer trailing wildcards or exact match in top-level metadata.

```yaml
# BAD — triggers warning
metadata:
  wildcard:
    upstreamJob.keyword: "*my-job-name*"

# OK
metadata:
  wildcard:
    upstreamJob.keyword: "my-job-name*"

# BETTER — exact match in top-level metadata
metadata:
  upstreamJob.keyword: periodic-ci-my-exact-job-name
```
