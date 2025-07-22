# Orion - CLI tool to find regressions

Orion stands as a powerful command-line tool/daemon designed for identifying regressions within perf-scale CPT runs, leveraging metadata provided during the process. The detection mechanism relies on [hunter](https://github.com/datastax-labs/hunter).

## Quick Start

### Installation
```bash
git clone <repository_url>
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
export ES_SERVER=<es_server_url>
pip install .
```

### Basic Usage
```bash
# Command-line mode
orion cmd --hunter-analyze

# Daemon mode
orion daemon
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

