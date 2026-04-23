# Configuration Guide

## Configuration File Format

Orion uses YAML configuration files to define tests, metadata, and metrics. Here's the basic structure:

```yaml
tests:
  - name: test-name
    metadata:
      # metadata filters
    metrics:
      # metric definitions
```

## Configuration Inheritance

Orion supports configuration inheritance to reduce duplication and improve maintainability. You can inherit metadata from a parent configuration file and load metrics from an separate file.

### Parent Configuration (`parentConfig`)

The `parentConfig` field allows you to inherit metadata from a parent configuration file. This is useful when multiple test configurations share common metadata settings.

**How it works:**
- The parent configuration file should contain a `metadata` section
- Metadata from the parent is merged into each test's metadata
- **Child configuration takes precedence** - if a key exists in both parent and child, the child value is used
- Paths can be relative (to the config file directory) or absolute

**Example:**

`parent.yaml`:
```yaml
metadata:
  platform: AWS
  clusterType: self-managed
  masterNodesType: m6a.xlarge
  masterNodesCount: 3
  workerNodesType: m6a.xlarge
  workerNodesCount: 6
  benchmark.keyword: node-density
```

`child.yaml`:
```yaml
parentConfig: parent.yaml
tests:
  - name: payload-node-density
    metadata:
      ocpVersion: "4.17"
      networkType: OVNKubernetes
      # Inherits all metadata from parent.yaml
      # Can override parent values if needed
    metrics:
      # metric definitions
```

### Separate Metrics File (`metricsFile`)

The `metricsFile` field allows you to load metrics from an separate file. This is useful for sharing common metrics across multiple test configurations.

**How it works:**
- The metrics file should contain a list of metric definitions
- Metrics from the separate file are merged with metrics defined in the test
- **Test-level metrics take precedence** - if a metric with the same `name` and `metricName` exists in both, the test-level metric is used
- Paths can be relative (to the config file directory) or absolute
- Metrics are merged: inherited metrics that don't conflict are included, then test-level metrics are added

**Example:**

`metrics.yaml`:
```yaml
- name: podReadyLatency
  metricName: podLatencyQuantilesMeasurement
  quantileName: Ready
  metric_of_interest: P99
  labels:
    - "[Jira: PerfScale]"
  direction: 1
  threshold: 10

- name: apiserverCPU
  metricName: containerCPU
  labels.namespace.keyword: openshift-kube-apiserver
  metric_of_interest: value
  agg:
    value: cpu
    agg_type: avg
  labels:
    - "[Jira: kube-apiserver]"
  direction: 1
  threshold: 10
```

`config.yaml`:
```yaml
metricsFile: metrics.yaml
tests:
  - name: my-test
    metadata:
      # metadata filters
    metrics:
      # Additional metrics specific to this test
      # Metrics from metrics.yaml are automatically included
      - name: customMetric
        # ... metric definition
```

### Combined Usage

You can use both `parentConfig` and `metricsFile` together:

```yaml
parentConfig: parent.yaml
metricsFile: metrics.yaml
tests:
  - name: payload-node-density
    metadata:
      ocpVersion: "4.17"
      # Inherits metadata from parent.yaml
    metrics:
      # Inherits metrics from metrics.yaml
      # Can add test-specific metrics here
```

### Local Overrides (`local_config` and `local_metrics`)

For individual tests, you can override the global parent and metrics by loading metadata or metrics from a **local** file instead of the config-level `parentConfig` or `metricsFile`.

**`local_config`** (test-level):

- Path to a YAML file that contains a `metadata` section.
- That file’s metadata is merged into the test’s metadata; **test-level metadata takes precedence** over the local file.
- Paths can be relative (to the config file directory) or absolute.

**`local_metrics`** (test-level):

- Path to a YAML file containing a **list** of metric definitions (same format as `metricsFile`).
- Those metrics are merged with the test’s own `metrics`; **test-level metrics take precedence** when names match (same `name` and `metricName`).
- Paths can be relative (to the config file directory) or absolute.

**Example with local overrides:**

`local_config.yaml`:
```yaml
metadata:
  platform: GCP
  clusterType: managed
```

`local_metrics.yaml`:
```yaml
- name: customMetric
  metricName: myMeasurement
  metric_of_interest: value
  threshold: 5
```

