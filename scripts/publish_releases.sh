#!/usr/bin/env bash
set -e

echo "=== Simulacra Release Packaging Script ==="
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

echo "Root Directory: $ROOT_DIR"
cd "$ROOT_DIR"

echo "Building and publishing win-x64 release..."
dotnet publish CharacterSimulator.GUI/CharacterSimulator.GUI.csproj \
    -c Release \
    -r win-x64 \
    --self-contained true \
    -o "$ROOT_DIR/publish/win-x64"

echo "Building and publishing linux-x64 release..."
dotnet publish CharacterSimulator.GUI/CharacterSimulator.GUI.csproj \
    -c Release \
    -r linux-x64 \
    --self-contained true \
    -o "$ROOT_DIR/publish/linux-x64"

echo "=== Release Build Packaging Complete ==="
echo "Artifacts generated in publish/win-x64 and publish/linux-x64."
