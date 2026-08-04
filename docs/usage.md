# Usage Guide

## ElasticSearch configuration

Orion uses ElasticSearch/OpenSearch (ES/OS) to fetch the data used for comparisons. It can be configured using the following flags or environment variables:

- `--es-server`: Sets the URL of ES/OS; or using the `ES_SERVER` environment variable
- `--metadata-index`: Index name of the ES/OS used to fetch metadata; or using `es_metadata_index` environment variable
- `--benchmark-index`: Index name of the ES/OS used to fetch benchmark data; or using `es_benchmark_index` environment variable

### Basic Usage

```bash
orion --hunter-analyze
```

### Version Information

Display the current version of Orion:

```bash
orion --version
```

This command outputs the version number, which is dynamically determined from git tags using setuptools_scm. The version format follows semantic versioning and may include additional metadata such as:
- `.post1.dev` suffix when the current commit is ahead of the latest tag
- `+dirty` suffix when there are uncommitted changes in the working directory

## Running with uvx

```bash
uvx --from git+https://github.com/cloud-bulldozer/orion.git -p 3.11 orion --hunter-analyze
```

## Core Algorithms

Orion supports three main algorithms that are **mutually exclusive**:

### Hunter Analysis
Uses statistical changepoint detection:
```bash
orion --hunter-analyze
```

### CMR (Compare Most Recent)
Compares the most recent run with previous matching runs:

```bash
orion --cmr
```

- If more than 1 previous run is found, values are averaged together
- Use with `direction: 0` in config when using `-o json` to see percent differences for both increases and decreases (default is `direction: 1` which only shows increases)

### Anomaly Detection
Detects anomalies in your data:
```bash
orion --anomaly-detection
```

## Configuration Options

### Config File
Specify a custom configuration file:
```bash
orion --config /path/to/config.yaml --hunter-analyze
```

The configuration file can be a Jinja2 template, environment variables and variables passed through the `--input-vars` flag are accessible in the Jinja2 template: `{{ random_var }}`. For example

Considering the following config file:

```yaml
tests:
  - name: metal-perfscale-cpt-node-density
    metadata:
      platform: BareMetal
      clusterType: self-managed
      masterNodesType.keyword: ""
      masterNodesCount: 3
      workerNodesType.keyword: ""
      workerNodesCount: 4
      benchmark.keyword: node-density
      wildcard:
        ocpVersion: "{{ version }}"
      networkType: OVNKubernetes
      not:
        stream: okd
    metrics:
    - name: podReadyLatency
      metricName.keyword: podLatencyQuantilesMeasurement
      quantileName: Ready
      metric_of_interest: P99
      not:
        jobName.keyword: "garbage-collection"
      labels:
        - "[Jira: PodLatency]"
      threshold: 10
```

The variable `version` can be passed through the `--input-vars` flag as follows:

```shell
$ orion --config /path/to/config.yaml --input-vars='{"version": "4.20*"}' --hunter-analyze
# Or using env vars
$ VERSION="4.20*" orion --config /path/to/config.yaml --hunter-analyze
```

> **info**
>> Variables pased from the `--input-vars` take precedence over environment variables
>> Environment variable name are lowercased

### Output Options
Control where and how results are saved:

```bash
# Custom output file location
orion --save-output-path /path/to/results.txt --hunter-analyze

# JSON output format
orion -o json --hunter-analyze

# JUnit XML format
orion -o junit --hunter-analyze

# Collapse text output (print only regression summary, full table saved to file)
orion --collapse --hunter-analyze

# Collapse JSON output (include only changepoint context rows)
orion --collapse -o json --hunter-analyze
```

### Interactive Visualizations
Generate interactive HTML visualizations alongside the standard Orion output:

```bash
# Generate text output plus an interactive HTML visualization
orion --config performance-config.yaml --hunter-analyze --viz

# Custom output path (HTML filename derives from this)
orion \
  --config performance-config.yaml \
  --hunter-analyze \
  --viz \
  --save-output-path ./outputs/results.txt
```