```yaml
parentConfig: parent.yaml
metricsFile: metrics.yaml
tests:
  - name: my-test
    local_config: local_config.yaml
    local_metrics: local_metrics.yaml
    metadata:
      ocpVersion: "4.17"   # Overrides or adds to local_config metadata
    metrics:
      - name: testSpecificMetric
        # ... only this test gets this metric; global metrics are not used
```

### Ignoring Global Inheritance (`IgnoreGlobal` and `IgnoreGlobalMetrics`)

You can disable inheritance from the config-level `parentConfig` or `metricsFile` for specific tests without using local files.

**`IgnoreGlobal`** (test-level, boolean):

- When `true`, this test **does not** inherit metadata from `parentConfig`.
- The test uses only its own `metadata` (and, if set, metadata from `local_config`).
- Use when a test needs completely different metadata and you do not want to use a local config file.

**`IgnoreGlobalMetrics`** (test-level, boolean):

- When `true`, this test **does not** inherit metrics from `metricsFile`.
- The test uses only its own `metrics` (and, if set, metrics from `local_metrics`).
- Use when a test needs a different set of metrics and you do not want to use a local metrics file.

**Example:**

```yaml
parentConfig: parent.yaml
metricsFile: metrics.yaml
tests:
  - name: olm-integration-test
    IgnoreGlobal: true
    IgnoreGlobalMetrics: true
    metadata:
      jobType: periodic
      not:
        stream: okd
    metrics:
      - name: catalogdCPU
        metricName: catalogd_cpu_usage_cores
        metric_of_interest: value
        threshold: 1
```

In this example, the test uses only the metadata and metrics defined in the test block; nothing is merged from `parent.yaml` or `metrics.yaml`.

## Complete Example

```yaml
tests:
  - name: payload-cluster-density-v2
    metadata:
      platform: AWS
      clusterType: self-managed
      masterNodesType: m6a.xlarge
      masterNodesCount: 3
      workerNodesType: m6a.xlarge
      workerNodesCount: 6
      benchmark.keyword: cluster-density-v2
      ocpVersion: 4.17
      networkType: OVNKubernetes

    metrics:
      - name: podReadyLatency
        metricName.keyword: podLatencyQuantilesMeasurement
        quantileName: Ready
        metric_of_interest: P99
        not:
          jobConfig.name: "garbage-collection"
        labels:
          - "[Jira: PerfScale]"
        direction: 0
        threshold: 10
        correlation: ovnCPU_avg
        context: 5

      - name: apiserverCPU
        metricName.keyword: containerCPU
        labels.namespace.keyword: openshift-kube-apiserver
        metric_of_interest: value
        agg:
          value: cpu
          agg_type: avg
        labels:
          - "[Jira: kube-apiserver]"
        direction: 0
        threshold: 10
```

## Metrics Options

### Custom Timestamp
The `timestamp` field allows users to set custom timestamp fields for both metadata and actual data:

- Can be set at **Test level** (applies to all metrics)
- Can be set at **Metric level** (applies only to that metric)
- Metric level takes precedence over test level
- Defaults to `timestamp` if not set
- Recommended type is int,str in seconds

### UUID
UUID field ensures that a set of test results from the same job are grouped together.

- `uuid` should be a top level key in your json payload
- Should be of type text with sub-field keyword in es index.

### Direction
Controls which types of changes to detect:

- `direction: 1` - Show only positive changes (increases)
- `direction: 0` - Show both positive and negative changes (default)
- `direction: -1` - Show only negative changes (decreases)

### Threshold
An absolute percentage value that filters changepoints:

- Can be set at **Test level** (applies to all metrics)
- Can be set at **Metric level** (applies only to that metric)
- Metric level takes precedence over test level
- Defaults to `0` (any change will be reported) if not set
- Only changepoints greater than this percentage will be detected

Example:
```yaml
threshold: 10  # Only detect changes > 10%
```

### Correlation
A filter that skips changepoint detection if a dependent metric has no changepoint:

```yaml
correlation: <metric_name>
```

**Building Correlation Names:**
- Use the `name` field of the metric
- Add an underscore `_`
- Add the `metric_of_interest` field OR the aggregation operation (`avg`, `sum`, `max`)

**Examples:**
- `podReadyLatency_P99`
- `ovnCPU_avg`
- `kubelet_avg`

