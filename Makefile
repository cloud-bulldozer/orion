.PHONY: help lint fix-lint

help:
	@echo "Available targets:"
	@echo "  lint      - Run YAML linting to check for issues"
	@echo "  fmt       - Automatically fix common YAML linting issues"
	@echo "  help      - Show this help message"

.DEFAULT_GOAL := help
lint:
	yamllint examples

fmt:
	@echo "Checking for YAML formatting tools..."
	@yamlfmt examples/ \
	@echo "Adding missing newlines at end of files..."
	@yamllint --list-files config 2>/dev/null | xargs -I {} sh -c 'if [ -s "{}" ] && [ "$$(tail -c 1 "{}" | wc -l)" -eq 0 ]; then echo "" >> "{}"; fi'
	@echo "Auto-fix complete! Run 'make lint' to check for remaining issues."