- `--viz` adds interactive HTML files alongside the standard output
- When used with `--pr-analysis`, separate HTML files are generated for periodic and pull runs
- The generated HTML loads Plotly from a CDN when opened in a browser

### Display Metadata Fields
Add custom metadata fields as columns in the output table:

```bash
# Display a single metadata field
orion --display ocpVirtVersion --hunter-analyze

# Display multiple metadata fields
orion --display ocpVirtVersion,osImage,releaseStream --hunter-analyze
```

**Note:** The `buildUrl` field is optional in the output, but it is always included in the default value of `--display`. This means:
- By default, `buildUrl` is shown as a column in the output
- You can exclude `buildUrl` by explicitly setting `--display` to other fields only
- You can include `buildUrl` along with other fields by adding it to the `--display` list

Examples:
```bash
# Default behavior: buildUrl is included
orion --config config.yaml --hunter-analyze

# Include buildUrl and additional fields
orion --display buildUrl,ocpVirtVersion --hunter-analyze

# Exclude buildUrl, show only ocpVirtVersion
orion --display ocpVirtVersion --hunter-analyze
```

### GitHub Context for Changepoints
Enrich JSON output with release and commit metadata for specific repositories:

```bash
orion \
  --config performance-config.yaml \
  --hunter-analyze \
  --github-repos openshift/origin,openshift/installer \
  -o json
```

- Provide repositories as a comma-separated list (e.g., `--github-repos org1/repo1,org2/repo2`)  
- Each repository reports separate `releases` and `commits` sections. Each section contains an `items` array plus a `count` and optional `reason` when GitHub cannot return data (rate limiting, malformed timestamps, etc.)  
- Orion gathers every release and commit with timestamps strictly after the previous changepoint and up to (and including) the current changepoint—no tags or SHAs are required from the CLI  
- When changepoints are detected, the JSON entries gain a `github_context` block summarizing the interval (`start`, `end`) and the matching release/commit items for every repository  
- Export a `GITHUB_TOKEN` (or `GH_TOKEN`) environment variable to increase GitHub API rate limits

## UUID and Baseline Options

### Specific UUID Analysis
Analyze a specific UUID bypassing metadata matching:
```bash
orion --uuid <uuid> --hunter-analyze
```

### Baseline Comparison
Compare against specific baseline UUIDs:
```bash
orion --uuid <current_uuid> --baseline "<uuid1>,<uuid2>,<uuid3>" --hunter-analyze
```

**Note:** `--baseline` should only be used with `--uuid`

## Time-Based Filtering

### Lookback Period
Constrain your analysis to a specific time period:
```bash
# Look back 5 days and 12 hours
orion --lookback 5d12h --hunter-analyze

# Look back 2 days
orion --lookback 2d --hunter-analyze

# Look back 8 hours
orion --lookback 8h --hunter-analyze
```

### Since Date
Specify an end date to bound the time range when used with `--lookback`:
```bash
# Analyze data from 5 days (2024-01-10) up to 2024-01-15
orion --lookback 5d --since 2024-01-15 --hunter-analyze

# Analyze data ending at 2024-02-01 (no lookback, gets all data before this date)
orion --since 2024-02-01 --hunter-analyze
```

The `--since` flag accepts dates in `YYYY-MM-DD` format and creates an upper bound for your time range:
- When used **with** `--lookback`: Creates a bounded time window between (since - lookback) and since
- When used **without** `--lookback`: Gets all data up to the specified date

**Example Scenarios:**

Today is 27 Aug 2024:
- `--lookback 5d`: Gets runs from 22 Aug onwards (to now)
- `--since 2024-08-25`: Gets all runs up to 25 Aug
- `--lookback 5d --since 2024-08-25`: Gets runs from 20 Aug to 25 Aug (5 day window ending at 25 Aug)
- `--lookback 3d --since 2024-08-25`: Gets runs from 22 Aug to 25 Aug (3 day window ending at 25 Aug)