**Important Notes:**
- Correlation is applied in order - set dependent metrics before their depending metrics
- Each correlation metric can only be in one correlation relation
- Config validation will fail if metrics appear in more than one relation
- This feature hides changepoint detections based on metric relationships - analyze results carefully

### Context
Works complementary to `correlation` by analyzing runs before and after the current changepoint:

```yaml
context: 5  # Analyze 5 runs before and after (default)
```

## Aggregation Metrics

Orion supports aggregating metric values across multiple data points per test run. This is useful for computing statistics like average CPU usage, total memory consumed, or latency percentiles.

### Supported Aggregation Types

- `avg` - Average (arithmetic mean)
- `sum` - Sum of all values
- `max` - Maximum value
- `min` - Minimum value
- `count` - Count of values (number of data points)
- `percentiles` - Calculate percentile distributions (e.g., P50, P95, P99)

### Standard Aggregation Examples

**Average (avg):**

```yaml
- name: apiserverCPU
  metricName.keyword: containerCPU
  labels.namespace.keyword: openshift-kube-apiserver
  metric_of_interest: value
  agg:
    value: cpu
    agg_type: avg  # Calculate average CPU usage
  threshold: 10
  direction: 1
```

**Count:**

```yaml
- name: api_request_count
  metricName: api_requests
  metric_of_interest: request_id
  agg:
    value: request_id
    agg_type: count  # Count number of requests
  threshold: 10
  direction: 1
```

The `count` aggregation counts the number of values in the specified field, useful for tracking volume metrics like number of requests, events, or samples.

**Other standard aggregations** (`sum`, `max`, `min`) follow the same pattern - just change `agg_type` to the desired aggregation.

### Percentile Aggregations

Percentile aggregations are particularly useful for analyzing latency distributions, response times, and other performance metrics where you need to understand the distribution of values rather than just the average.

**Basic percentile example (uses defaults):**

```yaml
- name: api_latency_p95
  metricName: api_response_time
  metric_of_interest: latency_ms
  agg:
    value: latency_ms
    agg_type: percentiles
  # Calculates P50, P95, P99 by default
  # Reports P95 by default
  threshold: 15
  direction: 1
```

**Advanced percentile example with custom configuration:**

```yaml
- name: api_latency_p99
  metricName: api_response_time
  metric_of_interest: latency_ms
  agg:
    value: latency_ms
    agg_type: percentiles
    percents: [50, 90, 95, 99, 99.9]  # Which percentiles to calculate
    target_percentile: 99              # Which percentile to report for regression detection
  threshold: 20
  direction: 1
```

**Percentile Configuration Options:**

- `percents` (optional): List of percentile values to calculate. Default: `[50, 95, 99]`
  - Can specify any percentile between 0 and 100
  - Examples: `[50, 95, 99]`, `[90, 95, 99, 99.9]`, `[25, 50, 75]`

- `target_percentile` (optional): Which percentile value to use for regression detection. Default: `95`
  - Must be one of the values in the `percents` list
  - This is the value that will be analyzed for changepoints
  - Other percentiles are calculated but not used for detection

**Complete percentile example:**

```yaml
- name: pod_ready_latency_p99
  metricName: podLatencyMeasurement
  quantileName: Ready
  metric_of_interest: latency_seconds
  agg:
    value: latency_seconds
    agg_type: percentiles
    percents: [50, 95, 99]
    target_percentile: 99
  labels:
    - "[Jira: PerfScale]"
  threshold: 15
  direction: 1
  correlation: cluster_cpu_avg
```

### Aggregation Field Naming

When using aggregations, the resulting metric name follows this pattern:
- Standard aggregations: `<name>_<agg_type>`
  - Examples: `apiserverCPU_avg`, `memory_sum`, `latency_max`, `requests_count`
- Percentiles: `<name>_percentiles`
  - Example: `api_latency_percentiles`

These names are used in:
- Output files and reports
- Correlation references
- JUnit test names

## Labels and Filtering

### Labels
Add JIRA or component team labels for tracking:

```yaml
labels:
  - "[Jira: PerfScale]"
  - "[Jira: kube-apiserver]"
```

### Filtering with `not`
Exclude specific data from metrics:

```yaml
not:
  jobConfig.name: "garbage-collection"
```

