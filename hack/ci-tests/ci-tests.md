# OpenSearch Test Data Loader

This directory contains a script and data files for loading test data into OpenSearch for Orion integration testing.

## Files

- `metadata_data.json` - Test dataset containing 10 metadata entries with dates going back one day per entry
- `metric_data.json` - Template for metric documents used in testing
- `rhoso.json` - Pre-built dataset with `metadata` and `metrics` arrays for RHOSO/Browbeat-style integration tests
- `load_metrics_to_opensearch.py` - Python script to load all test data into OpenSearch (metadata, generated metrics, and rhoso data)

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
```

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
