.PHONY: help lint fmt install uninstall test deps deps-test

help:
	@echo "Available targets:"
	@echo "  lint      - Run YAML linting to check for issues"
	@echo "  fmt       - Automatically fix common YAML linting issues"
	@echo "  install   - Install orion and its dependencies"
	@echo "  uninstall - Uninstall orion"
	@echo "  test      - Run the test suite with pytest"
	@echo "  help      - Show this help message"

.DEFAULT_GOAL := help
lint:
	$(PIP) install yamllint
	yamllint examples

fmt:
	@echo "Checking for YAML formatting tools..."
	@yamlfmt examples/ \
	@echo "Adding missing newlines at end of files..."
	@yamllint --list-files config 2>/dev/null | xargs -I {} sh -c 'if [ -s "{}" ] && [ "$$(tail -c 1 "{}" | wc -l)" -eq 0 ]; then echo "" >> "{}"; fi'
	@echo "Auto-fix complete! Run 'make lint' to check for remaining issues."

PIP := $(shell command -v uv > /dev/null 2>&1 && echo "uv pip" || echo "pip")

deps:
	$(PIP) install -r requirements.txt

deps-test:
	$(PIP) install -r requirements-test.txt

install: deps
	$(PIP) install .

uninstall:
	$(PIP) uninstall orion

test: lint deps-test
	pytest orion/tests/
