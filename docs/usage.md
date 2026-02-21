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
- Use with `direction: 0` in config when using `-o json` to see percent differences

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
        jobConfig.name: "garbage-collection"
      labels:
        - "[Jira: PodLatency]"
      threshold: 10
```

The variable `version` can be passed through the `--input-vars` flag as follows:

```shell
$ orion --config /path/to/config.yaml --input-vars='{"version": "4.20"}' --hunter-analyze
# Or using env vars
$ VERSION=4.20 orion --config /path/to/config.yaml --hunter-analyze
```

> **info**
>> Variables pased from the `--input-vars` take precedence over environment variables
>> Environment variable name are lowercased

### Output Options
Control where and how results are saved:

```bash
# Custom output file location
orion --output /path/to/results.csv --hunter-analyze

# JSON output format
orion cmd o json --hunter-analyze

# JUnit XML format
orion cmd o junit --hunter-analyze

# Collapse output (show only changepoints and surrounding data)
orion --collapse --hunter-analyze
```

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

Orion automatically loads `ack/all_ack.yaml` when present (filtered by version and test type from your config). Use `--ack` to add extra acknowledgment files; they are merged with the auto-loaded file. To disable only automatic ACK loading (manual `--ack` files are still loaded):

```bash
orion --no-ack --hunter-analyze
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
      ocpVersion: 4.17
    metrics:
      - name: apiserverCPU
        metricName.keyword: containerCPU
        labels.namespace.keyword: openshift-kube-apiserver
        metric_of_interest: value
        agg:
          value: cpu
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
      ocpVersion: 4.17
    metrics:
      # Base metric - must come first
      - name: ovnCPU
        metricName.keyword: containerCPU
        labels.namespace.keyword: openshift-ovn-kubernetes
        metric_of_interest: value
        agg:
          value: cpu
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
      ocpVersion: 4.17
    metrics:
      - name: apiserverCPU
        metricName.keyword: containerCPU
        labels.namespace.keyword: openshift-kube-apiserver
        metric_of_interest: value
        agg:
          value: cpu
          agg_type: avg
        labels:
          - "[Jira: kube-apiserver]"

      - name: etcdCPU
        metricName.keyword: containerCPU
        labels.namespace.keyword: openshift-etcd
        metric_of_interest: value
        agg:
          value: cpu
          agg_type: avg
        labels:
          - "[Jira: etcd]"

      - name: etcdDisk
        metricName.keyword: 99thEtcdDiskBackendCommitDurationSeconds
        metric_of_interest: value
        agg:
          value: duration
          agg_type: avg
        labels:
          - "[Jira: etcd]"

      - name: kubeletCPU
        metricName.keyword: kubeletCPU
        metric_of_interest: value
        agg:
          value: cpu
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
# Generate JSON output with only changepoints
orion --config performance-config.yaml --hunter-analyze -o json --collapse

# Generate JUnit XML for CI integration
orion --config performance-config.yaml --hunter-analyze -o junit --output results.xml
```

### Performance Analysis with Custom Thresholds
```bash
orion \
  --config perf-config.yaml \
  --hunter-analyze \
  --lookback 7d \
  --threshold 15 \
  --output results.csv \
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
  --output anomalies.json
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
When executing Orion with the flag `--pr-analysis` a pull request analysis will executed and the output for it will contain three sections

1. An analysis section of all payload results (No PR data)
2. A section with the AVG of all payload results
3. An analysis section from all PR runs

Having the AVG section will provide an easy way to compare the PR results to the payload results, allow to locate any issues.

| The only section that can trigger a failure in the job is the one in section one, the payload data, and it is not related to the changes in the PR.

### Necessary fields

To achieve this the following input_vars should be provided

- "jobtype"
- "pull_number"
- "organization"
- "repository"

### Input Example

`--input-vars='{"jobtype": "pull","pull_number": "2790", "organization": "openshift", "repository": "test"}'`

