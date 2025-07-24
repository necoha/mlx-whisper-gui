# MLX Whisper GUI

Apple Silicon専用に最適化されたWhisper音声転写GUIアプリケーション

## 主な機能

### ✨ 新機能
- **🎤 リアルタイム録音**: マイクから直接音声を録音して転写
- **📁 バッチ処理**: 複数の音声ファイルを一括で転写処理
- **⚡ MLX最適化**: Apple Silicon GPUを活用した高速処理

### 基本機能
- 音声ファイルからテキストへの転写
- 複数モデル対応（tiny, base, small, medium, large）
- 多言語対応（自動検出、英語、日本語など）
- 転写結果のテキストファイル保存

## 必要な環境

- **macOS** (Apple Silicon推奨)
- **Python 3.8+**
- **PortAudio** (音声録音用)

## インストール

1. **PortAudioをインストール**:
   ```bash
   brew install portaudio
   ```

2. **仮想環境の作成とアクティベート**:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **必要なパッケージをインストール**:
   ```bash
   pip install mlx-whisper pyaudio
   ```

## 使用方法

### 起動

```bash
./run_whisper_gui.sh
```

または直接：

```bash
source venv/bin/activate
python whisper_gui.py
```

### 機能の使用方法

1. **ファイル転写**: 
   - 「Browse」ボタンで音声ファイルを選択
   - モデルと言語を選択
   - 「Transcribe」ボタンで転写開始

2. **リアルタイム録音**:
   - 「🎤 Record」ボタンで録音開始
   - 「⏹️ Stop」ボタンで録音終了
   - 自動的に転写が開始

3. **バッチ処理**:
   - 「📋 Batch」ボタンで複数ファイル選択
   - 確認ダイアログで「Yes」を選択
   - 全ファイルの転写結果を一括表示

## 対応形式

- **音声ファイル**: MP3, WAV, M4A, FLAC, OGG, WMA
- **動画ファイル**: MP4, AVI, MOV, MKV

## 注意事項

- 初回実行時にマイクへのアクセス許可が求められます
- MLXモデルの初回ダウンロードに時間がかかる場合があります
- Apple Silicon以外のMacでは性能が制限される場合があります

## トラブルシューティング

### PyAudioインストールエラー
```bash
brew install portaudio
pip install pyaudio
```

### MLX Whisperが見つからない
```bash
pip install mlx-whisper
```

### 録音できない
- システム環境設定でマイクのアクセス許可を確認してください
- PortAudioが正しくインストールされているか確認してください