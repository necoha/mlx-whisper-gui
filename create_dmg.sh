#!/bin/bash

# MLX Whisper GUI DMG Creation Script

APP_NAME="MLXWhisperGUI"
APP_PATH="./dist/${APP_NAME}.app"
DMG_NAME="${APP_NAME}"
VOLUME_NAME="${APP_NAME}"
SOURCE_FOLDER="./dmg_temp"
DMG_PATH="./dist/${DMG_NAME}.dmg"

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
    echo "DMG created successfully: $DMG_PATH"
    
    # Clean up temp folder
    rm -rf "$SOURCE_FOLDER"
    
    # Show DMG size
    echo "DMG size: $(du -h "$DMG_PATH" | cut -f1)"
else
    echo "Error creating DMG"
    rm -rf "$SOURCE_FOLDER"
    exit 1
fi