### Example
```
payload-cluster-density-v2
==========================
time                       uuid                                  ocpVersion                          buildUrl          podReadyLatency_P99    apiserverCPU_avg    multusCPU_avg    monitoringCPU_avg    ovnCPU_avg    etcdCPU_avg    kubelet_avg    ovsCPU-irate-all_avg    ovsMemory-Workers_max    ovsMemory-Masters_max    ovsMemory-all_avg
-------------------------  ------------------------------------  ----------------------------------  --------------  ---------------------  ------------------  ---------------  -------------------  ------------  -------------  -------------  ----------------------  -----------------------  -----------------------  -------------------
2025-10-12 19:39:00 +0000  ce6bd7dd-568e-4df2-9ac1-659206440a76  4.21.0-0.nightly-2025-10-12-174700  https://pro456                  15000             4.59079         0.135002             0.922528       1.45358        3.33058        22.4811                0.16045               4.73473e+08              1.69095e+08          6.39637e+07
2025-10-13 03:07:04 +0000  b6bea795-9a66-4f1a-85bb-c6386c49b28c  4.21.0-0.nightly-2025-10-13-011858  https://pro536                  15000             4.8343          0.130706             1.04589        1.54966        3.46015        22.9901                0.158266              4.71241e+08              1.62673e+08          6.28333e+07

payload-cluster-density-v2 | Average of above Periodic runs
===========================================================
time                       uuid                                  ocpVersion                          buildUrl          podReadyLatency_P99    apiserverCPU_avg    multusCPU_avg    monitoringCPU_avg    ovnCPU_avg    etcdCPU_avg    kubelet_avg    ovsCPU-irate-all_avg    ovsMemory-Workers_max    ovsMemory-Masters_max    ovsMemory-all_avg
-------------------------  ------------------------------------  ----------------------------------  --------------  ---------------------  ------------------  ---------------  -------------------  ------------  -------------  -------------  ----------------------  -----------------------  -----------------------  -------------------
0000-00-00 00:00:00 +0000  xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx  xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx  xxxxxxxxxxxxxx            14991.22807              4.7760         0.129298              1.02638       1.48013        3.46592        22.6555                0.154375              4.70554e+08              1.66524e+08          6.32719e+07

payload-cluster-density-v2 | Pull Request #2394
===============================================
time                       uuid                                  ocpVersion                                                buildUrl            podReadyLatency_P99    apiserverCPU_avg    multusCPU_avg    monitoringCPU_avg    ovnCPU_avg    etcdCPU_avg    kubelet_avg    ovsCPU-irate-all_avg    ovsMemory-Workers_max    ovsMemory-Masters_max    ovsMemory-all_avg
-------------------------  ------------------------------------  --------------------------------------------------------  ----------------  ---------------------  ------------------  ---------------  -------------------  ------------  -------------  -------------  ----------------------  -----------------------  -----------------------  -------------------
2025-09-24 12:44:42 +0000  ce18087e-3cc2-4bb7-869c-9cb5e779d6c2  4.21.0-0.ci-2025-09-24-105904-test-ci-op-ylr50c4n-latest  https://prow1744                  15000             4.84306         0.13679               0.91342       1.39937        3.39843        21.6341              nan                     4.70409e+08              1.68456e+08        nan
2025-10-10 15:41:01 +0000  05a5c8d0-7977-4320-b24e-fd755a8ce6b4  4.21.0-0.ci-2025-10-10-134628-test-ci-op-0hx9q2xv-latest  https://prow8256                  15000             4.73279         0.132954              0.93639       1.42667        3.46745        21.5639                0.150409              4.64753e+08              1.70643e+08          6.32196e+07
```

## Tips and Best Practices

1. **Use `--debug`** when troubleshooting configuration issues
2. **Start with small lookback periods** when testing new configurations
3. **Use `--collapse`** to focus on changepoints in large datasets
4. **Combine `--uuid` and `--baseline`** for targeted comparisons
5. **Acknowledge known issues** to reduce noise in results
6. **Use appropriate algorithms** for your use case:
   - Hunter: General changepoint detection
   - CMR: Recent vs historical comparison
   - Anomaly: Outlier detection, does not support NaN in their values, all rows with NaN in any column is dropped to secure proper algorithm execution
