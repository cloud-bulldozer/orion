.PHONY: fix-lint help pylint test

help:
	@echo "Available targets:"
	@echo "  lint      - Run YAML linting to check for issues"
	@echo "  fmt       - Automatically fix common YAML linting issues"
	@echo "  help      - Show this help message"
	@echo "  test      - Run unit tests"
	@echo "  pylint    - Run pylint on production (non-test) python code"

.DEFAULT_GOAL := help
lint:
	yamllint examples

fmt:
	@echo "Checking for YAML formatting tools..."
	@yamlfmt examples/ \
	@echo "Adding missing newlines at end of files..."
	@yamllint --list-files config 2>/dev/null | xargs -I {} sh -c 'if [ -s "{}" ] && [ "$$(tail -c 1 "{}" | wc -l)" -eq 0 ]; then echo "" >> "{}"; fi'
	@echo "Auto-fix complete! Run 'make lint' to check for remaining issues."

test:
	python -m pytest orion/tests/ -v

pylint:
	pylint -d R0915 -d R1702 -d R0913 -d R0914 -d C0103 -d R0912 -d R0911 -d R0917 -d E0102 \
		$$(git ls-files '*/*.py' '*.py' | grep -v '/tests/')
