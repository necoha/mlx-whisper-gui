#!/usr/bin/env python3
"""
Whisper GUI - A simple graphical interface for MLX Whisper
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import threading
import os
import sys
import mlx_whisper
from pathlib import Path
import platform
from datetime import datetime
import socket
import tempfile


class SingleInstanceLock:
    """Prevents multiple instances of the application from running"""
    def __init__(self, app_name="MLXWhisperGUI"):
        self.app_name = app_name
        self.lock_file = None
        self.socket = None
        
    def acquire_lock(self):
        """Try to acquire the single instance lock"""
        try:
            # Try socket-based approach first
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.bind(('127.0.0.1', 0))  # Bind to any available port
            port = self.socket.getsockname()[1]
            
            # Store port in temp file for other instances to check
            temp_dir = tempfile.gettempdir()
            self.lock_file = os.path.join(temp_dir, f"{self.app_name}_port.lock")
            
            # Check if another instance is already running
            if os.path.exists(self.lock_file):
                with open(self.lock_file, 'r') as f:
                    try:
                        existing_port = int(f.read().strip())
                        # Test if the port is still in use
                        test_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        test_socket.settimeout(1)
                        result = test_socket.connect_ex(('127.0.0.1', existing_port))
                        test_socket.close()
                        if result == 0:
                            return False  # Another instance is running
                    except (ValueError, ConnectionRefusedError):
                        pass  # Lock file is stale
            
            # Write our port to the lock file
            with open(self.lock_file, 'w') as f:
                f.write(str(port))
            
            return True
            
        except Exception:
            return False
    
    def release_lock(self):
        """Release the single instance lock"""
        try:
            if self.socket:
                self.socket.close()
            if self.lock_file and os.path.exists(self.lock_file):
                os.remove(self.lock_file)
        except Exception:
            pass


def setup_ffmpeg_path():
    """Setup FFmpeg path for PyInstaller bundle"""
    if getattr(sys, 'frozen', False):
        # Running in PyInstaller bundle
        bundle_dir = sys._MEIPASS
        ffmpeg_path = os.path.join(bundle_dir, 'ffmpeg')
        if os.path.exists(ffmpeg_path):
            # Add bundle directory to PATH so ffmpeg can be found
            current_path = os.environ.get('PATH', '')
            if bundle_dir not in current_path:
                os.environ['PATH'] = bundle_dir + os.pathsep + current_path
            
            # Set DYLD_LIBRARY_PATH for libav libraries
            current_dyld_path = os.environ.get('DYLD_LIBRARY_PATH', '')
            if bundle_dir not in current_dyld_path:
                os.environ['DYLD_LIBRARY_PATH'] = bundle_dir + os.pathsep + current_dyld_path
            
            # Set FFMPEG_BINARY environment variable for mlx_whisper
            os.environ['FFMPEG_BINARY'] = ffmpeg_path


class WhisperGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("MLX Whisper GUI - Audio Transcription")
        self.root.geometry("800x600")
        self.root.minsize(600, 400)
        
        # Initialize single instance lock
        self.instance_lock = SingleInstanceLock()
        
        # Set up window close handler
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # Variables
        self.selected_file = tk.StringVar()
        self.model_var = tk.StringVar(value="large-v3")
        self.language_var = tk.StringVar(value="auto")
        self.auto_save_var = tk.BooleanVar(value=True)
        self.is_processing = False
        self.batch_files = []
        
        # Available models - MLX large-v3 for highest accuracy
        self.models = ["large-v3"]
        
        # Common languages
        self.languages = {
            "auto": "Auto-detect",
            "en": "English",
            "ja": "Japanese",
            "es": "Spanish",
            "fr": "French",
            "de": "German",
            "it": "Italian",
            "pt": "Portuguese",
            "ru": "Russian",
            "ko": "Korean",
            "zh": "Chinese"
        }
        
        self.create_widgets()
        
    def create_widgets(self):
        # Main frame
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(6, weight=1)
        
        # File selection
        ttk.Label(main_frame, text="Audio File:").grid(row=0, column=0, sticky=tk.W, pady=(0, 5))
        
        file_frame = ttk.Frame(main_frame)
        file_frame.grid(row=0, column=1, sticky=(tk.W, tk.E), pady=(0, 5))
        file_frame.columnconfigure(0, weight=1)
        
        self.file_entry = ttk.Entry(file_frame, textvariable=self.selected_file, state="readonly")
        self.file_entry.grid(row=0, column=0, sticky=(tk.W, tk.E), padx=(0, 5))
        
        ttk.Button(file_frame, text="Browse", command=self.browse_file).grid(row=0, column=1)
        
        # Model selection
        ttk.Label(main_frame, text="Model:").grid(row=1, column=0, sticky=tk.W, pady=(10, 5))
        model_combo = ttk.Combobox(main_frame, textvariable=self.model_var, values=self.models, state="readonly")
        model_combo.grid(row=1, column=1, sticky=(tk.W, tk.E), pady=(10, 5))
        
        # Language selection
        ttk.Label(main_frame, text="Language:").grid(row=2, column=0, sticky=tk.W, pady=(0, 5))
        language_combo = ttk.Combobox(main_frame, textvariable=self.language_var, 
                                    values=list(self.languages.keys()), state="readonly")
        language_combo.grid(row=2, column=1, sticky=(tk.W, tk.E), pady=(0, 5))
        
        # Auto-save option
        auto_save_check = ttk.Checkbutton(main_frame, text="Auto-save transcript to file", 
                                        variable=self.auto_save_var)
        auto_save_check.grid(row=3, column=0, columnspan=2, sticky=tk.W, pady=(5, 5))
        
        # Progress bar
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(main_frame, variable=self.progress_var, maximum=100)
        self.progress_bar.grid(row=4, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(10, 5))
        
        # Buttons frame
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=5, column=0, columnspan=2, pady=(10, 0))
        
        self.transcribe_btn = ttk.Button(button_frame, text="Transcribe", command=self.start_transcription)
        self.transcribe_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        
        self.batch_btn = ttk.Button(button_frame, text="🗋 Batch", command=self.select_batch_files)
        self.batch_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        ttk.Button(button_frame, text="Clear", command=self.clear_results).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(button_frame, text="Save", command=self.save_transcript).pack(side=tk.LEFT)
        
        # Results area
        ttk.Label(main_frame, text="Transcript:").grid(row=6, column=0, sticky=(tk.W, tk.N), pady=(10, 0))
        
        self.result_text = scrolledtext.ScrolledText(main_frame, wrap=tk.WORD, height=15)
        self.result_text.grid(row=6, column=1, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(10, 0))
        
        # Status bar
        self.status_var = tk.StringVar()
        self.status_var.set("Ready - MLX Whisper for Apple Silicon")
        status_bar = ttk.Label(main_frame, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        status_bar.grid(row=7, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(10, 0))
        
    def browse_file(self):
        """Open file browser to select audio file"""
        file_types = [
            ("Audio files", "*.mp3 *.wav *.m4a *.flac *.ogg *.wma *.mp4 *.avi *.mov *.mkv"),
            ("All files", "*.*")
        ]
        
        filename = filedialog.askopenfilename(
            title="Select Audio File",
            filetypes=file_types
        )
        
        if filename:
            self.selected_file.set(filename)
            self.status_var.set(f"Selected: {os.path.basename(filename)}")
    
    def start_transcription(self):
        """Start transcription in a separate thread"""
        if not self.selected_file.get():
            messagebox.showerror("Error", "Please select an audio file first.")
            return
            
        if not os.path.exists(self.selected_file.get()):
            messagebox.showerror("Error", "Selected file does not exist.")
            return
            
        if self.is_processing:
            messagebox.showwarning("Warning", "Transcription is already in progress.")
            return
        
        # Disable buttons and start processing
        self.transcribe_btn.config(state="disabled")
        self.batch_btn.config(state="disabled")
        self.is_processing = True
        self.progress_bar.config(mode="indeterminate")
        self.progress_bar.start()
        self.status_var.set("Loading MLX model...")
        
        # Start transcription in separate thread
        thread = threading.Thread(target=self.transcribe_audio, daemon=True)
        thread.start()
    
    def transcribe_audio(self):
        """Perform audio transcription using MLX Whisper"""
        try:
            model_name = self.model_var.get()
            language = self.language_var.get() if self.language_var.get() != "auto" else None
            
            # Load MLX model
            self.root.after(0, lambda: self.status_var.set(f"Loading {model_name} model..."))
            
            # Use MLX Whisper large-v3 for highest accuracy
            mlx_model_name = "mlx-community/whisper-large-v3-mlx"
            self.root.after(0, lambda: self.status_var.set("Transcribing audio with MLX..."))
            
            result = mlx_whisper.transcribe(
                self.selected_file.get(),
                path_or_hf_repo=mlx_model_name,
                language=language
            )
            
            # Update UI with results
            self.root.after(0, lambda: self.display_results(result))
            
        except Exception as e:
            error_msg = f"Error during transcription: {str(e)}"
            self.root.after(0, lambda: self.show_error(error_msg))
        
        finally:
            # Re-enable UI
            self.root.after(0, self.transcription_complete)
    
    def display_results(self, result):
        """Display transcription results"""
        # Clear previous results
        self.result_text.delete(1.0, tk.END)
        
        # Insert transcript
        transcript = result.get("text", "").strip()
        self.result_text.insert(tk.END, transcript)
        
        # Auto-save if enabled
        if self.auto_save_var.get() and transcript and self.selected_file.get():
            self.auto_save_transcript(transcript, self.selected_file.get())
        
        # Update status
        segments = result.get("segments", [])
        duration = len(segments)
        self.status_var.set(f"Transcription complete using MLX. {duration} segments processed.")
    
    def show_error(self, error_msg):
        """Show error message"""
        messagebox.showerror("Transcription Error", error_msg)
        self.status_var.set("Error occurred during transcription")
    
    def transcription_complete(self):
        """Reset UI after transcription completion"""
        self.is_processing = False
        self.transcribe_btn.config(state="normal")
        self.batch_btn.config(state="normal")
        self.progress_bar.stop()
        self.progress_bar.config(mode="determinate")
        self.progress_var.set(0)
    
    def clear_results(self):
        """Clear transcription results"""
        self.result_text.delete(1.0, tk.END)
        self.status_var.set("Results cleared")
    
    def save_transcript(self):
        """Save transcript to file"""
        content = self.result_text.get(1.0, tk.END).strip()
        
        if not content:
            messagebox.showwarning("Warning", "No transcript to save.")
            return
        
        file_path = filedialog.asksaveasfilename(
            title="Save Transcript",
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                self.status_var.set(f"Transcript saved to {os.path.basename(file_path)}")
                messagebox.showinfo("Success", "Transcript saved successfully!")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save file: {str(e)}")
    
    
    def select_batch_files(self):
        """Select multiple files for batch processing"""
        if self.is_processing:
            messagebox.showwarning("Warning", "Cannot start batch processing while transcription is in progress.")
            return
        
        file_types = [
            ("Audio files", "*.mp3 *.wav *.m4a *.flac *.ogg *.wma *.mp4 *.avi *.mov *.mkv"),
            ("All files", "*.*")
        ]
        
        files = filedialog.askopenfilenames(
            title="Select Audio Files for Batch Processing",
            filetypes=file_types
        )
        
        if files:
            self.batch_files = list(files)
            count = len(self.batch_files)
            self.status_var.set(f"Selected {count} files for batch processing")
            
            # Show confirmation dialog
            file_list = "\n".join([os.path.basename(f) for f in self.batch_files[:10]])
            if count > 10:
                file_list += f"\n... and {count-10} more files"
            
            result = messagebox.askyesno(
                "Batch Processing", 
                f"Process {count} files?\n\nFiles:\n{file_list}\n\nThis may take a while."
            )
            
            if result:
                self.start_batch_processing()
            else:
                self.batch_files = []
                self.status_var.set("Batch processing cancelled")
    
    def start_batch_processing(self):
        """Start batch processing in a separate thread"""
        if not self.batch_files:
            return
        
        # Disable buttons
        self.transcribe_btn.config(state="disabled")
        self.batch_btn.config(state="disabled")
        
        self.is_processing = True
        self.progress_bar.config(mode="determinate")
        self.progress_var.set(0)
        
        # Start batch processing in separate thread
        thread = threading.Thread(target=self.process_batch_files, daemon=True)
        thread.start()
    
    def process_batch_files(self):
        """Process multiple files in batch"""
        try:
            total_files = len(self.batch_files)
            all_transcripts = []
            
            for i, file_path in enumerate(self.batch_files):
                if not self.is_processing:  # Check if cancelled
                    break
                
                # Update progress
                progress = (i / total_files) * 100
                self.root.after(0, lambda p=progress: self.progress_var.set(p))
                
                filename = os.path.basename(file_path)
                self.root.after(0, lambda f=filename: self.status_var.set(f"Processing {f}..."))
                
                try:
                    # Transcribe current file using MLX large-v3
                    language = self.language_var.get() if self.language_var.get() != "auto" else None
                    mlx_model_name = "mlx-community/whisper-large-v3-mlx"
                    result = mlx_whisper.transcribe(
                        file_path,
                        path_or_hf_repo=mlx_model_name,
                        language=language
                    )
                    
                    transcript = result.get("text", "").strip()
                    all_transcripts.append(f"=== {filename} ===\n{transcript}\n")
                    
                    # Auto-save individual file if enabled
                    if self.auto_save_var.get() and transcript:
                        self.auto_save_transcript(transcript, file_path)
                    
                except Exception as e:
                    error_msg = f"Error processing {filename}: {str(e)}"
                    all_transcripts.append(f"=== {filename} ===\nERROR: {error_msg}\n")
            
            # Update UI with all results
            combined_text = "\n".join(all_transcripts)
            self.root.after(0, lambda: self.display_batch_results(combined_text, total_files))
            
        except Exception as e:
            error_msg = f"Batch processing error: {str(e)}"
            self.root.after(0, lambda: self.show_error(error_msg))
        
        finally:
            # Re-enable UI
            self.root.after(0, self.batch_processing_complete)
    
    def display_batch_results(self, combined_text, file_count):
        """Display batch processing results"""
        self.result_text.delete(1.0, tk.END)
        self.result_text.insert(tk.END, combined_text)
        
        # Auto-save batch results if enabled
        if self.auto_save_var.get() and combined_text.strip():
            self.auto_save_batch_results(combined_text)
        
        self.status_var.set(f"Batch processing complete. {file_count} files processed.")
    
    def batch_processing_complete(self):
        """Reset UI after batch processing completion"""
        self.is_processing = False
        self.transcribe_btn.config(state="normal")
        self.batch_btn.config(state="normal")
        self.progress_bar.config(mode="determinate")
        self.progress_var.set(100)
        self.batch_files = []
    
    def auto_save_transcript(self, transcript, audio_file_path):
        """Auto-save transcript with same name as audio file"""
        try:
            # Get audio file path without extension
            audio_path = Path(audio_file_path)
            text_file_path = audio_path.with_suffix('.txt')
            
            # Write transcript to text file
            with open(text_file_path, 'w', encoding='utf-8') as f:
                f.write(transcript)
            
            self.status_var.set(f"Transcript auto-saved to {text_file_path.name}")
            
        except Exception as e:
            print(f"Auto-save error: {e}")
            self.status_var.set("Error: Could not auto-save transcript")
    
    def auto_save_batch_results(self, combined_text):
        """Auto-save batch processing results"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            batch_file_path = Path(f"batch_transcripts_{timestamp}.txt")
            
            # Write combined results to text file
            with open(batch_file_path, 'w', encoding='utf-8') as f:
                f.write(combined_text)
            
            self.status_var.set(f"Batch results auto-saved to {batch_file_path.name}")
            
        except Exception as e:
            print(f"Batch auto-save error: {e}")
            self.status_var.set("Error: Could not auto-save batch results")
    
    def on_closing(self):
        """Handle window closing event"""
        self.instance_lock.release_lock()
        self.root.destroy()
    
    def run(self):
        """Start the GUI application"""
        # Check for single instance
        if not self.instance_lock.acquire_lock():
            messagebox.showwarning(
                "Already Running", 
                "MLX Whisper GUI is already running. Only one instance is allowed at a time."
            )
            self.root.destroy()
            return False
        
        try:
            self.root.mainloop()
        finally:
            self.instance_lock.release_lock()
        
        return True


def main():
    """Main entry point"""
    # Setup FFmpeg path for bundled app
    setup_ffmpeg_path()
    
    app = WhisperGUI()
    app.run()


if __name__ == "__main__":
    main()