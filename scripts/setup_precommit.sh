#!/bin/bash
# Setup script for pre-commit hooks
# This installs pre-commit and sets up git hooks for security and code quality

set -e

echo "🔧 Setting up pre-commit hooks for transcript-create..."
echo ""

# Check if pre-commit is installed
if ! command -v pre-commit &> /dev/null; then
    echo "📦 Installing pre-commit..."
    pip install pre-commit
else
    echo "✓ pre-commit is already installed"
fi

# Install the git hooks
echo "🎣 Installing git hooks..."
pre-commit install

echo ""
echo "✅ Pre-commit hooks installed successfully!"
echo ""
echo "The following checks will run on each commit:"
echo "  - Trailing whitespace removal"
echo "  - End-of-file fixing"
echo "  - YAML/JSON validation"
echo "  - Secret detection (gitleaks)"
echo "  - Private key detection"
echo "  - Code formatting (black, isort)"
echo "  - Linting (flake8)"
echo ""
echo "To run checks manually on all files:"
echo "  pre-commit run --all-files"
echo ""
echo "To skip pre-commit checks (not recommended):"
echo "  git commit --no-verify"
echo ""