This is particularly useful for:
- **Historical analysis**: Analyze a specific time period in the past
- **Reproducible reports**: Generate consistent reports for a fixed time range


### Lookback Size
Limit the number of runs to analyze:
```bash
# Analyze last 50 runs
orion --lookback-size 50 --hunter-analyze
```

### Combined Lookback Options
You can combine multiple time-based filtering options. When using multiple options, the more restrictive limit applies:

```bash
# Gets whichever is shorter: last 10 runs OR last 3 days
orion --lookback 3d --lookback-size 10 --hunter-analyze

# Get up to 20 runs from a 7-day window ending at a specific date
orion --lookback 7d --since 2024-08-25 --lookback-size 20 --hunter-analyze
```

**Example Scenario:**
Consider runs on dates: 21 Aug, 22 Aug (3 runs), 23 Aug (2 runs), 24 Aug, 25 Aug, 26 Aug

Today is 27 Aug:
- `--lookback 5d`: Gets runs from 22 Aug onwards (to now)
- `--lookback-size 6`: Gets last 6 runs  
- `--lookback 5d --lookback-size 6`: Gets last 6 runs from 22 Aug onwards
- `--lookback 3d --lookback-size 6`: Gets runs from 24 Aug onwards (3 days wins)
- `--lookback 5d --since 2024-08-25`: Gets runs from 20 Aug to 25 Aug (5-day bounded window)
- `--lookback 5d --since 2024-08-25 --lookback-size 3`: Gets up to 3 runs from 20 Aug to 25 Aug

## Early changepoints

If a changepoint is detected in the first 5 data points, Orion expands the lookback window, re-runs the analysis, and reports based on that expanded result.

## Confidence Indicators

Every detected changepoint is automatically annotated with a statistical confidence indicator that combines two measures:

- **Cohen's d effect size** (primary) — magnitude of the difference relative to data variability. This drives the label classification.
- **Welch's t-test p-value** (descriptive) — probability of observing a difference this extreme if there were no real before/after change. Reported alongside the effect size but does not gate the label.

Cohen's d is used as the primary indicator because the changepoint was already detected by the analysis algorithm — re-testing the same data with a t-test would inflate significance (post-selection bias). The effect size describes *how large* the shift is, independent of the detection method.

These produce a human-readable label shown in the "Affected Metrics" summary table and embedded in JSON output.

### Label Format

Labels are driven by Cohen's d effect size thresholds (Cohen 1988: 0.2 small, 0.5 medium, 0.8 large), with p-value as supplementary context:

| Label | Meaning |
|-------|---------|
| `Large shift (d=1.20, p=0.001)` | d >= 0.8 — strong evidence of a meaningful metric shift |
| `Moderate shift (d=0.60, p=0.03)` | 0.5 <= d < 0.8 — moderate-magnitude shift |
| `Small shift (d=0.30, p=0.02)` | 0.2 <= d < 0.5 — small but detectable effect |
| `Negligible shift (d=0.10, p=0.01)` | d < 0.2 — negligible practical impact |
| `Large shift (d=1.50, p=0.3) — Not statistically significant` | d >= 0.8 but p >= 0.05 — large effect size but insufficient statistical evidence |
| `Degenerate variance — shift detected but effect size undefined` | Both segments have zero variance with different means; Cohen's d is undefined |
| `Insufficient data` | Fewer than 2 data points on either side of the changepoint |
| `Anomaly detection — shift confidence not applicable` | IsolationForest detects outliers, not sustained shifts |

The p-value is formatted with `:.2g` to preserve precision (e.g., `5e-10` instead of `0.00`). When `p >= 0.05`, " — Not statistically significant" is appended to the label.

### Effect Size (Cohen's d)

Cohen's d is computed using a pooled standard deviation, which assumes the before and after segments have roughly similar variance. This is appropriate for CI performance data where the variance structure tends to be stable across a shift. An alternative (Glass's delta, using only the before-segment standard deviation) could be considered if shifts are expected to also change variance.

