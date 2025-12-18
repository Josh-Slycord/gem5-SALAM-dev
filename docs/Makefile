# =============================================================================
# gem5-SALAM Documentation Makefile
# =============================================================================
# Makefile for Sphinx documentation generation.
#
# Usage:
#   make html      - Build HTML documentation
#   make latexpdf  - Build PDF documentation
#   make clean     - Remove built documentation
#   make doxygen   - Generate Doxygen XML (required before html)
#   make all       - Build Doxygen XML then HTML
#
# For a complete rebuild:
#   make clean && make all
# =============================================================================

# Sphinx configuration
SPHINXOPTS    ?=
SPHINXBUILD   ?= sphinx-build
SOURCEDIR     = .
BUILDDIR      = _build

# Doxygen configuration
DOXYFILE      = Doxyfile.salam
PROJECT_ROOT  = ..

# Colors for output
CYAN  = \033[0;36m
GREEN = \033[0;32m
NC    = \033[0m

.PHONY: help clean doxygen html latexpdf linkcheck all serve

# Default target
help:
	@echo "$(CYAN)gem5-SALAM Documentation Build$(NC)"
	@echo ""
	@echo "Usage: make <target>"
	@echo ""
	@echo "Targets:"
	@echo "  all       - Build Doxygen XML then HTML (recommended)"
	@echo "  html      - Build HTML documentation (requires doxygen first)"
	@echo "  latexpdf  - Build PDF documentation"
	@echo "  doxygen   - Generate Doxygen XML for Breathe"
	@echo "  clean     - Remove all built documentation"
	@echo "  linkcheck - Check external links"
	@echo "  serve     - Start local documentation server"
	@echo ""
	@echo "Example workflow:"
	@echo "  make clean && make all"
	@echo "  make serve"

# Clean build directory
clean:
	@echo "$(CYAN)Cleaning build directory...$(NC)"
	rm -rf $(BUILDDIR)
	@echo "$(GREEN)Clean complete$(NC)"

# Generate Doxygen XML for Breathe
doxygen:
	@echo "$(CYAN)Generating Doxygen XML...$(NC)"
	@mkdir -p $(BUILDDIR)/doxygen
	cd $(PROJECT_ROOT) && doxygen docs/$(DOXYFILE)
	@echo "$(GREEN)Doxygen XML generated in $(BUILDDIR)/doxygen/xml/$(NC)"

# Build HTML documentation
html: doxygen
	@echo "$(CYAN)Building HTML documentation...$(NC)"
	@$(SPHINXBUILD) -b html "$(SOURCEDIR)" "$(BUILDDIR)/html" $(SPHINXOPTS)
	@echo ""
	@echo "$(GREEN)HTML documentation built in $(BUILDDIR)/html/$(NC)"
	@echo "Open $(BUILDDIR)/html/index.html in a browser"

# Build PDF documentation
latexpdf: doxygen
	@echo "$(CYAN)Building PDF documentation...$(NC)"
	@$(SPHINXBUILD) -b latex "$(SOURCEDIR)" "$(BUILDDIR)/latex" $(SPHINXOPTS)
	@$(MAKE) -C "$(BUILDDIR)/latex" all-pdf
	@echo ""
	@echo "$(GREEN)PDF documentation built in $(BUILDDIR)/latex/$(NC)"

# Check external links
linkcheck:
	@echo "$(CYAN)Checking documentation links...$(NC)"
	@$(SPHINXBUILD) -b linkcheck "$(SOURCEDIR)" "$(BUILDDIR)/linkcheck" $(SPHINXOPTS)
	@echo ""
	@echo "$(GREEN)Link check results in $(BUILDDIR)/linkcheck/$(NC)"

# Build all (Doxygen + HTML)
all: html
	@echo ""
	@echo "$(GREEN)Documentation build complete!$(NC)"

# Start local documentation server
serve: html
	@echo "$(CYAN)Starting documentation server at http://localhost:8000$(NC)"
	@echo "Press Ctrl+C to stop"
	@cd $(BUILDDIR)/html && python3 -m http.server 8000

# Catch-all target for Sphinx builders
%: Makefile
	@$(SPHINXBUILD) -b $@ "$(SOURCEDIR)" "$(BUILDDIR)/$@" $(SPHINXOPTS)
