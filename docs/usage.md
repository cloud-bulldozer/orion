# Usage Guide

## Command-Line Mode

Orion provides a flexible command-line interface with various options for different use cases.

### Basic Usage

```bash
orion cmd --hunter-analyze
```

## Core Algorithms

Orion supports three main algorithms that are **mutually exclusive**:

### Hunter Analysis
Uses statistical changepoint detection:
```bash
orion cmd --hunter-analyze
```

### CMR (Compare Most Recent)
Compares the most recent run with previous matching runs:
```bash
orion cmd --cmr
```
- If more than 1 previous run is found, values are averaged together
- Use with `direction: 0` in config when using `-o json` to see percent differences

### Anomaly Detection
Detects anomalies in your data:
```bash
orion cmd --anomaly-detection
```

## Configuration Options

### Config File
Specify a custom configuration file:
```bash
orion cmd --config /path/to/config.yaml --hunter-analyze
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
      ocpVersion: {{ version }}
      networkType: OVNKubernetes
      not:
        stream: okd
    metrics:
    - name: podReadyLatency
      metricName: podLatencyQuantilesMeasurement
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
$ orion cmd --config /path/to/config.yaml --input-vars='{"version": "4.20"}' --hunter-analyze
# Or using env vars
$ VERSION=4.20 orion cmd --config /path/to/config.yaml --hunter-analyze
```

> **info**
>> Variables pased from the `--input-vars` take precedence over environment variables
>> Environment variable name are lowercased

### Output Options
Control where and how results are saved:

```bash
# Custom output file location
orion cmd --output /path/to/results.csv --hunter-analyze

# JSON output format
orion cmd -o json --hunter-analyze

# JUnit XML format
orion cmd -o junit --hunter-analyze

# Collapse output (show only changepoints and surrounding data)
orion cmd --collapse --hunter-analyze
```

## UUID and Baseline Options

### Specific UUID Analysis
Analyze a specific UUID bypassing metadata matching:
```bash
orion cmd --uuid <uuid> --hunter-analyze
```

### Baseline Comparison
Compare against specific baseline UUIDs:
```bash
orion cmd --uuid <current_uuid> --baseline "<uuid1>,<uuid2>,<uuid3>" --hunter-analyze
```

**Note:** `--baseline` should only be used with `--uuid`

## Time-Based Filtering

### Lookback Period
Constrain your analysis to a specific time period:
```bash
# Look back 5 days and 12 hours
orion cmd --lookback 5d12h --hunter-analyze

# Look back 2 days
orion cmd --lookback 2d --hunter-analyze

# Look back 8 hours
orion cmd --lookback 8h --hunter-analyze
```

### Lookback Size
Limit the number of runs to analyze:
```bash
# Analyze last 50 runs
orion cmd --lookback-size 50 --hunter-analyze
```

### Combined Lookback Options
When using both options, the more restrictive limit applies:

```bash
# Gets whichever is shorter: last 10 runs OR last 3 days
orion cmd --lookback 3d --lookback-size 10 --hunter-analyze
```

**Example Scenario:**
Consider runs on dates: 21 Aug, 22 Aug (3 runs), 23 Aug (2 runs), 24 Aug, 25 Aug, 26 Aug

Today is 27 Aug:
- `--lookback 5d`: Gets runs from 22 Aug onwards
- `--lookback-size 6`: Gets last 6 runs  
- `--lookback 5d --lookback-size 6`: Gets last 6 runs from 22 Aug onwards
- `--lookback 3d --lookback-size 6`: Gets runs from 24 Aug onwards (3 days wins)

## Node Count Filtering

### Relaxed Matching
Open match requirements to find UUIDs based on metadata without exact jobConfig.jobIterations match:
```bash
orion cmd --node-count true --hunter-analyze
```

Default is `false` for strict matching.

## Debugging and Logging