When both segments have zero variance but different means, Cohen's d is mathematically undefined. In this case, `cohens_d` is reported as `null` with a "Degenerate variance" label.

### How Segments Are Split

The before/after data segments depend on the algorithm:

- **Hunter (E-Divisive)**: segments are bounded by neighboring changepoints. For a changepoint at index *i* with previous changepoint at *p* and next changepoint at *n*, the before-segment is `data[p:i]` and the after-segment is `data[i:n]`. If there is no previous changepoint, `p` defaults to 0 (start of data). If there is no next changepoint, `n` defaults to the end of data. This prevents a later recovery or reversal from masking an earlier genuine shift.
- **CMR**: all previous runs vs. the most recent run (CMR typically produces "Insufficient data" since the after segment has only one point)
- **Anomaly Detection (IsolationForest)**: confidence is not computed. IsolationForest identifies unusual individual observations, not sustained before/after shifts. A separate "Anomaly detection" label is assigned.

### Text Output

The "Affected Metrics" summary table includes a Confidence column:

```text
Affected Metrics
+---------+-------+----------+------------------------------------------+--------+
| Metric  | Value | % Change | Confidence                               | Labels |
+---------+-------+----------+------------------------------------------+--------+
| ovnCPU  | 2.43  | 64.14%   | Large shift (d=1.20, p=0.001)            | [infra] |
| etcdCPU | 3.50  | 1.18%    | Negligible shift (d=0.15, p=0.42)        | [etcd] |
+---------+-------+----------+------------------------------------------+--------+
```

### JSON Output

Each changepoint entry in JSON output includes a `confidence` object (illustrative values):

```json
{
  "is_changepoint": true,
  "metrics": {
    "ovnCPU_avg": {
      "value": 2.43,
      "percentage_change": 64.14,
      "confidence": {
        "p_value": 0.001,
        "cohens_d": 1.2,
        "label": "Large shift (d=1.20, p=0.001)",
        "sufficient_data": true,
        "sample_size_before": 15,
        "sample_size_after": 5,
        "mean_before": 1.48,
        "mean_after": 2.43,
        "std_before": 0.12,
        "std_after": 0.18,
        "ci_95": [0.82, 1.08]
      }
    }
  }
}
```

The `ci_95` field is always present. When confidence cannot be computed, it is `null`:

```json
{
  "confidence": {
    "p_value": null,
    "cohens_d": null,
    "label": "Insufficient data",
    "sufficient_data": false,
    "sample_size_before": 3,
    "sample_size_after": 1,
    "mean_before": 10.5,
    "mean_after": 20.0,
    "std_before": 0.5,
    "std_after": null,
    "ci_95": null
  }
}
```

### Confidence Fields Reference

| Field | Type | Description |
|-------|------|-------------|
| `p_value` | float\|null | Welch's t-test p-value. Lower means more statistically significant. Null when insufficient data or degenerate variance. |
| `cohens_d` | float\|null | Cohen's d effect size (pooled std). Measures the magnitude of the shift relative to data variability. Null when insufficient data, degenerate variance, or IsolationForest. |
| `label` | string | Human-readable confidence label (see Label Format above). |
| `sufficient_data` | bool | Whether both segments had at least 2 data points for statistical computation. |
| `sample_size_before` | int | Number of data points before the changepoint (after NaN removal). |
| `sample_size_after` | int | Number of data points from the changepoint onward (after NaN removal). |
| `mean_before` | float\|null | Mean of the before-segment values. |
| `mean_after` | float\|null | Mean of the after-segment values. |
| `std_before` | float\|null | Sample standard deviation of the before-segment (ddof=1). Null if fewer than 2 points. |
| `std_after` | float\|null | Sample standard deviation of the after-segment (ddof=1). Null if fewer than 2 points. |
| `ci_95` | [float, float]\|null | 95% confidence interval for the mean difference (mean_after − mean_before), computed using the Welch-Satterthwaite degrees of freedom. Null when insufficient data or when standard error is zero. Always present in the output (never omitted). |

