
<p align="center">
    <img src="images/logo.jpg" alt="Orion Logo" width="300">
</p>

# Orion - CLI tool to find regressions

Orion stands as a powerful command-line tool designed for identifying regressions within perf-scale CPT runs, leveraging metadata provided during the process. The detection mechanism relies on [hunter now apache otava](https://github.com/apache/otava).

## Quick Start

### Podman

```bash
$ podman build -f Dockerfile -t orion
$ podman run orion orion --config examples/trt-external-payload-node-density.yaml --hunter-analyze --input-vars='{"version": "4.19"}' --es-server='https://my-opensearch.perf.com' --benchmark-index=ripsaw-kube-burner-* --metadata-index=perf_scale_ci* --lookback=15d
 ```


### Installation

Requirements:
- Python 3.11 or higher
- pip or uv


```bash
$ git clone https://github.com/cloud-bulldozer/orion.git
$ cd orion && uv venv
$ source venv/bin/activate
$ make install
```

### Basic Usage

Trigger hunter analysis using data from the 15 latest days 

```bash
# Command-line mode
$ orion --config examples/trt-external-payload-node-density.yaml --hunter-analyze --input-vars='{"version": "4.19"}' --es-server='htts://my-opensearch.perf.com' --benchmark-index=ripsaw-kube-burner-* --metadata-index=perf_scale_ci* --lookback=15d
2025-08-12 10:45:31,965 - Orion      - INFO - file: main.py - line: 136 - 🏹 Starting Orion in command-line mode                                                                              2025-08-12 10:45:31,971 - Orion      - INFO - file: utils.py - line: 317 - The test payload-node-density has started                                                            
2025-08-12 10:45:31,971 - Matcher    - INFO - file: matcher.py - line: 75 - Executing query against index: perf_scale_ci*                                                                     2025-08-12 10:45:33,179 - Matcher    - INFO - file: matcher.py - line: 75 - Executing query against index: perf_scale_ci*                                                      
2025-08-12 10:45:33,441 - Matcher    - INFO - file: matcher.py - line: 75 - Executing query against index: ripsaw-kube-burner-*                                                               2025-08-12 10:45:33,715 - Orion      - INFO - file: utils.py - line: 67 - Collecting podReadyLatency                                                                            
2025-08-12 10:45:33,716 - Matcher    - INFO - file: matcher.py - line: 75 - Executing query against index: ripsaw-kube-burner-*                                                               2025-08-12 10:45:33,896 - Orion      - INFO - file: utils.py - line: 67 - Collecting apiserverCPU                                                                               
2025-08-12 10:45:33,897 - Matcher    - INFO - file: matcher.py - line: 75 - Executing query against index: ripsaw-kube-burner-*                                                               2025-08-12 10:45:34,697 - Orion      - INFO - file: utils.py - line: 67 - Collecting ovnCPU                                                                                                   
etc.
```

## Features

- **Regression Detection**: Identify performance regressions using advanced statistical methods
- **Multiple Algorithms**: Support for Hunter, CMR, and anomaly detection
- **Flexible Configuration**: YAML-based configuration with extensive customization options
- **Multiple Output Formats**: JSON, CSV, and JUnit XML output support
- **JIRA Integration**: Track and auto-create regression acknowledgments in JIRA

### JIRA Integration

Track performance regressions as JIRA issues with automatic creation and rich context:

```bash
# Query existing JIRA acknowledgments
orion --config config.yaml --jira-ack

# Auto-create JIRA issues for new regressions
orion --config config.yaml --jira-ack --jira-auto-create \
  --jira-url https://issues.example.com \
  --jira-project PERFSCALE \
  --jira-component CPT_ISSUES
```

Set environment variables for authentication:
```bash
export JIRA_TOKEN="your_token"
```

Auto-created issues include full regression details, affected metrics, related PRs, and GitHub context. See the [Configuration documentation](docs/configuration.md) for complete configuration options.

## Documentation

- **[Installation Guide](docs/installation.md)** - Detailed setup and build instructions
- **[Configuration](docs/configuration.md)** - Configuration format and metrics options
- **[Usage Guide](docs/usage.md)** - Command-line options, examples, and configurations
- **[CI Tests](hack/ci-tests/ci-tests.md)** - CI Tests data generation

## Compatibility

Orion currently supports Python version `3.11.x`. Please be aware that using other Python versions might lead to dependency conflicts. Python `3.12.x` may result in errors due to the removal of distutils.

## Contributing

Please read [CONTRIBUTING.md](CONTRIBUTING.md) for details on our code of conduct and the process for submitting pull requests.

## License

This project is licensed under the terms specified in the [LICENSE](LICENSE) file.

