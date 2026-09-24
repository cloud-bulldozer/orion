# MaaS AI Gateway Performance Configs

Reference for the Orion configs that track the MaaS (Models-as-a-Service) AI
Gateway performance periodics defined in
[openshift/release](https://github.com/openshift/release/tree/master/ci-operator/config/opendatahub-io/models-as-a-service).

The benchmark is an A/B test: the same GuideLLM load is driven through the
Kuadrant-based AI gateway (`gateway`) and directly at the model provider
(`baseline`), so the delta measures gateway overhead. Each CI job sweeps that
A/B across payload sizes, model providers and client concurrency levels.

## File layout

| File | Role |
| --- | --- |
| `examples/config/maas-gateway-perf-config.yaml` | Shared metadata (cluster shape, benchmark name, `jobType`/`pullNumber` plumbing). Pulled in via `parentConfig:`. |
| `examples/metrics/maas-gateway-perf-metrics.yaml` | Shared metric definitions. Pulled in via `metricsFile:`. |
| `examples/maas-gateway-perf-odh-anthropic.yaml` | Per-job config |
| `examples/maas-gateway-perf-odh-vertex.yaml` | Per-job config |
| `examples/maas-gateway-perf-odh-nil-small.yaml` | Per-job config |
| `examples/maas-gateway-perf-odh-nil-bulk.yaml` | Per-job config |

The per-job configs are deliberately tiny — everything except the job's own
identity is inherited. See
[Configuration Inheritance](configuration.md#configuration-inheritance) for how
`parentConfig` and `metricsFile` work in general.

## The four periodics

Each Orion config corresponds to one `periodic-ci-opendatahub-io-models-as-a-service-main-<name>-<name>` job.

| Config | `PROVIDERS` | `PAYLOAD_SIZES` | `CONCURRENCY_LEVELS` (job) | Tracked by Orion |
| --- | --- | --- | --- | --- |
| `maas-gateway-perf-odh-anthropic` | `claude-sonnet-anthropic` | small, medium, large, very-large | 2…1024 (10 levels) | 8, 64, 512 |
| `maas-gateway-perf-odh-vertex` | `claude-sonnet-vertex` | small, medium, large, very-large | 2…1024 (10 levels) | 8, 64, 512 |
| `maas-gateway-perf-odh-nil-small` | `gpt-4o-openai`, `gpt-4o-azure`, `gpt-4o-bedrock` | small | 2…1024 (10 levels) | 8, 64, 512 |
| `maas-gateway-perf-odh-nil-bulk` | `gpt-4o-openai`, `gpt-4o-azure`, `gpt-4o-bedrock` | medium, large, very-large | 8, 64, 512 | 8, 64, 512 (whole sweep) |

## Job naming and templating

kube-burner names each benchmark iteration:

```
<mode>-<payload size>-<provider>-c<concurrency>
```

for example `gateway-small-gpt-4o-openai-c8` and its
`baseline-small-gpt-4o-openai-c8` counterpart.

`metrics/maas-gateway-perf-metrics.yaml` rebuilds that list as the cross
product of four input variables, then uses it as the `fan_out` domain for every
metric:

| Input variable | Default | Source |
| --- | --- | --- |
| `gateway_modes` | `gateway,baseline` | `GATEWAY_MODES` — both halves of the A/B |
| `payload_sizes` | `small` | `PAYLOAD_SIZES` — same value the workload ran with |
| `providers` | `gpt-4o-openai` | `PROVIDERS` — same value the workload ran with |
| `orion_concurrency_levels` | `8,64,512` | `ORION_CONCURRENCY_LEVELS` — curated subset of `CONCURRENCY_LEVELS` |

Orion lowercases the process environment into template variables, so in CI
these come straight from the job's own environment rather than being hardcoded
per config. That is what stops a config from drifting away from what its job
actually runs — if the job's `PROVIDERS` changes and the config is not updated,
the query returns nothing rather than silently tracking the wrong series.

Jinja control statements in the metrics file are written behind a `#` so the
raw template still parses as YAML for `make lint`; they render down to empty
comment lines.

### Why `ORION_CONCURRENCY_LEVELS` is a subset

The container metrics fan out over every job name and then `group_by` every
container. Tracking all ten levels of a ten-level sweep would produce many
thousands of series per run, so Orion deliberately watches a low/mid/high
sample (8, 64, 512) of what the workload sweeps. Override it per job when a
different slice matters.

## Isolating one job's runs

All four periodics run on the same cluster shape and publish under the same
`benchmark.keyword`, so the inherited metadata alone matches **all** of them.
The per-metric `jobName` filters blank out the *columns* belonging to other
jobs, but they do not keep those runs out of the result set — foreign UUIDs
still show up as rows. Each per-job config therefore also pins `upstreamJob`:

```yaml
tests:
  - name: maas-perf-odh-anthropic
    metadata:
      wildcard:
        ocpVersion: "{{ version }}*"
        upstreamJob.keyword: "*maas-perf-odh-anthropic*"
```

Two things about that block are easy to get wrong:

- **The leading `*` is deliberate.** It also matches `rehearse-NNNNN-` prefixed
  runs, so a PR or rehearsal still contributes its own datapoint. Orion warns
  about leading wildcards on `.keyword` fields because they cannot use the
  index; here the cost is accepted in exchange for rehearsal coverage.
- **`ocpVersion` has to be restated.** Config merging is shallow, so a child
  that defines `wildcard` replaces the parent's `wildcard` block wholesale. Drop
  the `ocpVersion` line and the query silently widens to every OCP version.

## Metrics

All metrics fan out over the job-name matrix described above. Metrics sourced
from kube-burner key off `jobName`; metrics sourced from GuideLLM key off
`job_name.keyword`.

| Metric | Aggregation | Direction | Threshold |
| --- | --- | --- | --- |
| `${comp}Container{CPU,Memory}` for `maas`, `kuadrant`, `testInfra`, `maasAPI`, grouped by container | avg | 1 (lower is better) | 10% |
| `maasNetwork{Receive,Transmit}Rate` | avg | 0 (flag both ways) | 10% |
| `gatewayRequestDuration{P50,P95,P99}` | avg | 1 | 10% |
| `gatewayRequestRate` | avg | 0 | 10% |
| `gatewayRequestCount` | max | 0 | 10% |
| `limitadorAuthorizedCalls` | avg | 0 | 10% |
| `limitadorAuthorizedHitsRate` | avg | 1 | 10% |
| GuideLLM `ttft`, `itl`, `tpot`, `request-latency` at mean/p90/p95/p99 | avg | 1 | 10% |
| GuideLLM `output-tps`, `throughput` at mean/p90/p95/p99 | avg | -1 (higher is better) | 10% |
| GuideLLM `errored-requests` | sum | 1 | 0% |

`errored-requests` uses a threshold of `0` on purpose: any increase in errored
requests is worth flagging. It is stated explicitly rather than left to the
inherited default so that it reads as a decision.

See [Direction](configuration.md#direction) and
[Threshold](configuration.md#threshold) for the general semantics.

## Running locally

Pass the same providers and payload sizes the target job uses, or the query
will not match anything:

```bash
orion --config examples/maas-gateway-perf-odh-anthropic.yaml --hunter-analyze \
  --input-vars='{"version":"4.21","providers":"claude-sonnet-anthropic","payload_sizes":"small,medium,large,very-large"}'

orion --config examples/maas-gateway-perf-odh-vertex.yaml --hunter-analyze \
  --input-vars='{"version":"4.21","providers":"claude-sonnet-vertex","payload_sizes":"small,medium,large,very-large"}'

orion --config examples/maas-gateway-perf-odh-nil-small.yaml --hunter-analyze \
  --input-vars='{"version":"4.21","providers":"gpt-4o-openai,gpt-4o-azure,gpt-4o-bedrock","payload_sizes":"small"}'

orion --config examples/maas-gateway-perf-odh-nil-bulk.yaml --hunter-analyze \
  --input-vars='{"version":"4.21","providers":"gpt-4o-openai,gpt-4o-azure,gpt-4o-bedrock","payload_sizes":"medium,large,very-large"}'
```

Add `--input-vars='{"orion_concurrency_levels":"8,512"}'` to narrow the tracked
concurrency slice.

## Adding a new MaaS job

1. Add the periodic in `openshift/release` and set `ORION_CONFIG` to the new
   config path.
2. Create `examples/maas-gateway-perf-odh-<name>.yaml` with `parentConfig`,
   `metricsFile`, and a `wildcard` block containing both `ocpVersion` and an
   `upstreamJob.keyword` pin for the new job.
3. Add a matching case to `test.bats` so a drift between the config and the
   job's environment shows up as an empty result set.
4. Add a row to the periodics table above.
