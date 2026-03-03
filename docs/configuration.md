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

For metrics that require aggregation:

```yaml
- name: apiserverCPU
  metricName.keyword: containerCPU
  labels.namespace.keyword: openshift-kube-apiserver
  metric_of_interest: value
  agg:
    value: cpu
    agg_type: avg  # avg, sum, max, min
```

## Raw Metrics

Raw metrics are used when the benchmark index stores **documents that contain a field with multiple values** (e.g. an array of samples per run). Orion fetches those documents, then applies an aggregation in memory to produce one value per UUID. This fits benchmarks such as **Browbeat/Rally**, where each result document has a `raw` array of measurements.

**How it works:**

- Orion queries the benchmark index with the given `filters` and retrieves the field specified by `metric_of_interest` (e.g. `raw`) for each matching document.
- If that field is an array, aggregation is applied per document (e.g. `avg` over the array).
- The resulting metric name is `{name}_{agg_type}` (e.g. `keystone_v3_list_users_avg`).

**Required fields:**

| Field | Description |
|-------|-------------|
| `type` | Set to `raw` to enable raw-metrics processing. |
| `metric_of_interest` | The document field that holds the value(s) to aggregate (e.g. `raw` for Browbeat/Rally). |
| `agg` | Aggregation to apply. Must include `agg_type`. |

**Optional:**

| Field | Description |
|-------|-------------|
| `filters` | Key-value pairs used to filter which documents are fetched from the benchmark index (e.g. `action.keyword: "keystone_v3.list_users"`). If omitted, no extra filters are applied. |

**Supported `agg_type` values:** `avg`, `sum`, `min`, `max`, `count`, `P99`, `P95`, `P90`.

**Example (Browbeat/Rally-style data with a `raw` array per document):**

```yaml
metrics:
  - name: keystone_v3_list_users
    type: raw
    metric_of_interest: raw
    filters:
      action.keyword: "keystone_v3.list_users"
    threshold: 15
    direction: 1
    agg:
      agg_type: avg

  - name: keystone_v3_list_users
    type: raw
    metric_of_interest: raw
    filters:
      action.keyword: "keystone_v3.list_users"
    agg:
      agg_type: P99
```

This produces metrics such as `keystone_v3_list_users_avg` and `keystone_v3_list_users_P99`. Standard metric options (`threshold`, `direction`, `labels`, etc.) apply to raw metrics as well.

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

## Validation

Orion validates configuration files and will report errors for:
- Invalid correlation relationships
- Missing required fields
- Conflicting settings
- Malformed YAML syntax

Use the `--debug` flag to get detailed validation information. 
