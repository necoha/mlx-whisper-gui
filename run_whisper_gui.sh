#!/bin/bash

# Whisper GUI起動スクリプト
# このスクリプトはWhisper GUIアプリケーションを起動します

# スクリプトのディレクトリに移動
cd "$(dirname "$0")"

# 仮想環境をアクティベート
if [ -d "venv" ]; then
    echo "仮想環境をアクティベート中..."
    source venv/bin/activate
else
    echo "エラー: 仮想環境が見つかりません。"
    echo "先に 'python3 -m venv venv' でvenvを作成し、"
    echo "'pip install mlx-whisper pyaudio' で必要なパッケージをインストールしてください。"
    exit 1
fi

# 必要なパッケージが存在するかチェック
python -c "import mlx_whisper, pyaudio" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "エラー: 必要なパッケージが不足しています。"
    echo "以下のコマンドでインストールしてください:"
    echo "pip install mlx-whisper pyaudio"
    exit 1
fi

echo "Whisper GUI を起動中..."
echo "マイク使用許可のダイアログが表示される場合があります。"

# GUIアプリケーション起動
python whisper_gui.py