The `mean_before`, `mean_after`, `std_before`, and `std_after` fields are the exact values used to compute both `p_value` and `cohens_d`. Combined with the sample sizes, any consumer can independently reproduce the pooled standard deviation, t-statistic, and confidence interval.

The `ci_95` field gives a range for the true shift: e.g., `[12482, 20418]` means "we are 95% confident the true mean difference lies between 12,482 and 20,418." If the interval does not contain zero, the shift is statistically significant at the 5% level — consistent with `p_value < 0.05`.

### Standalone Reports

When generating reports from JSON files with `--report`, confidence data is propagated from the JSON into the summary tables automatically — no additional flags needed.

### Interpreting Results

Use confidence indicators to triage changepoints for evidence of meaningful metric shifts:

1. **Large shift** — investigate immediately; strong evidence of a meaningful metric shift with significant impact
2. **Moderate shift** — investigate; meaningful shift that warrants attention
3. **Small shift** — detectable but small; may be acceptable depending on the metric's sensitivity
4. **Negligible shift** — the detected change is too small to matter in practice
5. **Not statistically significant** — when appended to any label, indicates the p-value is >= 0.05; interpret the effect size with caution
6. **Insufficient data** — not enough data points to compute statistics (common with CMR or very recent runs)
7. **Anomaly detection** — IsolationForest results; the algorithm detects outliers, not sustained shifts

A confidence label indicates evidence of a metric shift, not necessarily that product code caused a regression. Environment changes, workload variations, or measurement differences could also explain the shift — always investigate the cause.

## Node Count Filtering

### Relaxed Matching
Open match requirements to find UUIDs based on metadata without exact jobConfig.jobIterations match:
```bash
orion --node-count true --hunter-analyze
```

Default is `false` for strict matching.

## Debugging and Logging

### Debug Mode
Enable detailed debug logs:
```bash
orion --debug --hunter-analyze
```

## Acknowledging Known Issues

Create an acknowledgment file to mark known regressions:

```yaml
# ack.yaml
---
ack:
  - uuid: "af24e294-93da-4729-a9cc-14acf38454e1"
    metric: "etcdCPU_avg"
    reason: "started thread with etcd team"
```

Apply acknowledgments:
```bash
orion --ack ack.yaml --hunter-analyze
```

Use `--ack` to provide acknowledgment files manually.

For JIRA-based acknowledgments, use `--jira-ack` with an optional status filter:
```bash
# Only treat resolved JIRA tickets as ACKs (statusCategory = "Done")
orion --jira-ack --jira-status-filter Done --hunter-analyze
```

**Benefits:**
- Prevents repeated notifications for known issues
- Tracks why issues are being ignored
- Links to JIRA tickets or Slack threads
- Documents low-impact changes

## Configuration Examples

### Simple CPU Monitoring

```yaml
tests:
  - name: cpu-monitoring
    metadata:
      platform: AWS
      wildcard:
        ocpVersion: "4.17*"
    metrics:
      - name: apiserverCPU
        metricName.keyword: containerCPU
        labels.namespace.keyword: openshift-kube-apiserver
        metric_of_interest: value
        agg:
          agg_type: avg
        direction: 0
        threshold: 15
```

### Pod Latency Monitoring

```yaml
tests:
  - name: pod-latency-check
    metadata:
      platform: AWS
      clusterType: self-managed
      benchmark.keyword: cluster-density-v2
    metrics:
      - name: podReadyLatency
        metricName.keyword: podLatencyQuantilesMeasurement
        quantileName: Ready
        metric_of_interest: P99
        labels:
          - "[Jira: PerfScale]"
        direction: 1  # Only alert on increases
        threshold: 10
```

### Correlated Metrics

