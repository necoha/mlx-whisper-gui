#!/usr/bin/env bash

# DMG作成スクリプト for MLX Whisper GUI

set -e

APP_NAME="MLX Whisper GUI"
APP_PATH="dist/MLX Whisper GUI.app"
DMG_NAME="MLXWhisperGUI-v1.1.0"
DMG_PATH="${DMG_NAME}.dmg"
VOLUME_NAME="MLX Whisper GUI"
SOURCE_FOLDER="dmg_temp"

# クリーンアップ
echo "🧹 Cleaning up previous builds..."
rm -rf "${SOURCE_FOLDER}"
rm -f "${DMG_PATH}"

# 一時フォルダ作成
echo "📁 Creating temporary DMG folder..."
mkdir -p "${SOURCE_FOLDER}"
mkdir -p "${SOURCE_FOLDER}/.background"

# アプリケーションをコピー
echo "📱 Copying application..."
cp -R "${APP_PATH}" "${SOURCE_FOLDER}/"

# アプリケーションフォルダへのシンボリックリンクを作成
echo "🔗 Creating Applications symlink..."
ln -s /Applications "${SOURCE_FOLDER}/Applications"

# README ファイルを作成
echo "📝 Creating README..."
cat > "${SOURCE_FOLDER}/README.txt" << 'EOF'
MLX Whisper GUI v1.1.0
======================

インストール方法:
1. 「MLX Whisper GUI.app」をアプリケーションフォルダにドラッグ&ドロップ
2. 初回起動時はセキュリティ設定で許可が必要な場合があります

機能:
• 高精度音声転写 (MLX Whisper large-v3)
• バッチ処理対応
• cline統合議事録機能
• VS Code風インターフェース

システム要件:
• macOS 10.15以上
• Apple Silicon (M1/M2/M3) 推奨
• メモリ 8GB以上推奨

お問い合わせ:
github.com/mlx-whisper-gui

EOF

# DMGを作成
echo "💿 Creating DMG..."
hdiutil create -volname "${VOLUME_NAME}" \
               -srcfolder "${SOURCE_FOLDER}" \
               -ov \
               -format UDZO \
               -imagekey zlib-level=9 \
               "${DMG_PATH}"

# 一時フォルダを削除
echo "🧹 Cleaning up temporary files..."
rm -rf "${SOURCE_FOLDER}"

echo "✅ DMG creation completed!"
echo "📦 Output: ${DMG_PATH}"
echo "📏 Size: $(du -h "${DMG_PATH}" | cut -f1)"

# DMGを開いて確認
echo "🔍 Opening DMG for verification..."
open "${DMG_PATH}"