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
import subprocess
import json
import time
import fcntl
import signal
import atexit


class SingleInstanceLock:
    """Advanced single instance lock using multiple mechanisms"""
    def __init__(self, app_name="MLXWhisperGUI"):
        self.app_name = app_name
        self.lock_file_path = None
        self.lock_file_handle = None
        self.socket = None
        self.pid_file_path = None
        
    def acquire_lock(self):
        """Try to acquire the single instance lock using multiple methods"""
        try:
            # Method 1: File-based locking with fcntl (most reliable on Unix)
            if self._try_file_lock():
                # Method 2: Socket-based lock as backup
                if self._try_socket_lock():
                    # Method 3: PID-based verification
                    if self._write_pid_file():
                        # Register cleanup on exit
                        atexit.register(self.release_lock)
                        # Handle signals for clean shutdown
                        signal.signal(signal.SIGTERM, self._signal_handler)
                        signal.signal(signal.SIGINT, self._signal_handler)
                        return True
            
            return False
            
        except Exception as e:
            print(f"Debug: Lock acquisition failed: {e}")
            return False
    
    def _try_file_lock(self):
        """Try to acquire exclusive file lock"""
        try:
            # Create lock directory if it doesn't exist
            if platform.system() == "Darwin":
                # Use ~/Library/Application Support on macOS
                lock_dir = os.path.expanduser("~/Library/Application Support/MLXWhisperGUI")
            else:
                # Use system temp directory on other platforms
                lock_dir = tempfile.gettempdir()
            
            os.makedirs(lock_dir, exist_ok=True)
            self.lock_file_path = os.path.join(lock_dir, f"{self.app_name}.lock")
            
            # Open file for exclusive access
            self.lock_file_handle = open(self.lock_file_path, 'w')
            
            # Try to acquire exclusive lock (non-blocking)
            fcntl.flock(self.lock_file_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            
            # Write current process info
            self.lock_file_handle.write(f"{os.getpid()}\n{time.time()}\n{self.app_name}")
            self.lock_file_handle.flush()
            
            return True
            
        except (IOError, OSError) as e:
            # Lock is already held by another process
            if self.lock_file_handle:
                try:
                    self.lock_file_handle.close()
                except:
                    pass
                self.lock_file_handle = None
            return False
    
    def _try_socket_lock(self):
        """Try to acquire socket-based lock as secondary verification"""
        try:
            # Bind to a specific port range for this app
            for port in range(17001, 17010):  # Use app-specific port range
                try:
                    self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    self.socket.bind(('127.0.0.1', port))
                    self.socket.listen(1)
                    return True
                except OSError:
                    if self.socket:
                        self.socket.close()
                        self.socket = None
                    continue
            
            return False
            
        except Exception:
            return False
    
    def _write_pid_file(self):
        """Write PID file for additional verification"""
        try:
            if platform.system() == "Darwin":
                pid_dir = os.path.expanduser("~/Library/Application Support/MLXWhisperGUI")
            else:
                pid_dir = tempfile.gettempdir()
            
            os.makedirs(pid_dir, exist_ok=True)
            self.pid_file_path = os.path.join(pid_dir, f"{self.app_name}.pid")
            
            # Check if PID file exists and process is still running
            if os.path.exists(self.pid_file_path):
                try:
                    with open(self.pid_file_path, 'r') as f:
                        old_pid = int(f.read().strip())
                    
                    # Check if process is still running
                    try:
                        os.kill(old_pid, 0)  # Signal 0 just checks if process exists
                        return False  # Process is still running
                    except (OSError, ProcessLookupError):
                        # Process is dead, remove stale PID file
                        os.remove(self.pid_file_path)
                except (ValueError, IOError):
                    # Invalid PID file, remove it
                    try:
                        os.remove(self.pid_file_path)
                    except:
                        pass
            
            # Write current PID
            with open(self.pid_file_path, 'w') as f:
                f.write(str(os.getpid()))
            
            return True
            
        except Exception:
            return False
    
    def _signal_handler(self, signum, frame):
        """Handle signals for clean shutdown"""
        self.release_lock()
        sys.exit(0)
    
    def release_lock(self):
        """Release all locks"""
        try:
            # Release file lock
            if self.lock_file_handle:
                try:
                    fcntl.flock(self.lock_file_handle.fileno(), fcntl.LOCK_UN)
                    self.lock_file_handle.close()
                except:
                    pass
                self.lock_file_handle = None
            
            # Remove lock file
            if self.lock_file_path and os.path.exists(self.lock_file_path):
                try:
                    os.remove(self.lock_file_path)
                except:
                    pass
            
            # Release socket
            if self.socket:
                try:
                    self.socket.close()
                except:
                    pass
                self.socket = None
            
            # Remove PID file
            if self.pid_file_path and os.path.exists(self.pid_file_path):
                try:
                    os.remove(self.pid_file_path)
                except:
                    pass
                    
        except Exception as e:
            print(f"Debug: Lock release error: {e}")
    
    def is_another_instance_running(self):
        """Check if another instance is already running"""
        try:
            # Quick check using socket
            test_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            test_socket.settimeout(0.5)
            
            for port in range(17001, 17010):
                try:
                    result = test_socket.connect_ex(('127.0.0.1', port))
                    if result == 0:
                        test_socket.close()
                        return True
                except:
                    continue
            
            test_socket.close()
            return False
            
        except:
            return False


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
        self.audio_duration = 0  # Duration in seconds
        self.transcription_start_time = 0  # Start time for ETA calculation
        self.eta_history = []  # Store ETA calculations for smoothing
        self.processing_stage = "idle"  # Track current processing stage
        
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
        
        # Progress bar with label
        progress_frame = ttk.Frame(main_frame)
        progress_frame.grid(row=4, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(10, 5))
        progress_frame.columnconfigure(0, weight=1)
        
        self.progress_label = ttk.Label(progress_frame, text="")
        self.progress_label.grid(row=0, column=0, sticky=tk.W, pady=(0, 2))
        
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(progress_frame, variable=self.progress_var, maximum=100)
        self.progress_bar.grid(row=1, column=0, sticky=(tk.W, tk.E))
        
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
            # Get audio duration
            duration = self.get_audio_duration(filename)
            self.audio_duration = duration
            if duration > 0:
                duration_str = f"{duration//60}:{duration%60:02d}"
                self.status_var.set(f"Selected: {os.path.basename(filename)} ({duration_str})")
            else:
                self.status_var.set(f"Selected: {os.path.basename(filename)}")
    
    def get_audio_duration(self, file_path):
        """Get audio file duration in seconds using ffprobe"""
        try:
            # Try to find ffprobe in bundled app first
            ffprobe_cmd = "ffprobe"
            if getattr(sys, 'frozen', False):
                # Running in PyInstaller bundle
                bundle_dir = sys._MEIPASS
                ffprobe_path = os.path.join(bundle_dir, 'ffprobe')
                if os.path.exists(ffprobe_path):
                    ffprobe_cmd = ffprobe_path
                else:
                    # Try the Resources directory
                    resources_dir = os.path.join(os.path.dirname(sys.executable), '..', 'Resources')
                    ffprobe_path = os.path.join(resources_dir, 'ffprobe')
                    if os.path.exists(ffprobe_path):
                        ffprobe_cmd = ffprobe_path
            
            # Use ffprobe to get audio duration
            cmd = [
                ffprobe_cmd, "-v", "quiet", "-print_format", "json", 
                "-show_format", file_path
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                data = json.loads(result.stdout)
                duration = float(data['format']['duration'])
                return int(duration)
        except Exception as e:
            print(f"Debug: ffprobe error: {e}")
        return 0
    
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
        
        # Always use determinate progress with manual updates
        self.progress_bar.config(mode="determinate")
        self.progress_var.set(0)
        if self.audio_duration > 0:
            duration_str = f"{self.audio_duration//60}:{self.audio_duration%60:02d}"
            self.progress_label.config(text=f"Initializing transcription... ({duration_str} audio)")
        else:
            self.progress_label.config(text="Initializing transcription...")
        self.status_var.set("Loading MLX model...")
        
        # Start transcription in separate thread
        thread = threading.Thread(target=self.transcribe_audio, daemon=True)
        thread.start()
    
    def calculate_smooth_eta(self, current_eta):
        """Calculate smoothed ETA to reduce fluctuations"""
        self.eta_history.append(current_eta)
        # Keep only last 5 ETA calculations for smoothing
        if len(self.eta_history) > 5:
            self.eta_history.pop(0)
        
        # Return median of recent ETAs for stability
        if len(self.eta_history) >= 3:
            sorted_etas = sorted(self.eta_history)
            return sorted_etas[len(sorted_etas) // 2]
        else:
            return current_eta

    def update_progress_simulation(self, stage, progress=0, elapsed_real_time=0):
        """Enhanced progress updates with accurate ETA calculation"""
        if not self.is_processing:
            return
        
        self.processing_stage = stage
            
        if stage == "loading":
            self.progress_var.set(5)
            self.progress_label.config(text="Loading MLX Whisper model...")
            self.eta_history.clear()
        elif stage == "processing":
            if self.audio_duration > 0:
                # With audio duration - show detailed progress with smart ETA
                base_progress = 5 + (progress * 90)  # 5% to 95%
                self.progress_var.set(min(base_progress, 90))
                
                elapsed = int(progress * self.audio_duration)
                elapsed_str = f"{elapsed//60}:{elapsed%60:02d}"
                duration_str = f"{self.audio_duration//60}:{self.audio_duration%60:02d}"
                
                # Enhanced ETA calculation
                eta_str = ""
                if progress > 0.05 and elapsed_real_time > 5:  # Wait for meaningful data
                    # MLX Whisper typically processes at 2-4x realtime on Apple Silicon
                    # Adjust based on actual performance
                    if progress < 0.5:
                        # Early stage: conservative estimate (1.5x realtime)
                        estimated_speed_factor = 1.5
                    else:
                        # Later stage: more optimistic (2.5x realtime)
                        estimated_speed_factor = 2.5
                    
                    # Calculate remaining audio time
                    remaining_audio = self.audio_duration * (1 - progress)
                    estimated_remaining_time = remaining_audio / estimated_speed_factor
                    
                    # Smooth the ETA to reduce jitter
                    smooth_eta = self.calculate_smooth_eta(estimated_remaining_time)
                    
                    if smooth_eta > 0:
                        eta_minutes = int(smooth_eta // 60)
                        eta_seconds = int(smooth_eta % 60)
                        eta_str = f" (ETA: {eta_minutes}:{eta_seconds:02d})"
                
                progress_percent = int(base_progress)
                self.progress_label.config(text=f"Processing audio... {elapsed_str}/{duration_str} ({progress_percent}%){eta_str}")
            else:
                # Without audio duration - show basic progress with elapsed time
                base_progress = 5 + (progress * 90)
                self.progress_var.set(min(base_progress, 90))
                
                eta_str = ""
                if elapsed_real_time > 10:  # After 10 seconds, show rough ETA
                    # Estimate based on typical processing patterns
                    if progress > 0.1:
                        estimated_total = elapsed_real_time / progress
                        remaining = max(0, estimated_total - elapsed_real_time)
                        eta_minutes = int(remaining // 60)
                        eta_seconds = int(remaining % 60)
                        eta_str = f" (ETA: ~{eta_minutes}:{eta_seconds:02d})"
                
                elapsed_minutes = int(elapsed_real_time // 60)
                elapsed_seconds = int(elapsed_real_time % 60)
                progress_percent = int(base_progress)
                self.progress_label.config(text=f"Processing audio... {elapsed_minutes}:{elapsed_seconds:02d} elapsed ({progress_percent}%){eta_str}")
        elif stage == "finalizing":
            self.progress_var.set(98)
            self.progress_label.config(text="Finalizing transcript... (almost done!)")
    
    def transcribe_audio(self):
        """Perform audio transcription using MLX Whisper"""
        try:
            model_name = self.model_var.get()
            language = self.language_var.get() if self.language_var.get() != "auto" else None
            
            # Load MLX model
            self.root.after(0, lambda: self.status_var.set(f"Loading {model_name} model..."))
            self.root.after(0, lambda: self.update_progress_simulation("loading"))
            
            # Use MLX Whisper large-v3 for highest accuracy
            mlx_model_name = "mlx-community/whisper-large-v3-mlx"
            self.root.after(0, lambda: self.status_var.set("Transcribing audio with MLX..."))
            
            # Simulate progress during transcription
            import time
            start_time = time.time()
            self.transcription_start_time = start_time
            
            # Start enhanced progress tracking thread
            def progress_updater():
                last_update = 0
                while self.is_processing:
                    elapsed = time.time() - start_time
                    
                    if self.audio_duration > 0:
                        # More realistic progress estimation for MLX Whisper
                        # MLX is typically 2-4x faster than realtime
                        if elapsed < 10:
                            # Initial loading phase
                            estimated_progress = min(elapsed / 10.0 * 0.1, 0.1)
                        else:
                            # Processing phase: assume 2.5x realtime average
                            processing_elapsed = elapsed - 10
                            estimated_audio_processed = processing_elapsed * 2.5
                            estimated_progress = 0.1 + min(estimated_audio_processed / self.audio_duration * 0.8, 0.8)
                    else:
                        # Without audio duration, use adaptive curve
                        if elapsed < 20:
                            estimated_progress = elapsed / 20.0 * 0.5
                        else:
                            # Slower progress after 20 seconds
                            estimated_progress = 0.5 + min((elapsed - 20) / 40.0 * 0.4, 0.4)
                    
                    # Update every 2 seconds or when progress changes significantly
                    current_time = time.time()
                    if (current_time - last_update >= 2) or abs(estimated_progress - getattr(self, '_last_progress', 0)) > 0.05:
                        self.root.after(0, lambda p=estimated_progress, e=elapsed: 
                            self.update_progress_simulation("processing", p, e))
                        last_update = current_time
                        self._last_progress = estimated_progress
                    
                    time.sleep(0.5)  # More frequent checks but less frequent updates
            
            progress_thread = threading.Thread(target=progress_updater, daemon=True)
            progress_thread.start()
            
            result = mlx_whisper.transcribe(
                self.selected_file.get(),
                path_or_hf_repo=mlx_model_name,
                language=language
            )
            
            # Finalizing
            self.root.after(0, lambda: self.update_progress_simulation("finalizing"))
            
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
        self.progress_var.set(100)
        
        # Calculate actual processing time
        if hasattr(self, 'transcription_start_time') and self.transcription_start_time > 0:
            total_time = time.time() - self.transcription_start_time
            time_minutes = int(total_time // 60)
            time_seconds = int(total_time % 60)
            if self.audio_duration > 0:
                speed_factor = self.audio_duration / total_time
                self.progress_label.config(text=f"Completed in {time_minutes}:{time_seconds:02d} ({speed_factor:.1f}x realtime)")
            else:
                self.progress_label.config(text=f"Completed in {time_minutes}:{time_seconds:02d}")
        else:
            self.progress_label.config(text="Transcription completed")
        
        # Clear progress after 5 seconds
        self.root.after(5000, lambda: (
            self.progress_var.set(0),
            self.progress_label.config(text="")
        ))
        
        # Clear ETA history for next transcription
        self.eta_history.clear()
        self.processing_stage = "idle"
    
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
        self.progress_label.config(text="Starting batch processing...")
        
        # Start batch processing in separate thread
        thread = threading.Thread(target=self.process_batch_files, daemon=True)
        thread.start()
    
    def process_batch_files(self):
        """Process multiple files in batch"""
        try:
            import time
            batch_start_time = time.time()
            total_files = len(self.batch_files)
            all_transcripts = []
            
            for i, file_path in enumerate(self.batch_files):
                if not self.is_processing:  # Check if cancelled
                    break
                
                # Update progress with ETA
                progress = (i / total_files) * 100
                self.root.after(0, lambda p=progress: self.progress_var.set(p))
                
                filename = os.path.basename(file_path)
                
                # Calculate ETA for batch processing
                if i > 0:
                    elapsed = time.time() - batch_start_time
                    avg_time_per_file = elapsed / i
                    remaining_files = total_files - i
                    eta_seconds = int(avg_time_per_file * remaining_files)
                    eta_minutes = eta_seconds // 60
                    eta_seconds = eta_seconds % 60
                    eta_str = f" (ETA: {eta_minutes}:{eta_seconds:02d})"
                else:
                    eta_str = ""
                
                self.root.after(0, lambda f=filename, i=i, t=total_files, eta=eta_str: 
                    self.progress_label.config(text=f"Processing file {i+1}/{t}: {f}{eta}"))
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
        self.progress_label.config(text="Batch processing completed")
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
    
    def bring_to_front(self):
        """Bring the application window to front"""
        try:
            self.root.lift()
            self.root.attributes('-topmost', True)
            self.root.after_idle(self.root.attributes, '-topmost', False)
            self.root.focus_force()
            
            # Flash the dock icon on macOS
            if platform.system() == "Darwin":
                try:
                    # Try to use osascript to bounce the dock icon
                    subprocess.run(['osascript', '-e', 
                        'tell application "System Events" to set frontmost of process "MLXWhisperGUI" to true'], 
                        capture_output=True, timeout=2)
                except:
                    pass
        except Exception:
            pass
    
    def run(self):
        """Start the GUI application"""
        # Check for single instance
        if not self.instance_lock.acquire_lock():
            # Try to bring existing instance to front
            self._try_focus_existing_instance()
            
            # Show user-friendly message
            response = messagebox.askquestion(
                "MLX Whisper GUI Already Running", 
                "MLX Whisper GUI is already running.\n\n"
                "Only one instance can run at a time for optimal performance.\n\n"
                "Would you like to close this window and use the existing instance?",
                icon='info'
            )
            
            if response == 'yes':
                self.root.destroy()
                return False
            else:
                # User chose to keep trying, destroy current instance anyway
                self.root.destroy()
                return False
        
        try:
            # Bring window to front on startup
            self.root.after(100, self.bring_to_front)
            self.root.mainloop()
        finally:
            self.instance_lock.release_lock()
        
        return True
    
    def _try_focus_existing_instance(self):
        """Try to focus the existing instance"""
        try:
            if platform.system() == "Darwin":
                # Try to activate the existing MLX Whisper GUI process
                subprocess.run([
                    'osascript', '-e',
                    'tell application "System Events" to tell process "MLXWhisperGUI" to set frontmost to true'
                ], capture_output=True, timeout=2)
        except Exception:
            pass


def main():
    """Main entry point with crash recovery"""
    # Setup FFmpeg path for bundled app
    setup_ffmpeg_path()
    
    # Clean up any stale lock files from previous crashes
    try:
        temp_lock = SingleInstanceLock()
        # Check if there are stale locks without acquiring them
        if platform.system() == "Darwin":
            lock_dir = os.path.expanduser("~/Library/Application Support/MLXWhisperGUI")
            if os.path.exists(lock_dir):
                for file in os.listdir(lock_dir):
                    if file.endswith('.lock') or file.endswith('.pid'):
                        file_path = os.path.join(lock_dir, file)
                        try:
                            # Check if file is older than 1 hour (likely stale)
                            if os.path.getmtime(file_path) < time.time() - 3600:
                                os.remove(file_path)
                        except:
                            pass
    except Exception:
        pass
    
    # Create and run the application
    try:
        app = WhisperGUI()
        success = app.run()
        
        if not success:
            # Application didn't start (likely due to another instance)
            return
            
    except Exception as e:
        # Handle unexpected crashes
        import traceback
        error_msg = f"An unexpected error occurred:\n\n{str(e)}\n\nTraceback:\n{traceback.format_exc()}"
        
        try:
            # Try to show error dialog
            root = tk.Tk()
            root.withdraw()  # Hide main window
            messagebox.showerror("MLX Whisper GUI - Fatal Error", error_msg)
            root.destroy()
        except:
            # If GUI fails, print to console
            print(f"MLX Whisper GUI Fatal Error: {error_msg}")
        
        # Clean up any locks
        try:
            temp_lock = SingleInstanceLock()
            temp_lock.release_lock()
        except:
            pass


if __name__ == "__main__":
    main()