```yaml
tests:
  - name: correlated-performance
    metadata:
      platform: AWS
      wildcard:
        ocpVersion: "4.17*"
    metrics:
      # Base metric - must come first
      - name: ovnCPU
        metricName.keyword: containerCPU
        labels.namespace.keyword: openshift-ovn-kubernetes
        metric_of_interest: value
        agg:
          agg_type: avg
        direction: 0
        threshold: 20

      # Correlated metric - only alerts if ovnCPU has changepoint
      - name: podReadyLatency
        metricName.keyword: podLatencyQuantilesMeasurement
        quantileName: Ready
        metric_of_interest: P99
        correlation: ovnCPU_avg  # References the base metric
        context: 10  # Analyze 10 runs before/after
        direction: 0
        threshold: 15
```

### Multi-Component Monitoring

```yaml
tests:
  - name: full-stack-monitoring
    threshold: 10  # Default threshold for all metrics
    metadata:
      platform: AWS
      clusterType: self-managed
      masterNodesCount: 3
      workerNodesCount: 6
      wildcard:
        ocpVersion: "4.17*"
    metrics:
      - name: apiserverCPU
        metricName.keyword: containerCPU
        labels.namespace.keyword: openshift-kube-apiserver
        metric_of_interest: value
        agg:
          agg_type: avg
        labels:
          - "[Jira: kube-apiserver]"

      - name: etcdCPU
        metricName.keyword: containerCPU
        labels.namespace.keyword: openshift-etcd
        metric_of_interest: value
        agg:
          agg_type: avg
        labels:
          - "[Jira: etcd]"

      - name: etcdDisk
        metricName.keyword: 99thEtcdDiskBackendCommitDurationSeconds
        metric_of_interest: value
        agg:
          agg_type: avg
        labels:
          - "[Jira: etcd]"

      - name: kubeletCPU
        metricName.keyword: kubeletCPU
        metric_of_interest: value
        agg:
          agg_type: avg
        labels:
          - "[Jira: Node]"
```

## Command-Line Examples

### Basic Regression Detection
```bash
# Run hunter analysis with default settings
orion --config performance-config.yaml --hunter-analyze

# Run with debug output
orion --config performance-config.yaml --hunter-analyze --debug
```

### Time-Constrained Analysis
```bash
# Analyze last 7 days of data
orion --config performance-config.yaml --hunter-analyze --lookback 7d

# Analyze last 24 hours with maximum 50 runs
orion --config performance-config.yaml --hunter-analyze --lookback 24h --lookback-size 50
```

### Specific UUID Analysis
```bash
# Analyze specific run against historical data
orion --config metrics-only.yaml --uuid "abc123-def456-ghi789" --hunter-analyze

# Compare specific run against baselines
orion --config metrics-only.yaml \
  --uuid "current-run-uuid" \
  --baseline "baseline1,baseline2,baseline3" \
  --cmr
```

### Output Formatting
```bash
# Generate JSON output with only changepoints (saved to file, no stdout)
orion --config performance-config.yaml --hunter-analyze -o json --collapse --save-output-path=./outputs/results.json

# Generate JUnit XML for CI integration (saved to file, no stdout)
orion --config performance-config.yaml --hunter-analyze -o junit --save-output-path=./outputs/results.xml
```

### Performance Analysis with Custom Thresholds
```bash
orion \
  --config perf-config.yaml \
  --hunter-analyze \
  --lookback 7d \
  --threshold 15 \
  --save-output-path results.txt \
  --debug
```

### Baseline Comparison with JSON Output
```bash
orion \
  --uuid "current-run-uuid" \
  --baseline "baseline1,baseline2" \
  --cmr \
  -o json \
  --collapse
```

### Quick Anomaly Check
```bash
orion \
  --config quick-check.yaml \
  --anomaly-detection \
  --lookback 24h \
  --save-output-path anomalies.txt
```

## Acknowledgment Examples