To exclude multiple values, use a list:

```yaml
not:
  service_mesh_mode:
    - "ambient"
    - "sidecar"
```

## Test-Level Settings

Settings that can be applied at the test level and inherited by all metrics:

```yaml
tests:
  - name: my-test
    threshold: 15        # Default threshold for all metrics
    timestamp: "@timestamp"  # Custom timestamp field
    # ... other settings
```

## Report output options

These command-line options control how the text report is formatted.

### `--column-group-size`

Number of metrics per column group in the plain-text report. When many metrics are present, the report splits them into multiple tables; each table shows the same time and attribute columns plus a subset of metrics.

- **Default:** `5`
- **Example:** `--column-group-size 6` to show 6 metrics per table

## Validation

Orion validates configuration files and will report errors for:
- Invalid correlation relationships
- Missing required fields
- Conflicting settings
- Malformed YAML syntax

Use the `--debug` flag to get detailed validation information.

## JIRA Integration for Regression Tracking

Orion supports tracking performance regressions as JIRA issues instead of (or in addition to) flat YAML files. This enables teams to manage regressions using their existing issue tracking workflows.

### ACK Provider Overview

ACK (Acknowledgment) providers allow Orion to query for known regressions before reporting new ones. Orion supports two types of providers:

- **File-based provider**: Reads acknowledgments from YAML files (default behavior)
- **JIRA provider**: Queries acknowledgments from JIRA issues (new in this release)

You can use both providers simultaneously in "hybrid mode" to transition from file-based to JIRA-based tracking.

### Basic JIRA Usage

**Query existing JIRA acknowledgments:**

```bash
orion --config config.yaml --jira-ack \
  --jira-url https://issues.example.com \
  --jira-project PERFSCALE \
  --jira-component CPT_ISSUES
```

**Auto-create JIRA issues for new regressions:**

```bash
orion --config config.yaml --jira-ack --jira-auto-create \
  --jira-url https://issues.example.com \
  --jira-project PERFSCALE \
  --jira-component CPT_ISSUES
```

### Authentication

JIRA authentication requires environment variables based on your JIRA deployment type:

**On-premise JIRA (Personal Access Token):**

```bash
export JIRA_TOKEN="your_personal_access_token"
```

**Atlassian Cloud (Email + API Token):**

```bash
export JIRA_EMAIL="your@email.com"
export JIRA_TOKEN="your_api_token"
```

### JIRA Configuration Options

#### Command-line Options

| Option | Description | Default |
|--------|-------------|---------|
| `--jira-ack` | Enable JIRA ACK provider | `false` |
| `--jira-auto-create` | Auto-create JIRA issues for new regressions | `false` |
| `--jira-url` | JIRA instance URL (e.g., `https://issues.redhat.com`) | Required |
| `--jira-project` | JIRA project key | `PERFSCALE` |
| `--jira-component` | JIRA component name | `CPT_ISSUES` |

#### Configuration File Options

You can also configure JIRA settings in your YAML configuration file:

```yaml
jira_url: https://issues.example.com
jira_project: PERFSCALE
jira_component: CPT_ISSUES
jira_uuid_field: description      # Field to store UUID (default)
jira_metric_field: labels          # Field to store metric name (default)
```

### Auto-created Issue Content

When `--jira-auto-create` is enabled, Orion creates rich JIRA issues that include:

- **Summary**: `Regression in <metric> (<version>)`
- **Description** (JIRA markup format):
  - Test name and UUID
  - Version change (e.g., `4.21 → 4.22`)
  - Build URL and timestamp
  - Percentage change for primary metric
  - Table of all affected metrics
  - Related pull requests between versions
  - GitHub context (commits and releases)
- **Labels**: Version, test type, and metric name
- **Component**: Specified via `--jira-component`
- **Issue Type**: Bug

### JIRA-only Mode

Skip file-based ACKs entirely:

```bash
# Use JIRA exclusively (no file ACK auto-detection)
orion --config config.yaml --jira-ack
```

Without `--ack`, Orion won't auto-detect or load file-based acknowledgments.

### Troubleshooting

**Debug mode:**

```bash
orion --config config.yaml --jira-ack --debug
```

This will show:
- JIRA connection status
- JQL queries being executed
- Issue parsing details
- Permission check results 
