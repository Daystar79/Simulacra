#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=== Simulacra Multi-Platform Release Packaging Script ==="
echo "Root directory: $ROOT_DIR"

RELEASES_DIR="$ROOT_DIR/releases"
MODELS_DIR="$ROOT_DIR/Models"
MODEL_FILE="$MODELS_DIR/qwen2.5-3b-instruct-q4_k_m.gguf"

mkdir -p "$RELEASES_DIR"

package_target() {
    local RID="$1"
    local EXT="$2"

    echo "=================================================="
    echo "--> Publishing CharacterSimulator.GUI (Release $RID)..."
    local PUBLISH_DIR="$ROOT_DIR/publish/$RID"
    rm -rf "$PUBLISH_DIR"
    mkdir -p "$PUBLISH_DIR/Models"

    dotnet publish "$ROOT_DIR/CharacterSimulator.GUI/CharacterSimulator.GUI.csproj" \
        -c Release \
        -r "$RID" \
        --self-contained true \
        -o "$PUBLISH_DIR"

    # 1. Lite Package (Without GGUF Model)
    local LITE_PKG="$RELEASES_DIR/Simulacra-v1.0-Lite-$RID.$EXT"
    echo "--> Creating Lite package: $LITE_PKG"
    if [ "$EXT" = "zip" ]; then
        (cd "$ROOT_DIR/publish" && python3 -m zipfile -c "$LITE_PKG" "$RID")
    else
        tar -czf "$LITE_PKG" -C "$ROOT_DIR/publish" "$RID"
    fi
    local LITE_SIZE=$(du -h "$LITE_PKG" | cut -f1)
    echo "✅ Created Lite Package: $LITE_PKG ($LITE_SIZE)"

    # 2. Full Standalone Package (With GGUF Model)
    if [ -f "$MODEL_FILE" ]; then
        echo "--> Copying Qwen 2.5 3B GGUF model into $RID publish output..."
        cp "$MODEL_FILE" "$PUBLISH_DIR/Models/"

        local FULL_PKG="$RELEASES_DIR/Simulacra-v1.0-Full-$RID.$EXT"
        echo "--> Creating Full Standalone package: $FULL_PKG"
        if [ "$EXT" = "zip" ]; then
            (cd "$ROOT_DIR/publish" && python3 -m zipfile -c "$FULL_PKG" "$RID")
        else
            tar -czf "$FULL_PKG" -C "$ROOT_DIR/publish" "$RID"
        fi
        local FULL_SIZE=$(du -h "$FULL_PKG" | cut -f1)
        echo "✅ Created Full Standalone Package: $FULL_PKG ($FULL_SIZE)"
    else
        echo "⚠️ Note: GGUF model file not found at $MODEL_FILE. Full package for $RID skipped."
    fi
}

# Build Linux x64 Packages
package_target "linux-x64" "tar.gz"

# Build Windows x64 Packages
package_target "win-x64" "zip"

echo "=================================================="
echo "=== All Release Packages Successfully Generated! ==="
ls -lh "$RELEASES_DIR"
