# OpenSearch Test Data Loader

This directory contains scripts and data for loading test metadata and metrics into OpenSearch for Orion integration testing.

## Files

- `metadata_data.json` - Test dataset containing 10 metadata entries with dates going back one day per entry
- `metric_data.json` - Template for metric documents used in testing
- `load_metadata_to_opensearch.sh` - Bash script to load the metadata JSON file into OpenSearch
- `load_metrics_to_opensearch.py` - Python script to generate and load metric documents into OpenSearch

## Prerequisites

Before running the scripts, ensure you have the following tools installed:

### For Metadata Loader (Bash Script)

- **jq** - JSON processor (required for parsing the JSON file)
  - macOS: `brew install jq`
  - Linux: `apt-get install jq` or `yum install jq`
  - Windows: Download from [jq website](https://stedolan.github.io/jq/download/)

- **curl** - Command-line tool for making HTTP requests (usually pre-installed on Unix systems)

### For Metrics Loader (Python Script)

- **Python 3.11** - Python interpreter
- **requests** - Python HTTP library
  ```bash
  pip install requests
  ```

## Quick Start

### Loading Metadata

1. Run with default settings (connects to `https://localhost:9200`):
   ```bash
   ./hack/ci-tests/load_metadata_to_opensearch.sh
   ```

### Loading Metrics

1. Install Python dependencies:
   ```bash
   pip install requests
   ```

2. Run with default settings:
   ```bash
   python hack/ci-tests/load_metrics_to_opensearch.py
   ```

## Metadata Loader Script

The `load_metadata_to_opensearch.sh` script loads metadata documents from `metadata_data.json` into OpenSearch.

### Basic Usage

```bash
# Use defaults (localhost:9200, index: orion-integration-test-data)
./hack/ci-tests/load_metadata_to_opensearch.sh

# Specify custom OpenSearch server
./hack/ci-tests/load_metadata_to_opensearch.sh --es-server https://opensearch.example.com:9200

# Specify custom index name
./hack/ci-tests/load_metadata_to_opensearch.sh --index my-test-index

# Specify custom JSON file
./hack/ci-tests/load_metadata_to_opensearch.sh --file /path/to/your/metadata.json
```

### Command-Line Options

| Option | Description | Default |
|--------|-------------|---------|
| `--es-server URL` | OpenSearch server URL | `https://localhost:9200` |
| `--index NAME` | Index name where documents will be loaded | `orion-integration-test-data` |
| `--file PATH` | Path to JSON file containing metadata | `./metadata_data.json` |
| `--insecure` | Skip SSL certificate verification | Enabled by default |
| `--help` | Display help message | - |

### Environment Variables

You can also configure the script using environment variables:

```bash
# Set OpenSearch server URL (can include credentials)
export ES_SERVER="https://user:password@opensearch.example.com:9200"

# Set index name
export ES_METADATA_INDEX="my-custom-index"

# Run the script
./hack/ci-tests/load_metadata_to_opensearch.sh
```

**Note:** The `ES_SERVER` environment variable can include authentication credentials in the URL format: `https://username:password@host:port`

### Authentication

The script supports authentication via the `ES_SERVER` environment variable. Include credentials in the URL:

```bash
export ES_SERVER="https://admin:secretpassword@opensearch.example.com:9200"
./hack/ci-tests/load_metadata_to_opensearch.sh
```

Alternatively, you can pass the full URL with credentials via the `--es-server` option:

```bash
./hack/ci-tests/load_metadata_to_opensearch.sh \
  --es-server "https://admin:secretpassword@opensearch.example.com:9200"
```

### How It Works

1. **Connection Test**: The script first tests the connection to the OpenSearch server
2. **Index Creation**: If the specified index doesn't exist, it will be created automatically with:
   - 1 shard
   - 0 replicas (suitable for testing)
3. **Document Loading**: Each JSON object from the array is loaded as a separate document
4. **Document IDs**: The script uses the `uuid` field from each document as the OpenSearch document ID when available, ensuring idempotent operations (re-running the script won't create duplicates)

### Example Output

```
Testing connection to OpenSearch at https://localhost:9200...
Checking if index 'orion-integration-test-data' exists...
Index 'orion-integration-test-data' does not exist. Creating it...
Index created successfully.

Loading 10 documents from ./metadata_data.json to index 'orion-integration-test-data'...

[1/10] ✓ Loaded document with UUID: a1b2c3d4-e5f6-4789-a012-b3c4d5e6f789
[2/10] ✓ Loaded document with UUID: b2c3d4e5-f6a7-4890-b123-c4d5e6f7a890
[3/10] ✓ Loaded document with UUID: c3d4e5f6-a7b8-4901-c234-d5e6f7a8b901
...

=========================================
Summary:
  Successfully loaded: 10 documents
  Failed: 0 documents
  Total: 10 documents
=========================================
```

## Metrics Loader Script

The `load_metrics_to_opensearch.py` script generates and loads metric documents into OpenSearch. For each UUID in `metadata_data.json`, it creates 50 metric documents with timestamps spaced 30 seconds apart.

### Basic Usage

```bash
# Use defaults (localhost:9200, index: orion-integration-test-metrics)
python hack/ci-tests/load_metrics_to_opensearch.py

# Specify custom OpenSearch server and index
python hack/ci-tests/load_metrics_to_opensearch.py \
  --es-server https://opensearch.example.com:9200 \
  --index my-metrics-index

# Custom document count and timestamp interval
python hack/ci-tests/load_metrics_to_opensearch.py \
  --count 100 \
  --interval 60
```

### Command-Line Options

| Option | Description | Default |
|--------|-------------|---------|
| `--es-server URL` | OpenSearch server URL | `https://localhost:9200` or `ES_SERVER` env var |
| `--index NAME` | Index name for metrics | `orion-integration-test-metrics` or `ES_BENCHMARK_INDEX` env var |
| `--metadata-file PATH` | Path to metadata JSON file | `./metadata_data.json` |
| `--metric-file PATH` | Path to metric template JSON file | `./metric_data.json` |
| `--count N` | Number of documents per UUID | `50` |
| `--interval N` | Seconds between timestamps | `30` |
| `--verify-ssl` | Verify SSL certificates | Disabled by default |
| `--help` | Display help message | - |

### Environment Variables

```bash
# Set OpenSearch server URL (can include credentials)
export ES_SERVER="https://user:password@opensearch.example.com:9200"

# Set metrics index name
export ES_BENCHMARK_INDEX="my-metrics-index"

# Run the script
python hack/ci-tests/load_metrics_to_opensearch.py
```

### How It Works

1. **Reads Metadata**: Loads UUIDs and OCP versions from `metadata_data.json`
2. **Reads Template**: Loads the metric template from `metric_data.json`
3. **Generates Documents**: For each UUID, creates the specified number of metric documents:
   - Replaces the `uuid` field with the actual UUID from metadata
   - Updates timestamps to be spaced at the specified interval (default: 30 seconds)
   - Updates `ocpVersion` in the metadata section to match the corresponding metadata entry
4. **Loads to OpenSearch**: Posts all documents to the specified index
5. **Unique Document IDs**: Uses UUID + timestamp to create unique document IDs

### Example Output

```
OpenSearch server: https://localhost:9200
Index: orion-integration-test-metrics
Metadata file: ./metadata_data.json
Metric template file: ./metric_data.json
Documents per UUID: 50
Timestamp interval: 30 seconds

Loading files...
Found 10 UUIDs in metadata file

Testing connection to OpenSearch at https://localhost:9200...
✓ Connection successful

Ensuring index 'orion-integration-test-metrics' exists...
✓ Index ready

Generating and loading 500 metric documents...

UUID 1/10: a1b2c3d4-e5f6-4789-a012-b3c4d5e6f789
  [10/50] ✓ Loaded
  [20/50] ✓ Loaded
  [30/50] ✓ Loaded
  [40/50] ✓ Loaded
  [50/50] ✓ Loaded

UUID 2/10: b2c3d4e5-f6a7-4890-b123-c4d5e6f7a890
  [10/50] ✓ Loaded
  ...

==================================================
Summary:
  Successfully loaded: 500 documents
  Failed: 0 documents
  Total: 500 documents
==================================================

✓ All documents loaded successfully!
```

## Test Data Structure

### Metadata Data

The `metadata_data.json` file contains an array of 10 metadata objects, each representing a test run with:

- **Unique UUIDs** for each entry
- **Dates going back one day** per entry (from 2026-01-19 to 2026-01-10)
- **Complete metadata** including:
  - CI system information (PROW)
  - Cluster configuration
  - OpenShift version
  - Job execution details
  - Timestamps and build information

Each document is suitable for testing Orion's metadata matching and regression detection capabilities.

### Metric Data

The `metric_data.json` file is a template for metric documents. The script uses it to generate metric documents with:

- **UUID**: Replaced with actual UUIDs from metadata
- **Timestamp**: Generated with 30-second intervals (configurable)
- **Value**: Metric value (from template)
- **Metadata**: OCP version information synchronized with corresponding metadata entry

The script generates **500 total documents** (10 UUIDs × 50 documents each) by default, suitable for testing Orion's metric analysis and changepoint detection.

## Troubleshooting

### Connection Issues

If you encounter connection errors:

1. **Verify OpenSearch is running**: Check that your OpenSearch instance is accessible
   ```bash
   curl https://localhost:9200
   ```

2. **Check SSL certificates**: The script uses `--insecure` by default. If you need to verify certificates, you'll need to modify the script.

3. **Verify authentication**: Ensure credentials are correctly formatted in the URL:
   ```bash
   # Correct format
   https://user:pass@host:port
   ```

### Index Creation Failures

If index creation fails:

- The script will continue and attempt to load documents anyway
- OpenSearch may auto-create the index when the first document is posted
- Check OpenSearch logs for detailed error messages

### Document Loading Failures

If some documents fail to load:

- Check the HTTP status code in the error message
- Common issues:
  - **401/403**: Authentication problems
  - **400**: Invalid document format
  - **503**: OpenSearch cluster is busy or unavailable

### Missing Dependencies

**For Metadata Loader:**
- If you see errors about missing `jq` or `curl`:
  - Install the missing tool using your system's package manager
  - Verify installation: `jq --version` and `curl --version`

**For Metrics Loader:**
- If you see errors about missing `requests`:
  - Install it: `pip install requests`
  - Verify installation: `python -c "import requests; print(requests.__version__)"`

## Integration with Orion

After loading both metadata and metrics, you can use them with Orion:

```bash
# Load metadata first
./hack/ci-tests/load_metadata_to_opensearch.sh

# Load metrics
python hack/ci-tests/load_metrics_to_opensearch.py

# Run Orion with the test data
orion \
  --es-server https://localhost:9200 \
  --metadata-index orion-integration-test-data \
  --benchmark-index orion-integration-test-metrics \
  --config hack/ci-tests/ci-test.yaml \
  --hunter-analyze
```

## Script Exit Codes

Both scripts use the following exit codes:

- `0`: Success - All documents loaded successfully
- `1`: Failure - One or more documents failed to load, or invalid arguments provided

## See Also

- [Orion Usage Guide](../../docs/usage.md) - For information on using Orion with OpenSearch
- [Orion Configuration Guide](../../docs/configuration.md) - For configuring Orion tests
