# OpenSearch Test Data Loader

This directory contains a script and data files for loading test data into OpenSearch for Orion integration testing.

## Files

- `metadata_data.json` - Test dataset containing 10 metadata entries with dates going back one day per entry
- `metric_data.json` - Template for metric documents used in testing
- `rhoso.json` - Pre-built dataset with `metadata` and `metrics` arrays for RHOSO/Browbeat-style integration tests
- `load_metrics_to_opensearch.py` - Python script to load all test data into OpenSearch (metadata, generated metrics, and rhoso data)
- `experiment_data.py` - Synthetic 15-run slow-ramp experiment dataset (5 flat points, then +1% per run)

## Prerequisites

- **Python 3.11** - Python interpreter
- **requests** - Python HTTP library
  ```bash
  pip install requests
  ```

## Quick Start

### Load Everything

Load metadata, generated metrics, and rhoso data in one command:

```bash
python hack/ci-tests/load_metrics_to_opensearch.py --all
```

### Load Individually

```bash
# Load metadata only
python hack/ci-tests/load_metrics_to_opensearch.py --metadata

# Load generated metrics only (default mode)
python hack/ci-tests/load_metrics_to_opensearch.py

# Load rhoso data only
python hack/ci-tests/load_metrics_to_opensearch.py --rhoso

# Load the 15-point slow-ramp experiment dataset
python hack/ci-tests/load_metrics_to_opensearch.py --experiment

# Analyze it (15 points: 5 flat, then +1% per run)
orion --lookback 30d --since 2026-01-27 --hunter-analyze \
  --config hack/ci-tests/configurations/ci-tests-experiment.yaml \
  --metadata-index "orion-integration-test-data*" \
  --benchmark-index "orion-integration-test-metrics*" \
  --es-server http://localhost:9200 --node-count true \
  --input-vars='{"version": "4.20"}'
```

### Analyze the same ramp with `acceptable_range`

The same 15-point ramp can be analyzed with an `acceptable_range` (an
inclusive absolute value band) instead of `threshold`. The bounds are
templated, so one config covers both outcomes:

```bash
# Band [0, 105]: the detected changepoint's value (107.0) is OUTSIDE -> regression (exit 2)
orion --lookback 30d --since 2026-01-27 --hunter-analyze \
  --config hack/ci-tests/configurations/ci-tests-experiment-range.yaml \
  --metadata-index "orion-integration-test-data*" \
  --benchmark-index "orion-integration-test-metrics*" \
  --es-server http://localhost:9200 --node-count true \
  --input-vars='{"version": "4.20", "range_min": 0, "range_max": 105}'

# Band [0, 110]: the same changepoint's value (107.0) is INSIDE -> filtered out (exit 0)
orion --lookback 30d --since 2026-01-27 --hunter-analyze \
  --config hack/ci-tests/configurations/ci-tests-experiment-range.yaml \
  --metadata-index "orion-integration-test-data*" \
  --benchmark-index "orion-integration-test-metrics*" \
  --es-server http://localhost:9200 --node-count true \
  --input-vars='{"version": "4.20", "range_min": 0, "range_max": 110}'
```

A metric with `acceptable_range` ignores both `threshold` and `direction`:
a detected changepoint is reported iff the **actual value at the changepoint
row** falls outside the inclusive `[range_min, range_max]` band (segment means
are not used for the check).

### Custom OpenSearch Server

```bash
# Via flag
python hack/ci-tests/load_metrics_to_opensearch.py --all \
  --es-server https://opensearch.example.com:9200

# Via environment variable (supports credentials in URL)
export ES_SERVER="https://user:password@opensearch.example.com:9200"
python hack/ci-tests/load_metrics_to_opensearch.py --all
```

## Modes

The script supports four modes:

| Mode | Flag | Description |
|------|------|-------------|
| **Metrics** | *(default)* | Generates metric documents from `metadata_data.json` + `metric_data.json` template. Creates 50 docs per UUID (500 total) with 30s-spaced timestamps. |
| **Metadata** | `--metadata` | Loads `metadata_data.json` into the metadata index. |
| **Rhoso** | `--rhoso` | Loads `rhoso.json` as-is: metadata to metadata index, metrics to metrics index. |
| **Experiment** | `--experiment` | Loads the synthetic 15-run slow-ramp dataset from `experiment_data.py`: 15 metadata docs + 15 metric docs (one metric per run → 15 data points). Runs 1-5 are flat at 100.0; runs 6-15 rise +1% per run (101.0 .. 110.0). |
| **All** | `--all` | Runs metadata, metrics, and rhoso in sequence. |

All modes use the OpenSearch `_bulk` API for fast indexing.

## Command-Line Options

| Option | Description | Default |
|--------|-------------|---------|
| `--all` | Load metadata, metrics, and rhoso data | Off |
| `--metadata` | Load metadata documents only | Off |
| `--rhoso` | Load rhoso.json data only | Off |
| `--es-server URL` | OpenSearch server URL | `https://localhost:9200` or `ES_SERVER` env var |
| `--index NAME` | Index name for metrics | `orion-integration-test-metrics` |
| `--metadata-index NAME` | Index name for metadata | `orion-integration-test-data` |
| `--metadata-file PATH` | Path to metadata JSON file | `./metadata_data.json` |
| `--metric-file PATH` | Path to metric template JSON file | `./metric_data.json` |
| `--rhoso-file PATH` | Path to rhoso JSON file | `./rhoso.json` |
| `--count N` | Number of documents per UUID (metrics mode) | `50` |
| `--interval N` | Seconds between timestamps (metrics mode) | `30` |
| `--verify-ssl` | Verify SSL certificates | Disabled |

## Test Data Structure

### Metadata Data (`metadata_data.json`)

Array of 10 metadata objects, each representing a test run with unique UUIDs, dates going back one day per entry (2026-01-19 to 2026-01-10), CI system information, cluster configuration, and OpenShift version details.

### Metric Data (`metric_data.json`)

Template for metric documents. The script generates documents with UUIDs from metadata, 30-second-spaced timestamps, and metric values. Four UUIDs get overridden values to create detectable changepoints for regression testing.

### RHOSO Data (`rhoso.json`)

Single JSON object with `metadata` and `metrics` arrays for Browbeat/Rally-style tests. Loaded as-is without transformation.

### Experiment Data (`experiment_data.py`)

Synthetic slow-ramp dataset used by the `--experiment` mode and `configurations/ci-tests-experiment.yaml`. 15 runs (`ci-exp-01` .. `ci-exp-15`), one per day from 2026-01-12 to 2026-01-26, each carrying a single `catalogd_cpu_usage_cores_experiment` metric document:

| Runs | Dates | Values |
|------|-------|--------|
| 1-5 | 01-12 .. 01-16 | 100.0 (flat, no change) |
| 6-15 | 01-17 .. 01-26 | 101.0 .. 110.0 (steady +1% per run) |

Because each run contributes exactly one metric document, the aggregated series Orion analyzes has exactly 15 data points.

## Integration with Orion

```bash
# Load all test data
python hack/ci-tests/load_metrics_to_opensearch.py --all \
  --es-server https://localhost:9200

# Run Orion against it
orion \
  --es-server https://localhost:9200 \
  --metadata-index orion-integration-test-data \
  --benchmark-index orion-integration-test-metrics \
  --config hack/ci-tests/configurations/ci-tests.yaml \
  --hunter-analyze
```

## Exit Codes

- `0`: All documents loaded successfully
- `1`: One or more documents failed to load, or invalid arguments