### Basic Acknowledgment File
```yaml
# known-issues.yaml
---
ack:
  - uuid: "abc123-def456-ghi789"
    metric: "etcdCPU_avg"
    reason: "Known issue tracked in JIRA-12345"
    
  - uuid: "def456-ghi789-abc123"
    metric: "podReadyLatency_P99"
    reason: "Infrastructure change, expected increase"
```

### Using Acknowledgments
```bash
orion --config performance-config.yaml --hunter-analyze --ack known-issues.yaml
```

## Running from a pull request
When executing Orion with the flag `--pr-analysis` a pull request analysis will be executed and the output for it will contain three sections

1. An analysis section of all payload results (No PR data)
2. An analysis section from all PR runs
3. A comparison table summarizing Baseline AVG, changepoint values, and PR results per metric

### Multiple PR comparison

Orion supports analyzing multiple pull requests in a single run. Each PR is analyzed independently against the periodic baseline, and all results appear side-by-side in the comparison table. This is useful for comparing the performance impact of different PRs.

There are three ways to specify multiple PRs (they can be combined — duplicates are automatically removed):

```bash
# Repeatable CLI flag
orion --pr-analysis --pull-number 1234 --pull-number 5678 --config config.yaml --hunter-analyze

# Comma-separated string in --input-vars
orion --pr-analysis --input-vars='{"pull_number": "1234,5678", ...}' --config config.yaml --hunter-analyze

# JSON array in --input-vars
orion --pr-analysis --input-vars='{"pull_numbers": [1234, 5678], ...}' --config config.yaml --hunter-analyze
```

The legacy single `pull_number` in `--input-vars` continues to work for backward compatibility.

> **Note:** Pull number `0` is reserved internally for periodic runs and is always filtered out.

### Comparison table

The comparison table provides a quick way to compare the PR results against the payload baseline and any detected changepoints. The columns are:

- **Metric** — the metric name
- **Baseline AVG** — the average of periodic (payload) runs **before** the first detected changepoint. When no changepoints are detected, it averages all runs. This excludes post-regression data so the baseline is not skewed by regressed values
- **Pre-CP#N** — the metric value from the run **immediately before** the Nth changepoint (shown for every metric, as a baseline reference)
- **CP#N** — the metric value **at** the Nth changepoint, but only for metrics where a regression was detected at that point. Metrics without a changepoint there show `-`
- **PR#number** — the value from the latest run of each PR. When multiple PRs are analyzed, each gets its own column

**How to read CP columns:** Changepoints are numbered in chronological order (`CP#1` is the earliest detected, `CP#2` the next, etc.). Each changepoint represents a moment in the payload history where a statistically significant shift was detected. To spot a regression, compare `Pre-CP#N` (the value just before the shift) with `CP#N` (the value at the shift). If `CP#N` shows `-`, that metric was stable at that point — only metrics that actually changed will have a value.

#### Single PR example

```text
Metric                 Baseline AVG    Pre-CP#1    CP#1    PR#2394
--------------------------  ------  ----------  ------  --------
podReadyLatency_P99          15000       15000   18000     15000
apiserverCPU_avg            4.776       4.834       -    4.7328
ovnCPU_avg                  1.4801      1.5497  2.4297    1.7267
etcdCPU_avg                 3.4659      3.4602      -    3.4675
```