### Debug Mode
Enable detailed debug logs:
```bash
orion cmd --debug --hunter-analyze
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
orion cmd --ack ack.yaml --hunter-analyze
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
        metricName: containerCPU
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
        metricName: podLatencyQuantilesMeasurement
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
        metricName: containerCPU
        labels.namespace.keyword: openshift-ovn-kubernetes
        metric_of_interest: value
        agg:
          value: cpu
          agg_type: avg
        direction: 0
        threshold: 20

      # Correlated metric - only alerts if ovnCPU has changepoint
      - name: podReadyLatency
        metricName: podLatencyQuantilesMeasurement
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
        metricName: containerCPU
        labels.namespace.keyword: openshift-kube-apiserver
        metric_of_interest: value
        agg:
          value: cpu
          agg_type: avg
        labels:
          - "[Jira: kube-apiserver]"

      - name: etcdCPU
        metricName: containerCPU
        labels.namespace.keyword: openshift-etcd
        metric_of_interest: value
        agg:
          value: cpu
          agg_type: avg
        labels:
          - "[Jira: etcd]"

      - name: etcdDisk
        metricName: 99thEtcdDiskBackendCommitDurationSeconds
        metric_of_interest: value
        agg:
          value: duration
          agg_type: avg
        labels:
          - "[Jira: etcd]"

      - name: kubeletCPU
        metricName: kubeletCPU
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
orion cmd --config performance-config.yaml --hunter-analyze

# Run with debug output
orion cmd --config performance-config.yaml --hunter-analyze --debug
```

### Time-Constrained Analysis
```bash
# Analyze last 7 days of data
orion cmd --config performance-config.yaml --hunter-analyze --lookback 7d

# Analyze last 24 hours with maximum 50 runs
orion cmd --config performance-config.yaml --hunter-analyze --lookback 24h --lookback-size 50
```

### Specific UUID Analysis
```bash
# Analyze specific run against historical data
orion cmd --config metrics-only.yaml --uuid "abc123-def456-ghi789" --hunter-analyze

# Compare specific run against baselines
orion cmd --config metrics-only.yaml \
  --uuid "current-run-uuid" \
  --baseline "baseline1,baseline2,baseline3" \
  --cmr
```

### Output Formatting
```bash
# Generate JSON output with only changepoints
orion cmd --config performance-config.yaml --hunter-analyze -o json --collapse

# Generate JUnit XML for CI integration
orion cmd --config performance-config.yaml --hunter-analyze -o junit --output results.xml
```

### Performance Analysis with Custom Thresholds
```bash
orion cmd \
  --config perf-config.yaml \
  --hunter-analyze \
  --lookback 7d \
  --threshold 15 \
  --output results.csv \
  --debug
```

### Baseline Comparison with JSON Output
```bash
orion cmd \
  --uuid "current-run-uuid" \
  --baseline "baseline1,baseline2" \
  --cmr \
  -o json \
  --collapse
```

### Quick Anomaly Check
```bash
orion cmd \
  --config quick-check.yaml \
  --anomaly-detection \
  --lookback 24h \
  --output anomalies.json
```

## Daemon Mode Examples

### Basic Daemon Usage
```bash
# Start daemon
orion daemon

# Query for changepoints
curl -X POST 'http://127.0.0.1:8080/daemon/changepoint?filter_changepoints=true&test_name=cpu-monitoring'
```

### Automated Monitoring Script
```bash
#!/bin/bash
# automated-monitoring.sh

DAEMON_URL="http://127.0.0.1:8080"
TEST_NAME="full-stack-monitoring"
OUTPUT_DIR="./monitoring-results"

mkdir -p "$OUTPUT_DIR"

while true; do
    timestamp=$(date +%Y%m%d-%H%M%S)
    output_file="$OUTPUT_DIR/results-$timestamp.json"
    
    # Query for changepoints
    curl -s -X POST "$DAEMON_URL/daemon/changepoint?filter_changepoints=true&test_name=$TEST_NAME" \
         > "$output_file"
    
    # Check if any changepoints were detected
    if grep -q '"is_changepoint": true' "$output_file"; then
        echo "$(date): Changepoint detected! Check $output_file"
        # Add your notification logic here (email, Slack, etc.)
    fi
    
    # Wait 1 hour before next check
    sleep 3600
done
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
orion cmd --config performance-config.yaml --hunter-analyze --ack known-issues.yaml
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
   - Anomaly: Outlier detection 
