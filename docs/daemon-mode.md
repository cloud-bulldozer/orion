# Daemon Mode

The daemon mode allows Orion to operate as a self-contained server, handling incoming HTTP requests for changepoint detection and anomaly analysis.

## Starting Daemon Mode

```bash
orion daemon
```

By default, the daemon starts on `http://127.0.0.1:8080`

## API Endpoints

### Changepoint Detection

Trigger changepoint detection on predefined tests.

**Endpoint:** `POST /daemon/changepoint`

**Parameters:**
- `uuid` (optional): The UUID of the run you want to compare with similar runs
- `baseline` (optional): Comma-separated list of baseline run UUIDs to compare against
- `version` (optional): The ocpVersion for metadata filtering (defaults to `4.15`)
- `filter_changepoints` (optional): Set to `true` to only show changepoints in response
- `test_name` (optional): Name of the test to perform (defaults to `small-scale-cluster-density`)

**Example Requests:**

```bash
# Basic changepoint detection
curl -X POST 'http://127.0.0.1:8080/daemon/changepoint'

# Filter for changepoints only
curl -X POST 'http://127.0.0.1:8080/daemon/changepoint?filter_changepoints=true'

# Specific version and test
curl -X POST 'http://127.0.0.1:8080/daemon/changepoint?version=4.14&test_name=small-scale-node-density-cni'

# With specific UUID and baseline
curl -X POST 'http://127.0.0.1:8080/daemon/changepoint?uuid=abc123&baseline=def456,ghi789'
```

**Response Format:**

```json
{
    "aws-small-scale-cluster-density-v2": [
        {
            "uuid": "4cb3efec-609a-4ac5-985d-4cbbcbb11625",
            "timestamp": 1704889895,
            "buildUrl": "https://tinyurl.com/2ya4ka9z",
            "metrics": {
                "ovnCPU_avg": {
                    "value": 2.8503958847,
                    "percentage_change": 0
                },
                "apiserverCPU_avg": {
                    "value": 10.2344511574,
                    "percentage_change": 0
                },
                "etcdCPU_avg": {
                    "value": 8.7663162253,
                    "percentage_change": 0
                },
                "P99": {
                    "value": 13000,
                    "percentage_change": 0
                }
            },
            "is_changepoint": false
        }
    ]
}
```

### Anomaly Detection

Perform anomaly detection on preset metadata.

**Endpoint:** `POST /daemon/anomaly`

**Parameters:**
- `uuid` (optional): The UUID of the run to analyze
- `version` (optional): The ocpVersion for metadata filtering (defaults to `4.15`)
- `test_name` (optional): Name of the test to perform

**Example Request:**

```bash
curl -X POST 'http://127.0.0.1:8080/daemon/anomaly?test_name=cluster-density&version=4.16'
```

### List Available Tests

Get a list of available predefined tests.

**Endpoint:** `GET /daemon/options`

**Example Request:**

```bash
curl -X GET 'http://127.0.0.1:8080/daemon/options'
```

**Response Format:**

```json
{
    "options": [
        "small-scale-cluster-density",
        "small-scale-node-density-cni",
        "payload-cluster-density-v2",
        "medium-scale-node-density"
    ]
}
```

## Response Fields

### Run Object
Each run in the response contains:

- `uuid`: Unique identifier for the test run
- `timestamp`: Unix timestamp of the run
- `buildUrl`: URL to the build (may be shortened if configured)
- `metrics`: Object containing metric results
- `is_changepoint`: Boolean indicating if this run contains any changepoints

### Metric Object
Each metric contains:

- `value`: The actual measured value
- `percentage_change`: Percentage change from baseline (0 if no change detected)

## Configuration

The daemon uses the same configuration files as the command-line mode. Ensure your configuration file includes the tests you want to make available via the API.

### Predefined Tests

Tests available in daemon mode are typically defined in your configuration file. Common predefined tests include:

- `small-scale-cluster-density`
- `small-scale-node-density-cni`
- `payload-cluster-density-v2`
- `medium-scale-node-density`

## Error Handling

The API returns appropriate HTTP status codes:

- `200`: Success
- `400`: Bad request (invalid parameters)
- `404`: Test not found
- `500`: Internal server error

Error responses include a message describing the issue:

```json
{
    "error": "Test 'invalid-test-name' not found",
    "available_tests": ["small-scale-cluster-density", "small-scale-node-density-cni"]
}
```

## Usage Patterns

### Continuous Monitoring
Set up automated requests to monitor for regressions:

```bash
#!/bin/bash
# Monitor for changepoints every hour
while true; do
    curl -X POST 'http://127.0.0.1:8080/daemon/changepoint?filter_changepoints=true' \
         -H 'Content-Type: application/json' \
         > "results-$(date +%Y%m%d-%H%M%S).json"
    sleep 3600
done
```

### Integration with CI/CD
Include daemon requests in your CI/CD pipeline:

```yaml
# Example GitHub Actions step
- name: Check for performance regressions
  run: |
    response=$(curl -s -X POST 'http://orion-daemon:8080/daemon/changepoint?filter_changepoints=true&test_name=cluster-density')
    if echo "$response" | grep -q '"is_changepoint": true'; then
      echo "Performance regression detected!"
      exit 1
    fi
```

### Baseline Comparisons
Compare new runs against known good baselines:

```bash
# Compare current run against last known good runs
curl -X POST 'http://127.0.0.1:8080/daemon/changepoint' \
     -G \
     --data-urlencode "uuid=current-run-uuid" \
     --data-urlencode "baseline=good-run-1,good-run-2,good-run-3"
```

## Security Considerations

When running the daemon in production:

1. **Network Security**: Consider running behind a reverse proxy
2. **Authentication**: Implement authentication if needed (not built-in)
3. **Rate Limiting**: Monitor and limit request rates if necessary
4. **Logging**: Enable appropriate logging for monitoring and debugging

## Troubleshooting

### Common Issues

**Daemon won't start:**
- Check if port 8080 is available
- Verify ES_SERVER environment variable is set
- Check configuration file syntax

**Tests not found:**
- Verify test names in your configuration file
- Use `/daemon/options` to see available tests
- Check configuration file path

**No data returned:**
- Verify ES_SERVER connectivity
- Check metadata filters in configuration
- Ensure test indices exist and contain data

### Debug Mode
Start daemon with debug logging:

```bash
export ORION_DEBUG=true
orion daemon
``` 