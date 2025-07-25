# MLX Whisper GUI

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