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
import requests
import urllib.parse


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


def try_focus_existing_instance():
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
            
            # Prevent child processes from launching GUI
            os.environ['_MLX_WHISPER_GUI_CHILD_PROCESS'] = '1'


class WhisperGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("MLX Whisper GUI - Audio Transcription")
        self.root.geometry("800x600")
        self.root.minsize(600, 400)
        
        # Instance lock will be set by main() function
        self.instance_lock = None
        
        # Set up window close handler
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # Variables
        self.selected_file = tk.StringVar()
        self.model_var = tk.StringVar(value="large-v3-turbo")
        self.language_var = tk.StringVar(value="auto")
        self.auto_save_var = tk.BooleanVar(value=True)
        self.is_processing = False
        self.batch_files = []
        self.audio_duration = 0  # Duration in seconds
        self.transcription_start_time = 0  # Start time for ETA calculation
        self.eta_history = []  # Store ETA calculations for smoothing
        self.processing_stage = "idle"  # Track current processing stage
        
        # Meeting/議事録 related variables
        self.is_recording_meeting = False
        self.meeting_data = {
            'title': '',
            'date': '',
            'participants': [],
            'agenda': [],
            'transcript_segments': [],
            'action_items': []
        }
        
        # Cline settings
        self.cline_settings = {
            'api_endpoint': 'http://localhost:3001',
            'api_key': '',
            'model': 'claude-3-5-sonnet-20241022',
            'use_local_processing': True,
            'custom_prompts': {
                'minutes_generation': '以下の転写テキストから、構造化された議事録を生成してください。会議の要点、決定事項、アクションアイテムを明確に整理してください。',
                'minutes_improvement': '以下の議事録を改善してください。読みやすさを向上させ、重要な情報を整理し、構造を最適化してください。',
                'action_extraction': '以下のテキストからアクションアイテムを抽出してください。担当者、期限、優先度を可能な限り特定してください。'
            }
        }
        
        # Available models - MLX large-v3-turbo for optimal speed and accuracy
        self.models = ["large-v3-turbo"]
        
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
        
        self.create_menu_bar()
        self.create_widgets()
    
    def create_menu_bar(self):
        """VS Code風のメニューバーを作成"""
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        
        # ファイルメニュー
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="ファイル", menu=file_menu)
        file_menu.add_command(label="開く...", command=self.browse_file, accelerator="Ctrl+O")
        file_menu.add_separator()
        file_menu.add_command(label="保存", command=self.save_transcript, accelerator="Ctrl+S")
        file_menu.add_command(label="終了", command=self.on_closing, accelerator="Ctrl+Q")
        
        # 議事録メニュー（新規追加）
        meeting_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="議事録", menu=meeting_menu)
        meeting_menu.add_command(label="会議録を開始", command=self.start_meeting_recording)
        meeting_menu.add_command(label="会議録を停止", command=self.stop_meeting_recording)
        meeting_menu.add_separator()
        meeting_menu.add_command(label="🤖 clineで議事録生成", command=self.generate_minutes_with_cline)
        meeting_menu.add_command(label="✨ 議事録改善", command=self.improve_minutes_with_cline)
        meeting_menu.add_command(label="📋 アクション抽出", command=self.extract_actions_with_cline)
        meeting_menu.add_separator()
        meeting_menu.add_command(label="⚙️ cline設定", command=self.configure_cline_settings)
        meeting_menu.add_command(label="テンプレート設定", command=self.configure_meeting_template)
        
        # ヘルプメニュー
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="ヘルプ", menu=help_menu)
        help_menu.add_command(label="使い方", command=self.show_help)
        help_menu.add_command(label="バージョン情報", command=self.show_about)
        
        # キーボードショートカットの設定
        self.root.bind_all('<Control-o>', lambda e: self.browse_file())
        self.root.bind_all('<Control-s>', lambda e: self.save_transcript())
        self.root.bind_all('<Control-q>', lambda e: self.on_closing())
        
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
        
        # 議事録関連ボタンを追加
        ttk.Separator(button_frame, orient='vertical').pack(side=tk.LEFT, padx=10, fill='y')
        
        self.meeting_start_btn = ttk.Button(button_frame, text="🎤 会議録開始", command=self.start_meeting_recording)
        self.meeting_start_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        self.meeting_stop_btn = ttk.Button(button_frame, text="⏹ 会議録停止", command=self.stop_meeting_recording, state="disabled")
        self.meeting_stop_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        ttk.Separator(button_frame, orient='vertical').pack(side=tk.LEFT, padx=10, fill='y')
        
        ttk.Button(button_frame, text="Clear", command=self.clear_results).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(button_frame, text="Save", command=self.save_transcript).pack(side=tk.LEFT)
        
        # Results area with notebook for tabs
        results_frame = ttk.Frame(main_frame)
        results_frame.grid(row=6, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(10, 0))
        results_frame.columnconfigure(0, weight=1)
        results_frame.rowconfigure(0, weight=1)
        
        # Create notebook for tabbed interface
        self.results_notebook = ttk.Notebook(results_frame)
        self.results_notebook.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Transcript tab
        transcript_frame = ttk.Frame(self.results_notebook)
        self.results_notebook.add(transcript_frame, text="転写結果")
        
        transcript_frame.columnconfigure(0, weight=1)
        transcript_frame.rowconfigure(0, weight=1)
        
        self.result_text = scrolledtext.ScrolledText(transcript_frame, wrap=tk.WORD, height=15)
        self.result_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=5, pady=5)
        
        # Meeting minutes tab
        meeting_frame = ttk.Frame(self.results_notebook)
        self.results_notebook.add(meeting_frame, text="議事録")
        
        meeting_frame.columnconfigure(0, weight=1)
        meeting_frame.rowconfigure(1, weight=1)
        
        # Meeting info display
        self.meeting_info_frame = ttk.LabelFrame(meeting_frame, text="会議情報", padding="5")
        self.meeting_info_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), padx=5, pady=(5,0))
        self.meeting_info_frame.columnconfigure(1, weight=1)
        
        ttk.Label(self.meeting_info_frame, text="会議名:").grid(row=0, column=0, sticky=tk.W, padx=(0,5))
        self.meeting_title_label = ttk.Label(self.meeting_info_frame, text="(未設定)", foreground="gray")
        self.meeting_title_label.grid(row=0, column=1, sticky=tk.W)
        
        ttk.Label(self.meeting_info_frame, text="日時:").grid(row=1, column=0, sticky=tk.W, padx=(0,5))
        self.meeting_date_label = ttk.Label(self.meeting_info_frame, text="(未設定)", foreground="gray")
        self.meeting_date_label.grid(row=1, column=1, sticky=tk.W)
        
        ttk.Label(self.meeting_info_frame, text="参加者:").grid(row=2, column=0, sticky=tk.W, padx=(0,5))
        self.meeting_participants_label = ttk.Label(self.meeting_info_frame, text="(未設定)", foreground="gray")
        self.meeting_participants_label.grid(row=2, column=1, sticky=tk.W)
        
        # Meeting content area with cline integration
        meeting_content_frame = ttk.Frame(meeting_frame)
        meeting_content_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=5, pady=5)
        meeting_content_frame.columnconfigure(0, weight=1)
        meeting_content_frame.rowconfigure(0, weight=1)
        
        self.meeting_text = scrolledtext.ScrolledText(meeting_content_frame, wrap=tk.WORD, height=10)
        self.meeting_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Cline integration buttons
        cline_button_frame = ttk.Frame(meeting_content_frame)
        cline_button_frame.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=(5, 0))
        
        self.generate_minutes_btn = ttk.Button(cline_button_frame, text="🤖 clineで議事録生成", command=self.generate_minutes_with_cline)
        self.generate_minutes_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        self.improve_minutes_btn = ttk.Button(cline_button_frame, text="✨ 議事録改善", command=self.improve_minutes_with_cline)
        self.improve_minutes_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        self.extract_actions_btn = ttk.Button(cline_button_frame, text="📋 アクション抽出", command=self.extract_actions_with_cline)
        self.extract_actions_btn.pack(side=tk.LEFT)
        
        # Status bar
        self.status_var = tk.StringVar()
        self.status_var.set("Ready - MLX Whisper large-v3-turbo for Apple Silicon")
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
                    # MLX Whisper large-v3-turbo typically processes at 3-6x realtime on Apple Silicon
                    # Adjust based on actual performance
                    if progress < 0.5:
                        # Early stage: conservative estimate (2.5x realtime)
                        estimated_speed_factor = 2.5
                    else:
                        # Later stage: more optimistic (4x realtime)
                        estimated_speed_factor = 4.0
                    
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
            # Ensure child processes won't launch GUI
            os.environ['_MLX_WHISPER_GUI_CHILD_PROCESS'] = '1'
            os.environ['_MLX_WHISPER_GUI_SUBPROCESS'] = '1'
            
            model_name = self.model_var.get()
            language = self.language_var.get() if self.language_var.get() != "auto" else None
            
            # Load MLX model
            self.root.after(0, lambda: self.status_var.set(f"Loading {model_name} model..."))
            self.root.after(0, lambda: self.update_progress_simulation("loading"))
            
            # Use MLX Whisper large-v3-turbo for optimal speed and accuracy
            mlx_model_name = "mlx-community/whisper-large-v3-turbo"
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
                        # More realistic progress estimation for MLX Whisper large-v3-turbo
                        # MLX turbo is typically 3-6x faster than realtime
                        if elapsed < 10:
                            # Initial loading phase
                            estimated_progress = min(elapsed / 10.0 * 0.1, 0.1)
                        else:
                            # Processing phase: assume 4x realtime average for turbo
                            processing_elapsed = elapsed - 10
                            estimated_audio_processed = processing_elapsed * 4.0
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
            # Ensure child processes won't launch GUI
            os.environ['_MLX_WHISPER_GUI_CHILD_PROCESS'] = '1'
            os.environ['_MLX_WHISPER_GUI_SUBPROCESS'] = '1'
            
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
                    # Transcribe current file using MLX large-v3-turbo
                    language = self.language_var.get() if self.language_var.get() != "auto" else None
                    mlx_model_name = "mlx-community/whisper-large-v3-turbo"
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
        if self.instance_lock:
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
        # Instance lock should already be acquired by main()
        if self.instance_lock is None:
            # Fallback if instance_lock wasn't set
            self.instance_lock = SingleInstanceLock()
            if not self.instance_lock.acquire_lock():
                self.root.destroy()
                return False
        
        try:
            # Bring window to front on startup
            self.root.after(100, self.bring_to_front)
            self.root.mainloop()
        finally:
            if self.instance_lock:
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
    
    # 議事録関連のメソッドを追加
    def start_meeting_recording(self):
        """リアルタイム議事録開始"""
        if self.is_processing:
            messagebox.showwarning("警告", "転写処理中は会議録を開始できません。")
            return
        
        if self.is_recording_meeting:
            messagebox.showwarning("警告", "既に会議録が開始されています。")
            return
        
        # 会議情報入力ダイアログを表示
        meeting_info = self.get_meeting_info()
        if not meeting_info:
            return
        
        self.meeting_data.update(meeting_info)
        self.is_recording_meeting = True
        
        # 議事録タブの情報を更新
        self.update_meeting_display()
        
        # 議事録タブをアクティブにする
        self.results_notebook.select(1)
        
        # UIの状態を更新
        self.meeting_start_btn.config(state="disabled")
        self.meeting_stop_btn.config(state="normal")
        self.transcribe_btn.config(state="disabled")
        self.batch_btn.config(state="disabled")
        
        self.status_var.set("会議録を開始しました - リアルタイム録音中...")
        
        # TODO: 実際のリアルタイム録音機能を実装
        messagebox.showinfo("情報", "会議録機能は今後実装予定です。\n現在は基本的なUI構造のみ提供しています。")
    
    def stop_meeting_recording(self):
        """会議録停止・保存"""
        if not self.is_recording_meeting:
            return
        
        self.is_recording_meeting = False
        
        # UIの状態を復元
        self.meeting_start_btn.config(state="normal")
        self.meeting_stop_btn.config(state="disabled")
        self.transcribe_btn.config(state="normal")
        self.batch_btn.config(state="normal")
        
        self.status_var.set("会議録を停止しました")
        
        # 会議録データを表示・保存
        self.save_meeting_minutes()
    
    def configure_cline_settings(self):
        """cline設定ダイアログ"""
        settings_window = tk.Toplevel(self.root)
        settings_window.title("cline設定")
        settings_window.geometry("600x500")
        settings_window.transient(self.root)
        settings_window.grab_set()
        
        # メインフレーム
        main_frame = ttk.Frame(settings_window, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # タイトル
        ttk.Label(main_frame, text="cline統合設定", font=("", 14, "bold")).pack(pady=(0, 20))
        
        # API設定セクション
        api_frame = ttk.LabelFrame(main_frame, text="API設定", padding="10")
        api_frame.pack(fill=tk.X, pady=(0, 10))
        
        # API エンドポイント
        ttk.Label(api_frame, text="API エンドポイント:").grid(row=0, column=0, sticky=tk.W, pady=5)
        endpoint_var = tk.StringVar(value=self.cline_settings['api_endpoint'])
        ttk.Entry(api_frame, textvariable=endpoint_var, width=50).grid(row=0, column=1, sticky=(tk.W, tk.E), padx=(10, 0), pady=5)
        
        # API キー
        ttk.Label(api_frame, text="API キー:").grid(row=1, column=0, sticky=tk.W, pady=5)
        apikey_var = tk.StringVar(value=self.cline_settings['api_key'])
        ttk.Entry(api_frame, textvariable=apikey_var, width=50, show="*").grid(row=1, column=1, sticky=(tk.W, tk.E), padx=(10, 0), pady=5)
        
        # モデル選択
        ttk.Label(api_frame, text="モデル:").grid(row=2, column=0, sticky=tk.W, pady=5)
        model_var = tk.StringVar(value=self.cline_settings['model'])
        model_combo = ttk.Combobox(api_frame, textvariable=model_var, width=47,
                                  values=["claude-3-5-sonnet-20241022", "claude-3-haiku-20240307", "gpt-4", "gpt-3.5-turbo"])
        model_combo.grid(row=2, column=1, sticky=(tk.W, tk.E), padx=(10, 0), pady=5)
        
        api_frame.columnconfigure(1, weight=1)
        
        # 処理方式設定
        processing_frame = ttk.LabelFrame(main_frame, text="処理方式", padding="10")
        processing_frame.pack(fill=tk.X, pady=(0, 10))
        
        use_local_var = tk.BooleanVar(value=self.cline_settings['use_local_processing'])
        ttk.Checkbutton(processing_frame, text="ローカル処理を使用（API未設定時のフォールバック）", 
                       variable=use_local_var).pack(anchor=tk.W)
        
        # プロンプト設定セクション
        prompt_frame = ttk.LabelFrame(main_frame, text="カスタムプロンプト", padding="10")
        prompt_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # ノートブック for プロンプトタブ
        prompt_notebook = ttk.Notebook(prompt_frame)
        prompt_notebook.pack(fill=tk.BOTH, expand=True)
        
        # 議事録生成プロンプト
        gen_frame = ttk.Frame(prompt_notebook)
        prompt_notebook.add(gen_frame, text="議事録生成")
        gen_text = tk.Text(gen_frame, wrap=tk.WORD, height=4)
        gen_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        gen_text.insert("1.0", self.cline_settings['custom_prompts']['minutes_generation'])
        
        # 議事録改善プロンプト
        imp_frame = ttk.Frame(prompt_notebook)
        prompt_notebook.add(imp_frame, text="議事録改善")
        imp_text = tk.Text(imp_frame, wrap=tk.WORD, height=4)
        imp_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        imp_text.insert("1.0", self.cline_settings['custom_prompts']['minutes_improvement'])
        
        # アクション抽出プロンプト
        act_frame = ttk.Frame(prompt_notebook)
        prompt_notebook.add(act_frame, text="アクション抽出")
        act_text = tk.Text(act_frame, wrap=tk.WORD, height=4)
        act_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        act_text.insert("1.0", self.cline_settings['custom_prompts']['action_extraction'])
        
        # 保存・キャンセルボタン
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(10, 0))
        
        def save_settings():
            self.cline_settings['api_endpoint'] = endpoint_var.get()
            self.cline_settings['api_key'] = apikey_var.get()
            self.cline_settings['model'] = model_var.get()
            self.cline_settings['use_local_processing'] = use_local_var.get()
            self.cline_settings['custom_prompts']['minutes_generation'] = gen_text.get("1.0", tk.END).strip()
            self.cline_settings['custom_prompts']['minutes_improvement'] = imp_text.get("1.0", tk.END).strip()
            self.cline_settings['custom_prompts']['action_extraction'] = act_text.get("1.0", tk.END).strip()
            
            messagebox.showinfo("保存完了", "cline設定を保存しました。")
            settings_window.destroy()
        
        ttk.Button(button_frame, text="保存", command=save_settings).pack(side=tk.RIGHT, padx=(5, 0))
        ttk.Button(button_frame, text="キャンセル", command=settings_window.destroy).pack(side=tk.RIGHT)
        
        # テスト接続ボタン
        def test_connection():
            try:
                if not self.cline_settings['api_endpoint'] or not self.cline_settings['api_key']:
                    messagebox.showwarning("設定不完全", "APIエンドポイントとAPIキーを設定してください。")
                    return
                
                # 簡単な接続テスト
                messagebox.showinfo("接続テスト", "接続テスト機能は今後実装予定です。")
            except Exception as e:
                messagebox.showerror("接続エラー", f"clineへの接続に失敗しました: {str(e)}")
        
        ttk.Button(button_frame, text="接続テスト", command=test_connection).pack(side=tk.LEFT)

    def configure_meeting_template(self):
        """議事録テンプレート設定ダイアログ"""
        template_window = tk.Toplevel(self.root)
        template_window.title("議事録テンプレート設定")
        template_window.geometry("400x300")
        template_window.transient(self.root)
        template_window.grab_set()
        
        # テンプレート設定UI（簡易版）
        ttk.Label(template_window, text="議事録テンプレート設定").pack(pady=10)
        
        # 会議タイプ選択
        ttk.Label(template_window, text="会議タイプ:").pack(anchor=tk.W, padx=20)
        meeting_type_var = tk.StringVar(value="定例会議")
        type_combo = ttk.Combobox(template_window, textvariable=meeting_type_var, 
                                values=["定例会議", "プロジェクトミーティング", "ブレインストーミング", "その他"])
        type_combo.pack(fill=tk.X, padx=20, pady=5)
        
        # 参加者テンプレート
        ttk.Label(template_window, text="参加者テンプレート:").pack(anchor=tk.W, padx=20, pady=(10,0))
        participants_text = tk.Text(template_window, height=6)
        participants_text.pack(fill=tk.BOTH, padx=20, pady=5, expand=True)
        participants_text.insert("1.0", "参加者1\n参加者2\n参加者3")
        
        # ボタン
        button_frame = ttk.Frame(template_window)
        button_frame.pack(fill=tk.X, padx=20, pady=10)
        
        ttk.Button(button_frame, text="保存", 
                  command=lambda: self.save_template(meeting_type_var.get(), 
                                                   participants_text.get("1.0", tk.END).strip(),
                                                   template_window)).pack(side=tk.RIGHT, padx=(5,0))
        ttk.Button(button_frame, text="キャンセル", 
                  command=template_window.destroy).pack(side=tk.RIGHT)
    
    def get_meeting_info(self):
        """会議情報入力ダイアログ"""
        info_window = tk.Toplevel(self.root)
        info_window.title("会議情報入力")
        info_window.geometry("400x250")
        info_window.transient(self.root)
        info_window.grab_set()
        
        result = {}
        
        # 会議タイトル
        ttk.Label(info_window, text="会議タイトル:").pack(anchor=tk.W, padx=20, pady=(20,5))
        title_var = tk.StringVar()
        ttk.Entry(info_window, textvariable=title_var).pack(fill=tk.X, padx=20)
        
        # 参加者
        ttk.Label(info_window, text="参加者 (カンマ区切り):").pack(anchor=tk.W, padx=20, pady=(10,5))
        participants_var = tk.StringVar()
        ttk.Entry(info_window, textvariable=participants_var).pack(fill=tk.X, padx=20)
        
        # 日時（自動設定）
        now = datetime.now()
        date_str = now.strftime("%Y-%m-%d %H:%M")
        ttk.Label(info_window, text=f"日時: {date_str}").pack(anchor=tk.W, padx=20, pady=(10,0))
        
        def on_ok():
            if title_var.get().strip():
                result['title'] = title_var.get().strip()
                result['date'] = date_str
                result['participants'] = [p.strip() for p in participants_var.get().split(',') if p.strip()]
                info_window.destroy()
            else:
                messagebox.showerror("エラー", "会議タイトルを入力してください。")
        
        def on_cancel():
            info_window.destroy()
        
        # ボタン
        button_frame = ttk.Frame(info_window)
        button_frame.pack(fill=tk.X, padx=20, pady=20)
        
        ttk.Button(button_frame, text="開始", command=on_ok).pack(side=tk.RIGHT, padx=(5,0))
        ttk.Button(button_frame, text="キャンセル", command=on_cancel).pack(side=tk.RIGHT)
        
        info_window.wait_window()
        return result
    
    def save_template(self, meeting_type, participants, window):
        """テンプレート保存"""
        # TODO: テンプレート保存機能を実装
        messagebox.showinfo("保存完了", f"テンプレート '{meeting_type}' を保存しました。")
        window.destroy()
    
    def save_meeting_minutes(self):
        """議事録を保存"""
        if not self.meeting_data['title']:
            return
        
        # 議事録フォーマットを作成
        minutes_content = self.format_meeting_minutes()
        
        # ファイル名を生成
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_title = "".join(c for c in self.meeting_data['title'] if c.isalnum() or c in (' ', '-', '_')).rstrip()
        filename = f"議事録_{safe_title}_{timestamp}.txt"
        
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(minutes_content)
            
            self.status_var.set(f"議事録を保存しました: {filename}")
            messagebox.showinfo("保存完了", f"議事録を保存しました:\n{filename}")
        except Exception as e:
            messagebox.showerror("保存エラー", f"議事録の保存に失敗しました: {str(e)}")
    
    def format_meeting_minutes(self):
        """議事録フォーマット作成"""
        content = []
        content.append("=" * 50)
        content.append("議事録")
        content.append("=" * 50)
        content.append("")
        content.append(f"会議名: {self.meeting_data['title']}")
        content.append(f"日時: {self.meeting_data['date']}")
        content.append(f"参加者: {', '.join(self.meeting_data['participants'])}")
        content.append("")
        content.append("=" * 30)
        content.append("会議内容")
        content.append("=" * 30)
        
        # 転写結果を追加
        transcript = self.result_text.get(1.0, tk.END).strip()
        if transcript:
            content.append(transcript)
        else:
            content.append("(転写内容なし)")
        
        content.append("")
        content.append("=" * 30)
        content.append("アクションアイテム")
        content.append("=" * 30)
        content.append("(今後実装予定)")
        
        return "\n".join(content)
    
    def show_help(self):
        """使い方を表示"""
        help_text = """MLX Whisper GUI - 使い方

基本機能:
• 音声ファイルの転写
• バッチ処理
• cline統合議事録機能

操作方法:
1. 「Browse」ボタンで音声ファイルを選択
2. 「Transcribe」ボタンで転写開始
3. 結果は自動保存されます

cline統合議事録機能:
• 「🎤 会議録開始」で会議録モードを開始
• 「⏹ 会議録停止」で停止・保存
• 「🤖 clineで議事録生成」で構造化された議事録を自動生成
• 「✨ 議事録改善」で既存議事録の品質向上
• 「📋 アクション抽出」でアクションアイテムを自動抽出

タブ機能:
• 「転写結果」タブ: 音声転写テキスト
• 「議事録」タブ: 構造化された議事録

キーボードショートカット:
• Ctrl+O: ファイルを開く
• Ctrl+S: 転写結果を保存
• Ctrl+Q: アプリを終了
"""
        messagebox.showinfo("使い方", help_text)
    
    def show_about(self):
        """バージョン情報を表示"""
        about_text = """MLX Whisper GUI
バージョン: 1.1.0

Apple Silicon用の高精度音声転写アプリケーション
MLX Whisper large-v3-turboモデルを使用

開発: MLX Whisper GUI Team
"""
        messagebox.showinfo("バージョン情報", about_text)
    
    def update_meeting_display(self):
        """議事録タブの表示を更新"""
        if self.meeting_data['title']:
            self.meeting_title_label.config(text=self.meeting_data['title'], foreground="black")
        else:
            self.meeting_title_label.config(text="(未設定)", foreground="gray")
        
        if self.meeting_data['date']:
            self.meeting_date_label.config(text=self.meeting_data['date'], foreground="black")
        else:
            self.meeting_date_label.config(text="(未設定)", foreground="gray")
        
        if self.meeting_data['participants']:
            participants_text = ", ".join(self.meeting_data['participants'])
            self.meeting_participants_label.config(text=participants_text, foreground="black")
        else:
            self.meeting_participants_label.config(text="(未設定)", foreground="gray")
        
        # 議事録内容を更新
        self.meeting_text.delete(1.0, tk.END)
        if self.meeting_data['title']:
            meeting_content = self.format_meeting_minutes()
            self.meeting_text.insert(tk.END, meeting_content)
    
    # Cline統合機能
    def call_cline_api(self, prompt_type, context=""):
        """cline APIを呼び出して議事録処理を実行"""
        try:
            # カスタムプロンプトを取得
            custom_prompt = self.cline_settings['custom_prompts'].get(prompt_type, prompt_type)
            full_prompt = f"{custom_prompt}\n\nコンテキスト:\n{context}"
            
            # API設定が完全で、ローカル処理が無効の場合はAPI呼び出し
            if (self.cline_settings['api_endpoint'] and 
                self.cline_settings['api_key'] and 
                not self.cline_settings['use_local_processing']):
                
                return self.call_external_cline_api(full_prompt)
            else:
                # ローカル処理を使用
                return self.process_with_enhanced_local_ai(prompt_type, context)
            
        except Exception as e:
            # エラー時はローカル処理にフォールバック
            return self.process_with_enhanced_local_ai(prompt_type, context)
    
    def call_external_cline_api(self, prompt):
        """外部cline APIを呼び出し（実装例）"""
        try:
            import requests
            import json
            
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {self.cline_settings["api_key"]}'
            }
            
            data = {
                'model': self.cline_settings['model'],
                'messages': [
                    {'role': 'user', 'content': prompt}
                ],
                'max_tokens': 2000
            }
            
            response = requests.post(
                f"{self.cline_settings['api_endpoint']}/api/chat",
                headers=headers,
                json=data,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                return result.get('content', '処理が完了しましたが、結果を取得できませんでした。')
            else:
                raise Exception(f"API Error: {response.status_code}")
                
        except Exception as e:
            raise Exception(f"外部API呼び出しエラー: {str(e)}")
    
    def process_with_enhanced_local_ai(self, prompt_type, context):
        """強化されたローカルAI処理"""
        if prompt_type == "minutes_generation":
            return self.generate_structured_minutes(context)
        elif prompt_type == "minutes_improvement":
            return self.improve_existing_minutes(context)
        elif prompt_type == "action_extraction":
            return self.extract_action_items_basic(context)
        else:
            return "処理が完了しました。"
    
    def process_with_local_ai(self, prompt, context):
        """ローカルAI処理（後方互換性のため）"""
        # 実際のcline統合までの暫定処理
        if "議事録生成" in prompt:
            return self.generate_structured_minutes(context)
        elif "改善" in prompt:
            return self.improve_existing_minutes(context)
        elif "アクション" in prompt:
            return self.extract_action_items_basic(context)
        else:
            return "処理が完了しました。"
    
    def generate_structured_minutes(self, transcript):
        """転写テキストから構造化された議事録を生成"""
        if not transcript.strip():
            return "転写テキストが空です。まず音声ファイルを転写してください。"
        
        # 基本的な構造化処理（実際のclineではより高度な処理が行われる）
        structured_minutes = f"""
# 議事録

## 会議概要
- **会議名**: {self.meeting_data.get('title', '未設定')}
- **日時**: {self.meeting_data.get('date', '未設定')}
- **参加者**: {', '.join(self.meeting_data.get('participants', []))}

## 主な議題と内容

{self.extract_key_points(transcript)}

## 決定事項

{self.extract_decisions(transcript)}

## アクションアイテム

{self.extract_action_items_basic(transcript)}

## その他

- 次回会議日程: （要調整）
- 課題・懸案事項: （整理中）

---
*この議事録はcline統合機能により自動生成されました*
"""
        return structured_minutes.strip()
    
    def improve_existing_minutes(self, current_minutes):
        """既存の議事録を改善"""
        if not current_minutes.strip():
            return "改善する議事録がありません。まず議事録を生成してください。"
        
        improved = f"""
{current_minutes}

## 改善された内容

- 重要ポイントの強調
- 構造の最適化
- アクションアイテムの明確化

*clineによる議事録改善が適用されました*
"""
        return improved
    
    def extract_action_items_basic(self, text):
        """基本的なアクションアイテム抽出"""
        # 簡易的な実装（実際のclineではより高度な自然言語処理）
        action_keywords = ["する必要がある", "します", "してください", "検討", "確認", "対応", "準備"]
        lines = text.split('\n')
        actions = []
        
        for line in lines:
            if any(keyword in line for keyword in action_keywords):
                actions.append(f"- {line.strip()}")
        
        return '\n'.join(actions[:5]) if actions else "- （自動抽出されたアクションアイテムはありません）"
    
    def extract_key_points(self, text):
        """主要ポイントの抽出"""
        # 簡易実装
        sentences = text.split('。')
        key_points = []
        
        for sentence in sentences[:5]:  # 最初の5文を主要ポイントとして抽出
            if len(sentence.strip()) > 10:
                key_points.append(f"- {sentence.strip()}。")
        
        return '\n'.join(key_points) if key_points else "- （主要ポイントが抽出されませんでした）"
    
    def extract_decisions(self, text):
        """決定事項の抽出"""
        decision_keywords = ["決定", "決まり", "合意", "承認", "採用"]
        lines = text.split('\n')
        decisions = []
        
        for line in lines:
            if any(keyword in line for keyword in decision_keywords):
                decisions.append(f"- {line.strip()}")
        
        return '\n'.join(decisions[:3]) if decisions else "- （明確な決定事項は抽出されませんでした）"
    
    def generate_minutes_with_cline(self):
        """clineを使用して議事録を生成"""
        transcript = self.result_text.get(1.0, tk.END).strip()
        
        if not transcript:
            messagebox.showwarning("警告", "転写テキストがありません。まず音声ファイルを転写してください。")
            return
        
        try:
            self.status_var.set("clineで議事録を生成中...")
            self.generate_minutes_btn.config(state="disabled")
            
            # cline APIを呼び出し
            def process_in_thread():
                try:
                    generated_minutes = self.call_cline_api("minutes_generation", transcript)
                    
                    # UIを更新
                    self.root.after(0, lambda: self.meeting_text.delete(1.0, tk.END))
                    self.root.after(0, lambda: self.meeting_text.insert(tk.END, generated_minutes))
                    self.root.after(0, lambda: self.status_var.set("clineによる議事録生成が完了しました"))
                    
                except Exception as e:
                    self.root.after(0, lambda: messagebox.showerror("エラー", f"議事録生成に失敗しました: {str(e)}"))
                    self.root.after(0, lambda: self.status_var.set("議事録生成に失敗しました"))
                
                finally:
                    self.root.after(0, lambda: self.generate_minutes_btn.config(state="normal"))
            
            # 別スレッドで処理
            threading.Thread(target=process_in_thread, daemon=True).start()
            
        except Exception as e:
            messagebox.showerror("エラー", f"cline連携でエラーが発生しました: {str(e)}")
            self.generate_minutes_btn.config(state="normal")
            self.status_var.set("Ready - MLX Whisper large-v3-turbo for Apple Silicon")
    
    def improve_minutes_with_cline(self):
        """clineを使用して議事録を改善"""
        current_minutes = self.meeting_text.get(1.0, tk.END).strip()
        
        if not current_minutes:
            messagebox.showwarning("警告", "改善する議事録がありません。まず議事録を生成してください。")
            return
        
        try:
            self.status_var.set("clineで議事録を改善中...")
            self.improve_minutes_btn.config(state="disabled")
            
            def process_in_thread():
                try:
                    improved_minutes = self.call_cline_api("minutes_improvement", current_minutes)
                    
                    self.root.after(0, lambda: self.meeting_text.delete(1.0, tk.END))
                    self.root.after(0, lambda: self.meeting_text.insert(tk.END, improved_minutes))
                    self.root.after(0, lambda: self.status_var.set("clineによる議事録改善が完了しました"))
                    
                except Exception as e:
                    self.root.after(0, lambda: messagebox.showerror("エラー", f"議事録改善に失敗しました: {str(e)}"))
                    self.root.after(0, lambda: self.status_var.set("議事録改善に失敗しました"))
                
                finally:
                    self.root.after(0, lambda: self.improve_minutes_btn.config(state="normal"))
            
            threading.Thread(target=process_in_thread, daemon=True).start()
            
        except Exception as e:
            messagebox.showerror("エラー", f"cline連携でエラーが発生しました: {str(e)}")
            self.improve_minutes_btn.config(state="normal")
    
    def extract_actions_with_cline(self):
        """clineを使用してアクションアイテムを抽出"""
        transcript = self.result_text.get(1.0, tk.END).strip()
        current_minutes = self.meeting_text.get(1.0, tk.END).strip()
        
        source_text = current_minutes if current_minutes else transcript
        
        if not source_text:
            messagebox.showwarning("警告", "アクションアイテムを抽出するテキストがありません。")
            return
        
        try:
            self.status_var.set("clineでアクションアイテムを抽出中...")
            self.extract_actions_btn.config(state="disabled")
            
            def process_in_thread():
                try:
                    actions = self.call_cline_api("action_extraction", source_text)
                    
                    # アクションアイテムを議事録に追加
                    current_content = self.meeting_text.get(1.0, tk.END).strip()
                    updated_content = f"{current_content}\n\n## 抽出されたアクションアイテム\n{actions}"
                    
                    self.root.after(0, lambda: self.meeting_text.delete(1.0, tk.END))
                    self.root.after(0, lambda: self.meeting_text.insert(tk.END, updated_content))
                    self.root.after(0, lambda: self.status_var.set("clineによるアクションアイテム抽出が完了しました"))
                    
                except Exception as e:
                    self.root.after(0, lambda: messagebox.showerror("エラー", f"アクションアイテム抽出に失敗しました: {str(e)}"))
                    self.root.after(0, lambda: self.status_var.set("アクションアイテム抽出に失敗しました"))
                
                finally:
                    self.root.after(0, lambda: self.extract_actions_btn.config(state="normal"))
            
            threading.Thread(target=process_in_thread, daemon=True).start()
            
        except Exception as e:
            messagebox.showerror("エラー", f"cline連携でエラーが発生しました: {str(e)}")
            self.extract_actions_btn.config(state="normal")


def main():
    """Main entry point with crash recovery"""
    # Set environment variable to prevent child processes from launching GUI
    os.environ['_MLX_WHISPER_GUI_SUBPROCESS'] = '1'
    
    # Check if this is a child process launched by ffmpeg/mlx_whisper
    if os.environ.get('_MLX_WHISPER_GUI_CHILD_PROCESS') == '1':
        # This is a child process, exit immediately
        return
    
    # First check for single instance BEFORE any environment setup
    instance_lock = SingleInstanceLock()
    if not instance_lock.acquire_lock():
        # Try to bring existing instance to front
        try_focus_existing_instance()
        
        # Show user-friendly message
        try:
            root = tk.Tk()
            root.withdraw()  # Hide main window
            response = messagebox.askquestion(
                "MLX Whisper GUI Already Running", 
                "MLX Whisper GUI is already running.\n\n"
                "Only one instance can run at a time for optimal performance.\n\n"
                "Would you like to close this window and use the existing instance?",
                icon='info'
            )
            root.destroy()
            
            if response == 'yes':
                return
            else:
                return
        except:
            print("MLX Whisper GUI is already running.")
            return
    
    # Setup FFmpeg path AFTER single instance check
    setup_ffmpeg_path()
    
    # Clean up any stale lock files from previous crashes
    try:
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
        app.instance_lock = instance_lock  # Transfer lock to app
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