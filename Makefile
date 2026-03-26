.PHONY: help lint fix-lint

help:
	@echo "Available targets:"
	@echo "  lint      - Run YAML linting to check for issues"
	@echo "  fix-lint  - Automatically fix common YAML linting issues"
	@echo "  help      - Show this help message"

.DEFAULT_GOAL := help
lint:
	yamllint config

fix-lint:
	@echo "Checking for YAML formatting tools..."
	if command -v yamlfmt >/dev/null 2>&1; then \
		echo "Using yamlfmt (Go YAML formatter)..."; \
		yamlfmt -w config/; \
	else \
		echo "No dedicated YAML formatter found. Using yq with better formatting..."; \
		for file in $$(yamllint --list-files config 2>/dev/null); do \
			echo "Formatting $$file"; \
			yq eval -i --indent 2 '.' "$$file" 2>/dev/null || echo "Warning: Could not format $$file"; \
		done; \
	fi
	@echo "Adding missing newlines at end of files..."
	@yamllint --list-files config 2>/dev/null | xargs -I {} sh -c 'if [ -s "{}" ] && [ "$$(tail -c 1 "{}" | wc -l)" -eq 0 ]; then echo "" >> "{}"; fi'
	@echo "Auto-fix complete! Run 'make lint' to check for remaining issues."
	@echo ""
	@echo "💡 Tip: Install a YAML formatter for best results:"
	@echo "   pip install yamlfix          # Python-based, very configurable"
