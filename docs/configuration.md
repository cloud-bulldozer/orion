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
        metricName: podLatencyQuantilesMeasurement
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
        metricName: containerCPU
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
  metricName: containerCPU
  labels.namespace.keyword: openshift-kube-apiserver
  metric_of_interest: value
  agg:
    value: cpu
    agg_type: avg  # avg, sum, max, min
```

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
