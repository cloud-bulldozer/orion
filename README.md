# Orion - CLI tool to find regressions

Orion stands as a powerful command-line tool/daemon designed for identifying regressions within perf-scale CPT runs, leveraging metadata provided during the process. The detection mechanism relies on [hunter](https://github.com/datastax-labs/hunter).

## Quick Start

### Podman
```bash
$ podman build -f Dockerfile -t orion
# Needed env vars.
# ES/OpenSearch Server where the results live
 $ export ES_SERVER='my-opensearch.perf.com'
 # Version of OpenShift
 $ export version=4.19
 # Index where the benchmark data is stored
 $ export es_benchmark_index=ripsaw-kube-burner*
 # Index where you store the run metadata
 $ export es_metadata_index=perf_scale_ci*
 $ podman run --env-host orion orion cmd --config orion/examples/trt-external-payload-node-density.yaml --hunter-analyze
 ```


### Installation
```bash
$ git clone <repository_url>
$ python3.11 -m venv venv
$ source venv/bin/activate
$ pip install -r requirements.txt
$ pip install .
```

### Basic Usage
```bash
# Command-line mode
$ orion cmd --hunter-analyze

# Daemon mode
$ orion daemon
```

## Features

- **Regression Detection**: Identify performance regressions using advanced statistical methods
- **Multiple Algorithms**: Support for Hunter, CMR, and anomaly detection
- **Flexible Configuration**: YAML-based configuration with extensive customization options
- **Command-line & Daemon Modes**: Use as a CLI tool or run as a service
- **Multiple Output Formats**: JSON, CSV, and JUnit XML output support

## Documentation

- **[Installation Guide](docs/installation.md)** - Detailed setup and build instructions
- **[Configuration](docs/configuration.md)** - Configuration format and metrics options
- **[Usage Guide](docs/usage.md)** - Command-line options, examples, and configurations
- **[Daemon Mode](docs/daemon-mode.md)** - API documentation and daemon setup

## Compatibility

Orion currently supports Python version `3.11.x`. Please be aware that using other Python versions might lead to dependency conflicts. Python `3.12.x` may result in errors due to the removal of distutils.

## Contributing

Please read [CONTRIBUTING.md](CONTRIBUTING.md) for details on our code of conduct and the process for submitting pull requests.

## License

This project is licensed under the terms specified in the [LICENSE](LICENSE) file.

