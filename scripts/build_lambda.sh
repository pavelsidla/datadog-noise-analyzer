#!/usr/bin/env bash
# Build the Lambda deployment package.
#
# Output: modules/noise-analyzer/lambda.zip
# Requires: pip3, zip
#
# Usage:
#   bash scripts/build_lambda.sh           # x86_64 (default)
#   bash scripts/build_lambda.sh arm64     # ARM64 (Graviton)

set -euo pipefail

ARCH="${1:-x86_64}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
BUILD_DIR="$PROJECT_ROOT/.build"
ZIP_PATH="$PROJECT_ROOT/modules/noise-analyzer/lambda.zip"

echo "Building Lambda package (arch: $ARCH)..."

# Clean previous build
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR"

# Copy Python source files
cp "$PROJECT_ROOT/noise_analyzer.py"     "$BUILD_DIR/"
cp "$PROJECT_ROOT/src/lambda_handler.py" "$BUILD_DIR/"
cp "$PROJECT_ROOT/src/metrics_publisher.py" "$BUILD_DIR/"

echo "Installing dependencies..."
pip3 install \
  --quiet \
  --target "$BUILD_DIR" \
  --platform "manylinux2014_${ARCH}" \
  --only-binary=:all: \
  --python-version "3.12" \
  --implementation cp \
  -r "$PROJECT_ROOT/src/requirements.txt"

# Remove unnecessary files to reduce zip size
find "$BUILD_DIR" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find "$BUILD_DIR" -type d -name "*.dist-info" -exec rm -rf {} + 2>/dev/null || true
find "$BUILD_DIR" -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
find "$BUILD_DIR" -name "*.pyc" -delete 2>/dev/null || true

# Create zip
echo "Zipping..."
cd "$BUILD_DIR"
zip -r9 "$ZIP_PATH" . --quiet

SIZE=$(du -sh "$ZIP_PATH" | cut -f1)
echo "Lambda package ready: $ZIP_PATH ($SIZE)"
echo ""
echo "Next steps:"
echo "  terraform init"
echo "  terraform plan"
echo "  terraform apply"