Here `ovnCPU_avg` jumped from `1.5497` (Pre-CP#1) to `2.4297` (CP#1), and the PR value `1.7267` is consistent with the pre-changepoint level — so the PR is addressing this regression.

#### Multiple PR example

```text
Metric                 Baseline AVG    Pre-CP#1    CP#1    PR#2394    PR#2387
--------------------------  ------  ----------  ------  --------  --------
podReadyLatency_P99          15000       15000   18000     15000     18000
apiserverCPU_avg            4.776       4.834       -    4.7328    4.7328
ovnCPU_avg                  1.4801      1.5497  2.4297    1.7267    2.7267
etcdCPU_avg                 3.4659      3.4602      -    3.4675    3.4675
```

Here you can compare two PRs at a glance: PR#2394 shows `ovnCPU_avg` at `1.7267` (close to the pre-changepoint baseline), while PR#2387 shows `2.7267` (worse than the changepoint) — suggesting PR#2387 may be the culprit.

| The only section that can trigger a failure in the job is the one in section one, the payload data, and it is not related to the changes in the PR.

### Necessary fields

To achieve this the following input_vars should be provided

- "jobtype"
- "organization"
- "repository"

And at least one pull number via `--pull-number` flag or `pull_number`/`pull_numbers` in `--input-vars`.

### Input Examples

Single PR (legacy format):
```bash
orion --pr-analysis --input-vars='{"jobtype": "pull", "pull_number": "2790", "organization": "openshift", "repository": "test"}' --config config.yaml --hunter-analyze
```

Multiple PRs:
```bash
orion --pr-analysis --pull-number 2394 --pull-number 2387 --input-vars='{"jobtype": "pull", "organization": "openshift", "repository": "test"}' --config config.yaml --hunter-analyze
```

Add `--viz` to this workflow to generate interactive HTML visualizations for each analyzed dataset alongside the standard PR report output.

### JSON output format

When using `-o json` with `--pr-analysis`, the output structure is:

```json
{
  "periodic": [ ... ],
  "periodic_avg": { ... },
  "pulls": [
    { "pr": 2394, "data": [ ... ] },
    { "pr": 2387, "data": [ ... ] }
  ]
}
```

Each entry in `pulls` contains the PR number and its full analysis data.

### Example
```
payload-cluster-density-v2
==========================
time                       uuid                                  ocpVersion                          ...
-------------------------  ------------------------------------  ----------------------------------  ---
2025-10-12 19:39:00 +0000  ce6bd7dd-568e-4df2-9ac1-659206440a76  4.21.0-0.nightly-2025-10-12-174700  ...
2025-10-13 03:07:04 +0000  b6bea795-9a66-4f1a-85bb-c6386c49b28c  4.21.0-0.nightly-2025-10-13-011858  ...

payload-cluster-density-v2 | Pull Request #2394
===============================================
time                       uuid                                  ocpVersion                                                ...
-------------------------  ------------------------------------  --------------------------------------------------------  ---
2025-09-24 12:44:42 +0000  ce18087e-3cc2-4bb7-869c-9cb5e779d6c2  4.21.0-0.ci-2025-09-24-105904-test-ci-op-ylr50c4n-latest  ...
2025-10-10 15:41:01 +0000  05a5c8d0-7977-4320-b24e-fd755a8ce6b4  4.21.0-0.ci-2025-10-10-134628-test-ci-op-0hx9q2xv-latest  ...

payload-cluster-density-v2 | Comparison
=======================================
Metric                 Baseline AVG    Pre-CP#1    CP#1    PR#2394
--------------------------  ------  ----------  ------  --------
podReadyLatency_P99          15000       15000   15000     15000
apiserverCPU_avg            4.776       4.834       -    4.7328
multusCPU_avg               0.1293      0.1307      -    0.1330
ovnCPU_avg                  1.4801      1.5497  1.4297    1.4267
etcdCPU_avg                 3.4659      3.4602      -    3.4675
kubelet_avg                 22.656      22.990      -    21.564
```

## Tips and Best Practices

1. **Use `--debug`** when troubleshooting configuration issues
2. **Start with small lookback periods** when testing new configurations
3. **Use `--collapse`** to print only the regression summary to stdout (full table is always saved to file)
4. **Combine `--uuid` and `--baseline`** for targeted comparisons
5. **Acknowledge known issues** to reduce noise in results
6. **Use appropriate algorithms** for your use case:
   - Hunter: General changepoint detection
   - CMR: Recent vs historical comparison
   - Anomaly: Outlier detection, does not support NaN in their values, all rows with NaN in any column is dropped to secure proper algorithm execution
