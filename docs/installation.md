# Installation Guide

## System Requirements

### Python Version
Orion currently supports Python version `3.11.x`. 

**Important Compatibility Notes:**
- Using other Python versions might lead to dependency conflicts caused by hunter, creating a challenging situation known as "dependency hell"
- Python `3.12.x` may result in errors due to the removal of distutils, a dependency used by numpy
- This information is essential to ensure a smooth experience with Orion and avoid potential compatibility issues

## Installation Steps

### 1. Clone the Repository
```bash
git clone <repository_url>
cd orion
```

### 2. Set Up Virtual Environment
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Set Environment Variables
```bash
export ES_SERVER=<es_server_url>
```

### 5. Install Orion
```bash
pip install .
```

## Install with `uv`

You will need to have [uv](https://docs.astral.sh/uv/getting-started/installation/) installed, then you should run:

```bash
uv tool install -p 3.11 orion --from git+https://github.com/cloud-bulldozer/orion.git
```

## Verification

After installation, verify that Orion is working correctly:

```bash
orion --help
```

You should see the help output with available commands and options.

## Troubleshooting

### Common Issues

#### Dependency Conflicts
If you encounter dependency conflicts, ensure you're using Python 3.11.x and consider creating a fresh virtual environment.

#### Environment Variables
Make sure the `ES_SERVER` environment variable is properly set. You can verify this with:
```bash
echo $ES_SERVER
```

#### Permission Issues
If you encounter permission issues during installation, you may need to use `sudo` or check your Python installation permissions.

## Development Installation

For development purposes, you can install Orion in editable mode:

```bash
pip install -e .
```

This allows you to make changes to the code without reinstalling the package. 