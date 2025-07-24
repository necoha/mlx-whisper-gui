#!/usr/bin/env python3
"""
transcribe.py  – MLX Whisper (Apple Silicon) large-v3 for highest accuracy
"""

import os; os.environ["MLX_PREFER_GPU"] = "1"
from pathlib import Path
import sys
from tqdm import tqdm

# ==== MLX モデル ID - 最高精度のlarge-v3 =============================
MLX_MODEL_ID = "mlx-community/whisper-large-v3-mlx"
# ===========================================================

def load_model():
    """Return MLX Whisper module for highest accuracy."""
    import mlx_whisper as mw           # return the module itself
    return mw

def transcribe_file(model, audio_path: Path):
    """Transcribe one file using MLX Whisper large-v3 and write .txt next to it."""
    text = model.transcribe(
        str(audio_path),
        path_or_hf_repo=MLX_MODEL_ID
    )["text"]

    out = audio_path.with_suffix(".txt")
    out.write_text(text, encoding="utf‑8")
    print(f"✅ {audio_path.name} → {out.name}")

def main():
    # Check if script was launched with a file argument
    direct_file_arg = None
    if len(sys.argv) > 1 and Path(sys.argv[1]).exists():
        file_path = Path(sys.argv[1])
        exts = {".mp3", ".wav", ".m4a", ".flac", ".aifc", ".aiff"}
        if file_path.suffix.lower() in exts:
            direct_file_arg = file_path
            print(f"Processing directly launched file: {direct_file_arg}")
    
    print("Using MLX Whisper large-v3 for highest accuracy...")
    model = load_model()
    
    # If we have a direct file argument, process only that file and skip recordings folder
    if direct_file_arg:
        transcribe_file(model, direct_file_arg)
        return  # Exit function after processing the direct file

    # Only process recordings folder if no direct file was specified
    rec_dir = Path("./recordings")
    if not rec_dir.exists():
        sys.exit("Folder 'recordings' not found.")

    exts = {".mp3", ".wav", ".m4a", ".flac", ".aifc", ".aiff"}
    files = [p for p in rec_dir.iterdir() if p.suffix.lower() in exts]

    if not files:
        sys.exit("No audio files detected.")

    print("\nFiles:")
    for i, f in enumerate(files, 1):
        print(f"{i}: {f.name}")
    print("0: all   C: cancel")

    sel = input("Select file: ").strip().lower()
    if sel == "c":
        sys.exit("Cancelled.")
    try:
        targets = files if sel == "0" else [files[int(sel) - 1]]
    except (ValueError, IndexError):
        sys.exit("Invalid selection.")

    for p in tqdm(targets, desc="Transcribing with MLX large-v3"):
        transcribe_file(model, p)

if __name__ == "__main__":
    # Apple GPU を確実に使いたい場合は
    #   import os; os.environ["MLX_PREFER_GPU"] = "1"
    main()