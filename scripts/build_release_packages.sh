#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=== Simulacra Dual-Release Packaging Script ==="
echo "Root directory: $ROOT_DIR"

PUBLISH_DIR="$ROOT_DIR/publish/linux-x64"
RELEASES_DIR="$ROOT_DIR/releases"
MODELS_DIR="$ROOT_DIR/Models"

rm -rf "$PUBLISH_DIR"
mkdir -p "$PUBLISH_DIR"
mkdir -p "$RELEASES_DIR"

echo "--> Publishing CharacterSimulator.GUI (Release linux-x64)..."
dotnet publish "$ROOT_DIR/CharacterSimulator.GUI/CharacterSimulator.GUI.csproj" \
    -c Release \
    -r linux-x64 \
    --self-contained true \
    -o "$PUBLISH_DIR"

# Ensure Models directory exists inside publish output
mkdir -p "$PUBLISH_DIR/Models"

# 1. Package LITE Release (Without GGUF Model, ~80 MB)
LITE_TAR="$RELEASES_DIR/Simulacra-v1.0-Lite-linux-x64.tar.gz"
echo "--> Creating Lite Release package: $LITE_TAR"
tar -czf "$LITE_TAR" -C "$ROOT_DIR/publish" linux-x64

LITE_SIZE=$(du -h "$LITE_TAR" | cut -f1)
echo "✅ Created Lite Package: $LITE_TAR ($LITE_SIZE)"

# 2. Package FULL Release (With Qwen 2.5 3B GGUF Model, ~2.1 GB)
MODEL_FILE="$MODELS_DIR/qwen2.5-3b-instruct-q4_k_m.gguf"
if [ -f "$MODEL_FILE" ]; then
    echo "--> Copying Qwen 2.5 3B GGUF model into publish output..."
    cp "$MODEL_FILE" "$PUBLISH_DIR/Models/"

    FULL_TAR="$RELEASES_DIR/Simulacra-v1.0-Full-linux-x64.tar.gz"
    echo "--> Creating Full Standalone Release package: $FULL_TAR"
    tar -czf "$FULL_TAR" -C "$ROOT_DIR/publish" linux-x64

    FULL_SIZE=$(du -h "$FULL_TAR" | cut -f1)
    echo "✅ Created Full Standalone Package: $FULL_TAR ($FULL_SIZE)"
else
    echo "⚠️ Note: GGUF model file not found at $MODEL_FILE. Full package skipped (run download task to generate Full package)."
fi

echo "=== Release Build Complete ==="
