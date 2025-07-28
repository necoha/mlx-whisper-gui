#!/bin/bash

# MLX Whisper GUI DMG Creation Script

APP_NAME="MLXWhisperGUI"
APP_PATH="./dist/${APP_NAME}.app"
DMG_NAME="${APP_NAME}"
VOLUME_NAME="${APP_NAME}"
SOURCE_FOLDER="./dmg_temp"
DMG_PATH="./dist/${DMG_NAME}.dmg"

# コード署名設定（オプション）
CODESIGN_IDENTITY="${CODESIGN_IDENTITY:-}"
ENABLE_HARDENED_RUNTIME="${ENABLE_HARDENED_RUNTIME:-true}"

# Check if app exists
if [ ! -d "$APP_PATH" ]; then
    echo "Error: App bundle not found at $APP_PATH"
    echo "Please build the app first using PyInstaller"
    exit 1
fi

# Clean up any previous temp folder
rm -rf "$SOURCE_FOLDER"

# Create temporary folder for DMG contents
mkdir -p "$SOURCE_FOLDER"

# Copy app to temp folder
cp -R "$APP_PATH" "$SOURCE_FOLDER/"

# コード署名（署名IDが設定されている場合のみ）
if [ ! -z "$CODESIGN_IDENTITY" ]; then
    echo "Code signing app bundle..."
    if [ "$ENABLE_HARDENED_RUNTIME" = "true" ]; then
        codesign --force --verify --verbose --sign "$CODESIGN_IDENTITY" \
                 --options runtime \
                 --entitlements entitlements.plist \
                 "$SOURCE_FOLDER/$APP_NAME.app"
    else
        codesign --force --verify --verbose --sign "$CODESIGN_IDENTITY" \
                 "$SOURCE_FOLDER/$APP_NAME.app"
    fi
    
    if [ $? -eq 0 ]; then
        echo "✅ Code signing completed"
    else
        echo "⚠️  Code signing failed, continuing without signature"
    fi
else
    echo "⚠️  No code signing identity provided - app will show security warnings"
    echo "   To enable code signing, set CODESIGN_IDENTITY environment variable"
    echo "   Example: export CODESIGN_IDENTITY='Developer ID Application: Your Name'"
fi

# Create Applications symlink for easy drag-and-drop installation
ln -s /Applications "$SOURCE_FOLDER/Applications"

# Remove any existing DMG
rm -f "$DMG_PATH"

echo "Creating DMG..."

# Create DMG with nice layout
hdiutil create -volname "$VOLUME_NAME" \
               -srcfolder "$SOURCE_FOLDER" \
               -ov \
               -format UDZO \
               -imagekey zlib-level=9 \
               "$DMG_PATH"

if [ $? -eq 0 ]; then
    echo "✅ DMG created successfully: $DMG_PATH"
    
    # DMGにもコード署名を適用（署名IDが設定されている場合）
    if [ ! -z "$CODESIGN_IDENTITY" ]; then
        echo "Code signing DMG..."
        codesign --force --sign "$CODESIGN_IDENTITY" "$DMG_PATH"
        if [ $? -eq 0 ]; then
            echo "✅ DMG code signing completed"
        else
            echo "⚠️  DMG code signing failed"
        fi
    fi
    
    # Clean up temp folder
    rm -rf "$SOURCE_FOLDER"
    
    # Show DMG size
    echo "📦 DMG size: $(du -h "$DMG_PATH" | cut -f1)"
    
    echo ""
    echo "🚀 Installation instructions:"
    echo "   1. Double-click the DMG to mount it"
    echo "   2. Drag the app to Applications folder"
    echo "   3. On first launch, you may need to:"
    echo "      - Right-click the app and select 'Open'"
    echo "      - Or go to System Preferences > Security & Privacy"
    echo "      - Or run: xattr -dr com.apple.quarantine '/Applications/$APP_NAME.app'"
    
else
    echo "❌ Error creating DMG"
    rm -rf "$SOURCE_FOLDER"
    exit 1
fi