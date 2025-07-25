# MLX Whisper GUI

[🇺🇸 **English**](#english) | [🇯🇵 **日本語**](#japanese)

---

## English

A sophisticated graphical interface for MLX Whisper transcription on Apple Silicon Macs with advanced progress tracking and ETA estimation.

## Features

### Core Functionality
- **High Accuracy**: Uses MLX Whisper large-v3 model for optimal transcription quality
- **Smart Progress Tracking**: Real-time progress bar with ETA estimation
- **Batch Processing**: Process multiple audio files simultaneously
- **Auto-save**: Automatic transcript saving with original filename
- **Single Instance**: Prevents multiple app instances for resource efficiency

### Advanced Progress System
- **Intelligent ETA Calculation**: Adapts to MLX Whisper's 2-4x realtime processing speed
- **Smooth Progress Updates**: Anti-jitter algorithm for stable progress display
- **Processing Speed Display**: Shows completion time and realtime factor
- **Stage Tracking**: Clear indication of loading, processing, and finalizing phases

### User Experience
- **Audio Duration Detection**: Displays file length using ffprobe
- **Drag-and-drop Interface**: Easy file selection
- **Language Auto-detection**: Supports 10+ languages with auto-detection
- **Real-time Status Updates**: Detailed processing information

## Requirements

- **Hardware**: Apple Silicon Mac (M1/M2/M3/M4)
- **OS**: macOS 12.0+ (Monterey or later)
- **Dependencies**: All included in DMG distribution

## Installation

### Option 1: DMG Distribution (Recommended)
1. Download `MLXWhisperGUI.dmg` from releases
2. Double-click to mount the disk image
3. Drag `MLXWhisperGUI.app` to Applications folder
4. Launch from Applications or Spotlight

### Option 2: From Source
```bash
# Clone repository
git clone https://github.com/yourusername/mlx-whisper-gui.git
cd mlx-whisper-gui

# Create virtual environment
python3 -m venv whisper-gui
source whisper-gui/bin/activate

# Install dependencies
pip install mlx-whisper

# Run application
python whisper_gui.py
```

## Usage

### Basic Transcription
1. **Select File**: Click "Browse" or drag audio file to select
2. **Choose Settings**: Select language (auto-detect recommended)
3. **Start Processing**: Click "Transcribe" to begin
4. **Monitor Progress**: Watch real-time progress with ETA
5. **Review Results**: Transcript appears automatically when complete

### Batch Processing
1. Click "🗋 Batch" button
2. Select multiple audio files
3. Confirm processing in dialog
4. Monitor batch progress with file-by-file ETA
5. All transcripts saved automatically

### Progress Information
- **With Audio Duration**: `"Processing audio... 2:30/5:00 (45%) (ETA: 1:23)"`
- **Without Duration**: `"Processing audio... 1:30 elapsed (60%) (ETA: ~2:15)"`
- **Completion**: `"Completed in 2:34 (1.9x realtime)"`

## Supported Formats

### Audio Files
- **Lossless**: WAV, FLAC
- **Compressed**: MP3, M4A, OGG, WMA
- **Professional**: AIFF, AU

### Video Files (Audio Track)
- **Standard**: MP4, AVI, MOV, MKV
- **Streaming**: WebM, FLV

## Technical Details

### MLX Optimization
- Utilizes Apple's MLX framework for maximum Apple Silicon performance
- Automatic GPU acceleration on supported hardware
- Memory-efficient processing for large audio files

### Progress Algorithm
- **Early Stage**: Conservative 1.5x realtime estimate
- **Later Stage**: Optimistic 2.5x realtime estimate
- **ETA Smoothing**: Median of last 5 calculations
- **Update Frequency**: Every 2 seconds or 5% progress change

## Building from Source

### Requirements
```bash
pip install pyinstaller mlx-whisper
```

### Build Process
```bash
# Build application bundle
pyinstaller MLXWhisperGUI.spec

# Create DMG distribution
./create_dmg.sh
```

## Troubleshooting

### Common Issues
- **No Progress Display**: Ensure ffprobe is available in system PATH
- **Slow Processing**: Check available memory and close other applications
- **Audio Not Detected**: Verify file format is supported

### Performance Tips
- Use WAV or FLAC for fastest processing
- Close unnecessary applications to free memory
- Shorter audio files (< 30 minutes) process more efficiently

## Contributing

Contributions welcome! Please feel free to submit pull requests or open issues for bugs and feature requests.

## License

MIT License - see LICENSE file for details.

## Acknowledgments

- [MLX Whisper](https://github.com/ml-explore/mlx-whisper) - Apple MLX implementation
- [OpenAI Whisper](https://github.com/openai/whisper) - Original Whisper model
- Apple MLX Team - Framework development

---

## Japanese

高精度な進捗追跡とETA予測機能を備えた、Apple Silicon Mac専用の高度なMLX Whisper転写GUIアプリケーションです。

## 機能

### コア機能
- **高精度**: 最適な転写品質のためのMLX Whisper large-v3モデル
- **スマート進捗追跡**: ETA予測付きリアルタイム進捗バー
- **バッチ処理**: 複数の音声ファイルを同時処理
- **自動保存**: 元ファイル名での転写結果自動保存
- **シングルインスタンス**: リソース効率のため複数アプリ起動を防止

### 高度な進捗システム
- **インテリジェントETA計算**: MLX Whisperの2-4倍速リアルタイム処理速度に適応
- **スムースな進捗更新**: 安定した進捗表示のためのアンチジッターアルゴリズム
- **処理速度表示**: 完了時間とリアルタイム係数の表示
- **段階追跡**: 読み込み、処理、仕上げ段階の明確な表示

### ユーザー体験
- **音声長検出**: ffprobeを使用したファイル長表示
- **ドラッグ&ドロップインターフェース**: 簡単なファイル選択
- **言語自動検出**: 自動検出対応の10以上の言語サポート
- **リアルタイムステータス更新**: 詳細な処理情報

## 必要環境

- **ハードウェア**: Apple Silicon Mac (M1/M2/M3/M4)
- **OS**: macOS 12.0以降 (Monterey以降)
- **依存関係**: DMG配布版にすべて含まれています

## インストール

### オプション1: DMG配布版（推奨）
1. リリースから `MLXWhisperGUI.dmg` をダウンロード
2. ディスクイメージをダブルクリックしてマウント
3. `MLXWhisperGUI.app` をApplicationsフォルダにドラッグ
4. ApplicationsまたはSpotlightから起動

### オプション2: ソースから
```bash
# リポジトリをクローン
git clone https://github.com/necoha/mlx-whisper-gui.git
cd mlx-whisper-gui

# 仮想環境を作成
python3 -m venv whisper-gui
source whisper-gui/bin/activate

# 依存関係をインストール
pip install mlx-whisper

# アプリケーションを実行
python whisper_gui.py
```

## 使用方法

### 基本転写
1. **ファイル選択**: "Browse"をクリックまたは音声ファイルをドラッグして選択
2. **設定選択**: 言語を選択（自動検出推奨）
3. **処理開始**: "Transcribe"をクリックして開始
4. **進捗監視**: ETAとリアルタイム進捗を確認
5. **結果確認**: 完了時に転写結果が自動表示

### バッチ処理
1. "🗋 Batch"ボタンをクリック
2. 複数の音声ファイルを選択
3. ダイアログで処理を確認
4. ファイル別ETAでバッチ進捗を監視
5. すべての転写結果が自動保存

### 進捗情報
- **音声長あり**: `"Processing audio... 2:30/5:00 (45%) (ETA: 1:23)"`
- **音声長なし**: `"Processing audio... 1:30 elapsed (60%) (ETA: ~2:15)"`
- **完了時**: `"Completed in 2:34 (1.9x realtime)"`

## 対応形式

### 音声ファイル
- **ロスレス**: WAV, FLAC
- **圧縮**: MP3, M4A, OGG, WMA
- **プロフェッショナル**: AIFF, AU

### 動画ファイル（音声トラック）
- **標準**: MP4, AVI, MOV, MKV
- **ストリーミング**: WebM, FLV

## 技術詳細

### MLX最適化
- 最大Apple Silicon性能のためのApple MLXフレームワーク活用
- サポートハードウェアでの自動GPU加速
- 大きな音声ファイルのメモリ効率的処理

### 進捗アルゴリズム
- **初期段階**: 保守的1.5倍速リアルタイム予測
- **後期段階**: 楽観的2.5倍速リアルタイム予測
- **ETAスムージング**: 過去5回計算の中央値
- **更新頻度**: 2秒毎または5%進捗変化時

## ソースからビルド

### 必要条件
```bash
pip install pyinstaller mlx-whisper
```

### ビルドプロセス
```bash
# アプリケーションバンドルをビルド
pyinstaller MLXWhisperGUI.spec

# DMG配布版を作成
./create_dmg.sh
```

## トラブルシューティング

### よくある問題
- **進捗表示なし**: システムPATHでffprobeが利用可能か確認
- **処理が遅い**: 利用可能メモリを確認し他のアプリケーションを終了
- **音声検出されない**: サポートされているファイル形式か確認

### パフォーマンスのヒント
- 最速処理にはWAVまたはFLACを使用
- メモリ解放のため不要なアプリケーションを終了
- 短い音声ファイル（30分未満）の方が効率的に処理

## 貢献

貢献を歓迎します！バグレポートや機能要求のためのプルリクエストやissueの開設をお気軽にどうぞ。

## ライセンス

MIT License - 詳細はLICENSEファイルを参照してください。

## 謝辞

- [MLX Whisper](https://github.com/ml-explore/mlx-whisper) - Apple MLX実装
- [OpenAI Whisper](https://github.com/openai/whisper) - オリジナルWhisperモデル
- Apple MLXチーム - フレームワーク開発