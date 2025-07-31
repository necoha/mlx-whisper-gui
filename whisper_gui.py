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
import weakref
import requests
import urllib.parse


class ProcessManager:
    """Enhanced process management for ffmpeg and child processes"""
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialize()
        return cls._instance
    
    def _initialize(self):
        self.active_processes = []
        self.process_groups = []
        self.monitoring_enabled = True
        self.monitor_thread = None
        self.lock = threading.RLock()
        self._transcribing = False  # Track transcription state
        
        # Register cleanup at exit
        atexit.register(self.cleanup_all)
        
        # Set up signal handlers for graceful shutdown
        if platform.system() != "Windows":
            signal.signal(signal.SIGTERM, self._signal_handler)
            signal.signal(signal.SIGINT, self._signal_handler)
            signal.signal(signal.SIGPIPE, signal.SIG_IGN)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        print(f"Debug: ProcessManager received signal {signum}, cleaning up...")
        self.cleanup_all()
    
    def register_process(self, process):
        """Register a process for tracking"""
        with self.lock:
            self.active_processes.append(weakref.ref(process))
            return process
    
    def create_process_group(self):
        """Create a new process group for better isolation"""
        if platform.system() != "Windows":
            try:
                # Create new process group
                pgid = os.setpgrp()
                self.process_groups.append(pgid)
                return pgid
            except OSError:
                return None
        return None
    
    def kill_ffmpeg_processes(self, force=False):
        """Kill only stale or orphaned ffmpeg processes, not active transcription ones"""
        with self.lock:
            # Throttle ffmpeg killing to prevent excessive calls
            current_time = time.time()
            if not force and hasattr(self, '_last_ffmpeg_kill') and (current_time - self._last_ffmpeg_kill) < 5:
                return  # Skip if called too recently (increased to 5 seconds)
            
            self._last_ffmpeg_kill = current_time
        
        # Only kill stale processes if forced (app shutdown) or if not currently transcribing
        if not force and hasattr(self, '_transcribing') and self._transcribing:
            print("Debug: Skipping ffmpeg cleanup during active transcription")
            return
        
        try:
            import psutil
            killed_count = 0
            current_time = time.time()
            
            for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'create_time']):
                try:
                    proc_info = proc.info
                    proc_name = proc_info.get('name', '').lower()
                    cmdline = proc_info.get('cmdline', [])
                    create_time = proc_info.get('create_time', 0)
                    
                    # Check if it's an ffmpeg process
                    if ('ffmpeg' in proc_name or 
                        any('ffmpeg' in str(arg).lower() for arg in cmdline)):
                        
                        # Only kill if it's been running for more than 5 minutes (likely stale)
                        # or if force=True (app shutdown)
                        process_age = current_time - create_time
                        if force or process_age > 300:  # 5 minutes
                            print(f"Debug: Killing stale ffmpeg process {proc_info['pid']} (age: {process_age:.1f}s)")
                            try:
                                proc.terminate()
                                proc.wait(timeout=2)
                                killed_count += 1
                            except psutil.TimeoutExpired:
                                proc.kill()
                                killed_count += 1
                            except (psutil.NoSuchProcess, psutil.AccessDenied):
                                pass
                        else:
                            print(f"Debug: Keeping active ffmpeg process {proc_info['pid']} (age: {process_age:.1f}s)")
                            
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            
            if killed_count > 0:
                print(f"Debug: Killed {killed_count} stale ffmpeg processes")
                
        except ImportError:
            # Avoid using pkill/killall as they can interfere with other applications
            print("Debug: psutil not available, skipping ffmpeg cleanup to prevent interference")
    
    def cleanup_all(self):
        """Clean up all tracked processes and process groups - quick version"""
        try:
            with self.lock:
                self.monitoring_enabled = False
                
                # Clean up tracked processes - with short timeout
                for proc_ref in self.active_processes[:]:
                    proc = proc_ref()
                    if proc and proc.poll() is None:
                        try:
                            proc.terminate()
                            proc.wait(timeout=0.5)  # Reduced timeout
                        except (subprocess.TimeoutExpired, OSError):
                            try:
                                proc.kill()
                            except OSError:
                                pass
                
                # Quick ffmpeg cleanup (force=True, no waiting)
                self.kill_ffmpeg_processes(force=True)
                
                # Clean up process groups - don't wait
                for pgid in self.process_groups:
                    try:
                        os.killpg(pgid, signal.SIGTERM)
                        # Don't wait - just send SIGKILL immediately
                        os.killpg(pgid, signal.SIGKILL)
                    except (OSError, ProcessLookupError):
                        pass
        except Exception as e:
            print(f"Debug: Quick cleanup error: {e}")
            # Don't let cleanup errors block shutdown
            
            self.active_processes.clear()
            self.process_groups.clear()
    
    def start_monitoring(self):
        """Start background monitoring of processes (only once)"""
        with self.lock:
            if self.monitor_thread is None or not self.monitor_thread.is_alive():
                self.monitoring_enabled = True
                self.monitor_thread = threading.Thread(target=self._monitor_processes, daemon=True)
                self.monitor_thread.start()
                print("Debug: ProcessManager monitoring started")
    
    def _monitor_processes(self):
        """Background process monitoring"""
        while self.monitoring_enabled:
            try:
                with self.lock:
                    # Clean up dead process references
                    self.active_processes = [ref for ref in self.active_processes if ref() is not None]
                
                # Check for orphaned ffmpeg processes every 30 seconds (reduced frequency)
                self._check_orphaned_ffmpeg()
                
                time.sleep(30)
            except Exception as e:
                print(f"Debug: Process monitoring error: {e}")
                time.sleep(5)
    
    def _check_orphaned_ffmpeg(self):
        """Check for and clean up truly orphaned ffmpeg processes"""
        # Skip if currently transcribing to avoid killing active processes
        if hasattr(self, '_transcribing') and self._transcribing:
            print("Debug: Skipping orphaned ffmpeg check during active transcription")
            return
            
        try:
            import psutil
            current_pid = os.getpid()
            app_name = "MLXWhisperGUI"
            
            for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'ppid']):
                try:
                    proc_info = proc.info
                    if proc_info['pid'] == current_pid:
                        continue
                        
                    proc_name = proc_info.get('name', '').lower()
                    cmdline = proc_info.get('cmdline', [])
                    
                    if 'ffmpeg' in proc_name or any('ffmpeg' in str(arg).lower() for arg in cmdline):
                        try:
                            parent = proc.parent()
                            # Check if parent exists and is our application
                            if parent is None or not parent.is_running():
                                print(f"Debug: Found orphaned ffmpeg process {proc_info['pid']} - parent is dead")
                                proc.terminate()
                                proc.wait(timeout=2)
                            else:
                                # Check if parent is our application by checking the command line
                                parent_cmdline = parent.cmdline()
                                if parent_cmdline and not any(app_name in str(cmd) for cmd in parent_cmdline):
                                    # Parent exists but is not our app - likely inherited from another process
                                    print(f"Debug: Found ffmpeg process {proc_info['pid']} with foreign parent {parent.pid}")
                                    # Don't terminate - might be from another legitimate application
                                else:
                                    print(f"Debug: Keeping ffmpeg process {proc_info['pid']} with valid parent {parent.pid}")
                        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.TimeoutExpired):
                            pass
                                
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
                    
        except ImportError:
            pass


class SingleInstanceLock:
    """Advanced single instance lock using multiple mechanisms"""
    def __init__(self, app_name="MLXWhisperGUI"):
        self.app_name = app_name
        self.lock_file_path = None
        self.lock_file_handle = None
        self.socket = None
        self.pid_file_path = None
        
        # Use global process manager (initialized in main app)
        self.process_manager = ProcessManager()
        
    def acquire_lock(self):
        """Try to acquire the single instance lock using multiple methods"""
        try:
            # Kill any stale processes first
            self._cleanup_stale_processes()
            
            # Check if another instance is already running
            if self._check_existing_instance():
                return False
            
            # Set up process group for better child process management
            self._setup_process_group()
            
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
            
            self.release_lock()
            return False
            
        except Exception as e:
            print(f"Debug: Lock acquisition failed: {e}")
            return False
    
    def _check_existing_instance(self):
        """Check if another instance is already running"""
        try:
            # Check PID file first
            if platform.system() == "Darwin":
                pid_dir = os.path.expanduser("~/Library/Application Support/MLXWhisperGUI")
            else:
                pid_dir = tempfile.gettempdir()
            
            pid_file = os.path.join(pid_dir, f"{self.app_name}.pid")
            current_pid = os.getpid()
            
            if os.path.exists(pid_file):
                try:
                    with open(pid_file, 'r') as f:
                        content = f.read().strip()
                        lines = content.split('\n')
                        stored_pid = int(lines[0])
                    
                    # Always check if this is the same process first
                    if stored_pid == current_pid:
                        print(f"Debug: PID file contains current process {current_pid}, clearing stale file")
                        try:
                            os.remove(pid_file)  # Remove stale self-reference
                        except:
                            pass
                        return False  # This is the same process
                    
                    # Check if the stored process is still running
                    try:
                        os.kill(stored_pid, 0)  # Signal 0 just checks if process exists
                        # Process exists, verify it's our application
                        import psutil
                        proc = psutil.Process(stored_pid)
                        proc_name = proc.name().lower()
                        if 'mlxwhispergui' in proc_name or 'whisper' in proc_name:
                            print(f"Debug: Found existing MLXWhisperGUI process {stored_pid} (current: {current_pid})")
                            return True
                        else:
                            # Process exists but it's not our app - remove stale PID file
                            print(f"Debug: PID {stored_pid} exists but is not MLXWhisperGUI ({proc_name}), removing stale PID file")
                            try:
                                os.remove(pid_file)
                            except:
                                pass
                            return False
                    except (OSError, ProcessLookupError, psutil.NoSuchProcess):
                        # Process is dead, clean up stale PID file
                        try:
                            os.remove(pid_file)
                            print(f"Debug: Removed stale PID file for dead process {stored_pid}")
                        except:
                            pass
                        return False
                except (ValueError, IOError, IndexError):
                    # Invalid PID file, remove it
                    try:
                        os.remove(pid_file)
                        print("Debug: Removed invalid PID file")
                    except:
                        pass
                    return False
            
            return False
            
        except Exception as e:
            print(f"Debug: Exception in _check_existing_instance: {e}")
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
                        content = f.read().strip()
                        lines = content.split('\n')
                        old_pid = int(lines[0])
                    
                    # Check if process is still running
                    try:
                        os.kill(old_pid, 0)  # Signal 0 just checks if process exists
                        # If process exists, check if it's transcribing (give it more leniency)
                        if len(lines) >= 3 and "TRANSCRIBING" in lines[2]:
                            print(f"Debug: Found active transcription process {old_pid}, avoiding interference")
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
        """Release all locks and cleanup child processes"""
        try:
            # Use enhanced process manager for cleanup
            self.process_manager.cleanup_all()
            
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
            # First check PID file method which is more reliable
            if self._check_existing_instance():
                return True
            
            # Quick check using socket as backup
            test_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            test_socket.settimeout(0.5)
            
            for port in range(17001, 17010):
                try:
                    result = test_socket.connect_ex(('127.0.0.1', port))
                    if result == 0:
                        test_socket.close()
                        print(f"Debug: Found socket lock on port {port}")
                        return True
                except:
                    continue
            
            test_socket.close()
            return False
            
        except Exception as e:
            print(f"Debug: Exception in is_another_instance_running: {e}")
            return False
    
    def _setup_process_group(self):
        """Set up process group for better child process management"""
        try:
            if platform.system() != "Windows":
                # Create a new process group on Unix systems
                self.process_group_id = os.getpid()
                os.setpgrp()  # Make this process the group leader
        except Exception as e:
            print(f"Debug: Failed to set up process group: {e}")

    def _cleanup_stale_processes(self):
        """Clean up only truly stale/zombie processes that might interfere"""
        try:
            import psutil
            current_pid = os.getpid()
            
            # Only clean up zombie/dead processes, not running ones
            for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'status']):
                try:
                    if proc.info['pid'] == current_pid:
                        continue
                        
                    # Only target zombie or dead processes
                    status = proc.info.get('status')
                    if status in [psutil.STATUS_ZOMBIE, psutil.STATUS_DEAD]:
                        # Check if it's related to our app
                        cmdline = proc.info.get('cmdline', [])
                        is_our_app = any(self.app_name.lower() in str(arg).lower() for arg in cmdline)
                        
                        if is_our_app:
                            print(f"Debug: Cleaning up zombie process {proc.info['pid']}")
                            try:
                                proc.terminate()
                                proc.wait(timeout=1)
                            except (psutil.NoSuchProcess, psutil.TimeoutExpired):
                                pass
                                
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
                    
        except ImportError:
            # psutil not available, use basic cleanup
            self._basic_process_cleanup()
        except Exception as e:
            print(f"Debug: Error cleaning up stale processes: {e}")
    
    def _basic_process_cleanup(self):
        """Basic process cleanup without psutil - minimalistic approach"""
        try:
            # Don't use pkill as it can kill legitimate processes
            # Only clean up what we can safely identify as ours
            print("Debug: Skipping aggressive process cleanup to prevent interference")
        except Exception:
            pass
    
        except Exception as e:
            print(f"Debug: Error cleaning up process group: {e}")
    
    def register_child_process(self, process):
        """Register a child process for cleanup (deprecated - use ProcessManager)"""
        # Redirect to ProcessManager
        return self.process_manager.register_process(process)


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
            
            # Set process isolation and control flags
            os.environ['FFMPEG_ISOLATION'] = '1'
            os.environ['FFMPEG_HIDE_BANNER'] = '1'  # Reduce noise
            os.environ['FFMPEG_NOSTDIN'] = '1'      # Prevent stdin issues
            
    # Always set these for better ffmpeg behavior
    os.environ['PYTHONUNBUFFERED'] = '1'  # Ensure output is not buffered
    
    # Set up signal handling for child processes
    if platform.system() != "Windows":
        # Ignore SIGPIPE to prevent ffmpeg issues
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)


class WhisperGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("MLX Whisper GUI - Audio Transcription")
        self.root.geometry("800x600")
        self.root.minsize(600, 400)
        
        # Initialize single instance lock
        self.instance_lock = SingleInstanceLock()
        
        # Clean up any stale PID files from previous instances
        self._cleanup_stale_pid_files()
        
        # Initialize global process manager
        self.process_manager = ProcessManager()
        
        # Start process monitoring (once per application)
        self.process_manager.start_monitoring()
        
        # Set up process monitoring
        self._setup_process_monitoring()
        
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
            "ko": "Korean",
            "zh": "Chinese",
            "es": "Spanish",
            "fr": "French",
            "de": "German",
            "it": "Italian",
            "pt": "Portuguese",
            "ru": "Russian",
            "ar": "Arabic",
            "hi": "Hindi",
            "th": "Thai",
            "vi": "Vietnamese"
        }
        
        self.create_widgets()
        
        # Load saved settings
        self.load_settings()
        
    def create_widgets(self):
        # Create notebook for tabs
        self.notebook = ttk.Notebook(self.root)
        self.notebook.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=5, pady=5)
        
        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        
        # Create tabs
        self.create_transcription_tab()
        self.create_minutes_tab()
        self.create_settings_tab()
    
    def create_transcription_tab(self):
        # Main transcription frame
        main_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(main_frame, text="🎤 Transcription")
        
        # Configure grid weights
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
    
    def create_minutes_tab(self):
        # Meeting minutes frame
        minutes_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(minutes_frame, text="📝 Meeting Minutes")
        
        # Configure grid weights
        minutes_frame.columnconfigure(0, weight=1)
        minutes_frame.rowconfigure(4, weight=1)
        
        # Instructions
        instructions = ttk.Label(minutes_frame, 
            text="Generate meeting minutes from transcription using CIRCUIT API",
            font=('TkDefaultFont', 10))
        instructions.grid(row=0, column=0, sticky=tk.W, pady=(0, 10))
        
        # Text input source frame
        input_frame = ttk.LabelFrame(minutes_frame, text="Input Source", padding="10")
        input_frame.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        input_frame.columnconfigure(1, weight=1)
        
        # Text source selection
        self.text_source_var = tk.StringVar(value="transcript")
        self.text_source_var.trace('w', self.on_text_source_change)
        
        # Option 1: Use transcript from transcription
        ttk.Radiobutton(input_frame, text="Use transcript from transcription tab", 
                       variable=self.text_source_var, value="transcript").grid(row=0, column=0, columnspan=2, sticky=tk.W, pady=(0, 5))
        
        # Option 2: Load text file
        ttk.Radiobutton(input_frame, text="Load text file:", 
                       variable=self.text_source_var, value="file").grid(row=1, column=0, sticky=tk.W, pady=(0, 5))
        
        # Text file selection
        text_file_frame = ttk.Frame(input_frame)
        text_file_frame.grid(row=2, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 5))
        text_file_frame.columnconfigure(1, weight=1)
        
        self.text_file_var = tk.StringVar()
        text_file_entry = ttk.Entry(text_file_frame, textvariable=self.text_file_var, state='readonly')
        text_file_entry.grid(row=0, column=0, sticky=(tk.W, tk.E), padx=(0, 5))
        
        ttk.Button(text_file_frame, text="Browse Text File", 
                  command=self.browse_text_file).grid(row=0, column=1)
        
        # Generate button frame
        generate_frame = ttk.Frame(minutes_frame)
        generate_frame.grid(row=2, column=0, sticky=(tk.W, tk.E), pady=(0, 5))
        
        self.generate_minutes_btn = ttk.Button(generate_frame, text="🤖 Generate Minutes with CIRCUIT", 
                                             command=self.generate_minutes, state=tk.DISABLED)
        self.generate_minutes_btn.pack(side=tk.LEFT)
        
        # Progress indicator for minutes generation
        self.minutes_progress = ttk.Progressbar(generate_frame, mode='indeterminate')
        self.minutes_progress.pack(side=tk.LEFT, padx=(10, 0), fill=tk.X, expand=True)
        
        # Status label for minutes generation (separate row)
        self.minutes_status = ttk.Label(minutes_frame, text="Ready to generate minutes", foreground='gray')
        self.minutes_status.grid(row=3, column=0, sticky=tk.W, pady=(0, 10))
        
        # Minutes text area
        self.minutes_text = scrolledtext.ScrolledText(minutes_frame, wrap=tk.WORD, height=20)
        self.minutes_text.grid(row=4, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 10))
        
        # Save minutes button
        save_minutes_frame = ttk.Frame(minutes_frame)
        save_minutes_frame.grid(row=5, column=0, sticky=(tk.W, tk.E))
        
        self.save_minutes_btn = ttk.Button(save_minutes_frame, text="💾 Save Minutes", 
                                          command=self.save_minutes, state=tk.DISABLED)
        self.save_minutes_btn.pack(side=tk.LEFT)
        
        self.copy_minutes_btn = ttk.Button(save_minutes_frame, text="📋 Copy Minutes", 
                                          command=self.copy_minutes, state=tk.DISABLED)
        self.copy_minutes_btn.pack(side=tk.LEFT, padx=(10, 0))
    
    def create_settings_tab(self):
        # Settings frame
        settings_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(settings_frame, text="⚙️ Settings")
        
        # Configure grid weights
        settings_frame.columnconfigure(1, weight=1)
        
        # CIRCUIT API Settings
        api_group = ttk.LabelFrame(settings_frame, text="CIRCUIT API Configuration", padding="10")
        api_group.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 20))
        api_group.columnconfigure(1, weight=1)
        
        # Client ID
        ttk.Label(api_group, text="Client ID:").grid(row=0, column=0, sticky=tk.W, pady=(0, 5))
        self.client_id_var = tk.StringVar()
        self.client_id_entry = ttk.Entry(api_group, textvariable=self.client_id_var, width=50)
        self.client_id_entry.grid(row=0, column=1, sticky=(tk.W, tk.E), pady=(0, 5))
        
        # Client Secret
        ttk.Label(api_group, text="Client Secret:").grid(row=1, column=0, sticky=tk.W, pady=(0, 5))
        self.client_secret_var = tk.StringVar()
        self.client_secret_entry = ttk.Entry(api_group, textvariable=self.client_secret_var, show="*", width=50)
        self.client_secret_entry.grid(row=1, column=1, sticky=(tk.W, tk.E), pady=(0, 5))
        
        # App Key
        ttk.Label(api_group, text="App Key:").grid(row=2, column=0, sticky=tk.W, pady=(0, 5))
        self.app_key_var = tk.StringVar()
        self.app_key_entry = ttk.Entry(api_group, textvariable=self.app_key_var, width=50)
        self.app_key_entry.grid(row=2, column=1, sticky=(tk.W, tk.E), pady=(0, 5))
        
        # Model selection for CIRCUIT API
        ttk.Label(api_group, text="Model:").grid(row=3, column=0, sticky=tk.W, pady=(0, 5))
        self.circuit_model_var = tk.StringVar(value="gpt-4o-mini (Free Tier)")
        model_combo = ttk.Combobox(api_group, textvariable=self.circuit_model_var, 
                                  values=[
                                      "gpt-4o-mini (Free Tier)",
                                      "gpt-4.1 (Free Tier)",
                                      "gpt-4o (Premium Tier - Pay as you use)",
                                      "o4-mini (Premium Tier - Pay as you use)",
                                      "o3 (Premium Tier - Pay as you use)",
                                      "gemini-2.5-flash (Premium Tier - Pay as you use)",
                                      "gemini-2.5-pro (Premium Tier - Pay as you use)"
                                  ], state="readonly")
        model_combo.grid(row=3, column=1, sticky=(tk.W, tk.E), pady=(0, 5))
        
        # Language selection for minutes
        ttk.Label(api_group, text="Minutes Language:").grid(row=4, column=0, sticky=tk.W, pady=(0, 5))
        self.minutes_language_var = tk.StringVar(value="Auto (from transcript)")
        language_combo = ttk.Combobox(api_group, textvariable=self.minutes_language_var, 
                                    values=["Auto (from transcript)", "English", "Japanese", "Chinese", "Spanish", "French", "German", "Korean"], state="readonly")
        language_combo.grid(row=4, column=1, sticky=(tk.W, tk.E), pady=(0, 5))
        
        # Test connection button
        ttk.Button(api_group, text="🔍 Test Connection", 
                  command=self.test_circuit_connection).grid(row=5, column=0, columnspan=2, pady=(10, 0))
        
        # Minutes Prompt Settings
        prompt_group = ttk.LabelFrame(settings_frame, text="Meeting Minutes Template", padding="10")
        prompt_group.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 20))
        prompt_group.columnconfigure(0, weight=1)
        prompt_group.rowconfigure(1, weight=1)
        
        ttk.Label(prompt_group, text="Minutes Generation Template:").grid(row=0, column=0, sticky=tk.W, pady=(0, 5))
        
        self.minutes_prompt_var = tk.StringVar(value="""Generate focused, actionable meeting minutes from the transcript below. Keep it concise and business-ready.

**Instructions:**
- Generate in {language}
- Focus on decisions and actions, not discussions
- Use bullet points for clarity
- Keep each section brief but complete

**Format:**

# Meeting Minutes

## Summary
[2-3 sentences describing the meeting purpose and main outcome]

## Key Decisions
• [Decision 1 - what was decided and why]
• [Decision 2 - what was decided and why]
• [Additional decisions...]

## Action Items
• **[Task]** - Assigned to: [Person] - Due: [Date/Timeline]
• **[Task]** - Assigned to: [Person] - Due: [Date/Timeline]
• **[Task]** - Assigned to: [Person] - Due: [Date/Timeline]

## Important Issues
• [Issue 1 - problem that needs attention]
• [Issue 2 - concern raised during meeting]
• [Additional issues...]

## Next Steps
• [Next meeting date/time if mentioned]
• [Follow-up actions needed]
• [Dependencies or blockers]

---
**Note:** If information is unclear or missing from the transcript, use "[Not specified]"

**Transcript:**
{transcript}""")
        
        self.minutes_prompt_text = scrolledtext.ScrolledText(prompt_group, wrap=tk.WORD, height=15)
        self.minutes_prompt_text.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        self.minutes_prompt_text.insert('1.0', self.minutes_prompt_var.get())
        
        # Save settings button
        ttk.Button(settings_frame, text="💾 Save Settings", 
                  command=self.save_settings).grid(row=2, column=0, columnspan=2, pady=(10, 0))
        
        # Load saved settings
        self.load_settings()
        
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
    
    def browse_text_file(self):
        """Open file browser to select text file for minutes generation"""
        file_types = [
            ("Text files", "*.txt *.text"),
            ("All files", "*.*")
        ]
        
        filename = filedialog.askopenfilename(
            title="Select Text File",
            filetypes=file_types
        )
        
        if filename:
            self.text_file_var.set(filename)
            self.text_source_var.set("file")  # Auto-select file option
            # Enable generate button if conditions are met
            if self.can_generate_minutes():
                self.generate_minutes_btn.config(state=tk.NORMAL)
            self.minutes_status.config(text=f"Text file selected: {os.path.basename(filename)}")
    
    def on_text_source_change(self, *args):
        """Called when text source radio button selection changes"""
        # Update generate button state
        if self.can_generate_minutes():
            self.generate_minutes_btn.config(state=tk.NORMAL)
        else:
            self.generate_minutes_btn.config(state=tk.DISABLED)
    
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
            # Use better process management for ffmpeg
            result = subprocess.run(cmd, capture_output=True, text=True, 
                                  creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if platform.system() == "Windows" else 0,
                                  start_new_session=True if platform.system() != "Windows" else False)
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
            # Set transcription state to prevent ffmpeg cleanup during processing
            self.process_manager._transcribing = True
            print("Debug: Started transcription - ffmpeg cleanup disabled")
            
            # Strengthen the instance lock during transcription to prevent interference
            if hasattr(self, 'instance_lock'):
                # Force lock refresh to prevent timeout during long operations
                try:
                    # Write a fresh timestamp to lock file to indicate active processing
                    if self.instance_lock.lock_file_handle:
                        self.instance_lock.lock_file_handle.seek(0)
                        self.instance_lock.lock_file_handle.write(f"{os.getpid()}\n{time.time()}\nMLXWhisperGUI-TRANSCRIBING")
                        self.instance_lock.lock_file_handle.flush()
                        self.instance_lock.lock_file_handle.truncate()
                except Exception as e:
                    print(f"Debug: Lock refresh warning: {e}")
            
            model_name = self.model_var.get()
            language = self.language_var.get() if self.language_var.get() != "auto" else None
            
            # Create new process group for isolation
            pgid = self.process_manager.create_process_group()
            print(f"Debug: Created process group {pgid} for transcription")
            
            # Load MLX model
            self.root.after(0, lambda: self.status_var.set(f"Loading {model_name} model..."))
            self.root.after(0, lambda: self.update_progress_simulation("loading"))
            
            # Use MLX Whisper large-v3 for highest accuracy
            mlx_model_name = "mlx-community/whisper-large-v3-mlx"
            self.root.after(0, lambda: self.status_var.set("Transcribing audio with MLX..."))
            
            # Simulate progress during transcription
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
            
            # Set environment variables for better process isolation
            old_env = {}
            try:
                # Save original environment
                for key in ['PYTHONUNBUFFERED', 'MLX_DISABLE_METAL_CAPTURE', 'OBJC_DISABLE_INITIALIZE_FORK_SAFETY']:
                    old_env[key] = os.environ.get(key, None)
                
                # Set isolation variables
                os.environ['PYTHONUNBUFFERED'] = '1'
                os.environ['MLX_DISABLE_METAL_CAPTURE'] = '1'  # Prevent Metal capture issues
                os.environ['OBJC_DISABLE_INITIALIZE_FORK_SAFETY'] = 'YES'  # macOS fork safety
                
                print(f"Debug: Starting MLX Whisper transcription with process group {pgid}")
                result = mlx_whisper.transcribe(
                    self.selected_file.get(),
                    path_or_hf_repo=mlx_model_name,
                    language=language
                )
                print("Debug: MLX Whisper transcription completed successfully")
                
            finally:
                # Restore original environment
                for key, value in old_env.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value
            
            # Finalizing
            self.root.after(0, lambda: self.update_progress_simulation("finalizing"))
            
            # Update UI with results
            self.root.after(0, lambda: self.display_results(result))
            
        except Exception as e:
            error_msg = f"Error during transcription: {str(e)}"
            self.root.after(0, lambda: self.show_error(error_msg))
        
        finally:
            # Re-enable ffmpeg cleanup and clean up any remaining processes
            self.process_manager._transcribing = False
            print("Debug: Transcription finished - re-enabling ffmpeg cleanup")
            
            # Reset lock file to normal state
            if hasattr(self, 'instance_lock') and self.instance_lock.lock_file_handle:
                try:
                    self.instance_lock.lock_file_handle.seek(0)
                    self.instance_lock.lock_file_handle.write(f"{os.getpid()}\n{time.time()}\nMLXWhisperGUI")
                    self.instance_lock.lock_file_handle.flush()
                    self.instance_lock.lock_file_handle.truncate()
                except Exception as e:
                    print(f"Debug: Lock reset warning: {e}")
            
            self.process_manager.kill_ffmpeg_processes(force=True)
            
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
        
        # Enable meeting minutes button if conditions are met
        if self.can_generate_minutes():
            self.generate_minutes_btn.config(state="normal")
        
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
                    # Set transcription state for this batch file
                    self.process_manager._transcribing = True
                    print(f"Debug: Starting batch transcription for file {current_file + 1}/{total_files}")
                    time.sleep(0.5)  # Brief pause between files
                    
                    # Transcribe current file using MLX large-v3
                    language = self.language_var.get() if self.language_var.get() != "auto" else None
                    mlx_model_name = "mlx-community/whisper-large-v3-mlx"
                    
                    # Set isolation environment for batch processing
                    old_env = {}
                    try:
                        for key in ['PYTHONUNBUFFERED', 'MLX_DISABLE_METAL_CAPTURE', 'OBJC_DISABLE_INITIALIZE_FORK_SAFETY']:
                            old_env[key] = os.environ.get(key, None)
                        
                        os.environ['PYTHONUNBUFFERED'] = '1'
                        os.environ['MLX_DISABLE_METAL_CAPTURE'] = '1'
                        os.environ['OBJC_DISABLE_INITIALIZE_FORK_SAFETY'] = 'YES'
                        
                        result = mlx_whisper.transcribe(
                            file_path,
                            path_or_hf_repo=mlx_model_name,
                            language=language
                        )
                    finally:
                        # Restore environment and reset transcription state
                        self.process_manager._transcribing = False
                        for key, value in old_env.items():
                            if value is None:
                                os.environ.pop(key, None)
                            else:
                                os.environ[key] = value
                    
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
            # Reset transcription state and cleanup
            self.process_manager._transcribing = False
            
            # Reset lock file to normal state after batch processing
            if hasattr(self, 'instance_lock') and self.instance_lock.lock_file_handle:
                try:
                    self.instance_lock.lock_file_handle.seek(0)
                    self.instance_lock.lock_file_handle.write(f"{os.getpid()}\n{time.time()}\nMLXWhisperGUI")
                    self.instance_lock.lock_file_handle.flush()
                    self.instance_lock.lock_file_handle.truncate()
                except Exception as e:
                    print(f"Debug: Batch lock reset warning: {e}")
            
            self.process_manager.kill_ffmpeg_processes(force=True)
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
    
    def _setup_process_monitoring(self):
        """Set up periodic process monitoring to catch orphaned ffmpeg processes"""
        def monitor_processes():
            try:
                import psutil
                # Check for orphaned ffmpeg processes every 30 seconds
                for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'ppid']):
                    try:
                        proc_info = proc.info
                        if 'ffmpeg' in proc_info.get('name', '').lower():
                            cmdline = proc_info.get('cmdline', [])
                            # Check if this ffmpeg is processing audio (likely from our app)
                            if any('s16le' in str(arg) or '16000' in str(arg) for arg in cmdline):
                                # Check if parent is still alive and is our app
                                try:
                                    parent = proc.parent()
                                    if parent is None or not parent.is_running():
                                        print(f"Debug: Terminating orphaned ffmpeg process {proc_info['pid']}")
                                        proc.terminate()
                                        proc.wait(timeout=2)
                                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.TimeoutExpired):
                                    pass
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue
            except ImportError:
                pass  # psutil not available
            except Exception as e:
                print(f"Debug: Process monitoring error: {e}")
            
            # Schedule next check
            if hasattr(self, 'root') and self.root.winfo_exists():
                self.root.after(30000, monitor_processes)  # Check every 30 seconds
        
        # Start monitoring after a delay
        self.root.after(5000, monitor_processes)  # Start after 5 seconds

    def _cleanup_stale_pid_files(self):
        """Clean up any stale PID files from previous instances"""
        try:
            if platform.system() == "Darwin":
                pid_dir = os.path.expanduser("~/Library/Application Support/MLXWhisperGUI")
            else:
                pid_dir = tempfile.gettempdir()
            
            pid_file = os.path.join(pid_dir, "MLXWhisperGUI.pid")
            current_pid = os.getpid()
            
            if os.path.exists(pid_file):
                try:
                    with open(pid_file, 'r') as f:
                        content = f.read().strip()
                        lines = content.split('\n')
                        stored_pid = int(lines[0])
                    
                    # If PID file contains our current PID, it's stale
                    if stored_pid == current_pid:
                        os.remove(pid_file)
                        print(f"Debug: Removed stale self-referencing PID file")
                    else:
                        # Check if stored process is actually running
                        try:
                            os.kill(stored_pid, 0)
                            # Process exists - don't remove PID file
                            print(f"Debug: PID file contains active process {stored_pid}")
                        except (OSError, ProcessLookupError):
                            # Process is dead - remove stale PID file
                            os.remove(pid_file)
                            print(f"Debug: Removed stale PID file for dead process {stored_pid}")
                except (ValueError, IOError, IndexError):
                    # Invalid PID file - remove it
                    os.remove(pid_file)
                    print("Debug: Removed invalid PID file")
        except Exception as e:
            print(f"Debug: Exception during PID file cleanup: {e}")
    
    def on_closing(self):
        """Handle window closing event"""
        print("Debug: Application closing, performing quick cleanup")
        
        # Immediately disable monitoring to prevent interference
        if hasattr(self.process_manager, 'monitoring_enabled'):
            self.process_manager.monitoring_enabled = False
        
        # Set transcription to false to allow cleanup
        if hasattr(self.process_manager, '_transcribing'):
            self.process_manager._transcribing = False
        
        # First, destroy the GUI immediately
        try:
            self.root.quit()  # Exit mainloop immediately
        except:
            pass
        
        # Then do cleanup in background thread to avoid blocking
        def cleanup_in_background():
            try:
                # Quick cleanup only
                self.process_manager.cleanup_all()
                self.instance_lock.release_lock()
            except Exception as e:
                print(f"Debug: Background cleanup error: {e}")
            finally:
                # Force exit regardless
                import os
                os._exit(0)
        
        # Start cleanup in background
        threading.Thread(target=cleanup_in_background, daemon=True).start()
        
        # Don't wait for cleanup - exit immediately
        try:
            self.root.destroy()  # Destroy window
        except:
            pass
        
        # Force exit after short delay
        def force_exit():
            import os
            os._exit(0)
        
        self.root.after(1000, force_exit)  # Force exit after 1 second max
    
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
    
    def circuit_credentials_configured(self):
        """Check if CIRCUIT API credentials are configured"""
        return (self.client_id_var.get().strip() and 
                self.client_secret_var.get().strip() and 
                self.app_key_var.get().strip())
    
    def can_generate_minutes(self):
        """Check if minutes generation is available"""
        if not self.circuit_credentials_configured():
            return False
        
        # Check if we have text from transcript or file
        if self.text_source_var.get() == "file":
            return bool(self.text_file_var.get())
        else:
            return (hasattr(self, 'result_text') and 
                   bool(self.result_text.get(1.0, tk.END).strip()))
    
    def test_circuit_connection(self):
        """Test CIRCUIT API connection"""
        if not self.circuit_credentials_configured():
            messagebox.showerror("Error", "Please configure all CIRCUIT API credentials first")
            return
        
        def test_in_thread():
            try:
                # Get access token
                token = self.get_circuit_token()
                if token:
                    status_msg = "✅ CIRCUIT API connection successful"
                    self.root.after(0, lambda: messagebox.showinfo("Success", status_msg))
                else:
                    status_msg = "❌ Failed to authenticate with CIRCUIT API"
                    self.root.after(0, lambda: messagebox.showerror("Error", status_msg))
            except Exception as e:
                error_msg = f"❌ Connection failed: {str(e)}"
                self.root.after(0, lambda: messagebox.showerror("Error", error_msg))
        
        threading.Thread(target=test_in_thread, daemon=True).start()
    
    def get_circuit_token(self):
        """Get OAuth2 access token from CIRCUIT API"""
        import requests
        import base64
        
        client_id = self.client_id_var.get().strip()
        client_secret = self.client_secret_var.get().strip()
        
        # Encode credentials
        credentials = base64.b64encode(f'{client_id}:{client_secret}'.encode('utf-8')).decode('utf-8')
        
        url = "https://id.cisco.com/oauth2/default/v1/token"
        headers = {
            "Accept": "*/*",
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Basic {credentials}"
        }
        data = "grant_type=client_credentials"
        
        try:
            response = requests.post(url, headers=headers, data=data, timeout=30)
            response.raise_for_status()
            token_data = response.json()
            return token_data.get('access_token')
        except Exception:
            return None
    
    def generate_minutes(self):
        """Generate meeting minutes from transcript or text file using CIRCUIT API"""
        # Get text source based on selection
        if self.text_source_var.get() == "file":
            # Use text from file
            text_file_path = self.text_file_var.get()
            if not text_file_path:
                messagebox.showerror("Error", "No text file selected")
                return
            
            try:
                with open(text_file_path, 'r', encoding='utf-8') as f:
                    transcript = f.read().strip()
                if not transcript:
                    messagebox.showerror("Error", "Text file is empty")
                    return
            except Exception as e:
                messagebox.showerror("Error", f"Failed to read text file: {str(e)}")
                return
        else:
            # Use transcript from transcription tab
            if not hasattr(self, 'result_text'):
                messagebox.showerror("Error", "No transcript available for minutes generation")
                return
                
            transcript = self.result_text.get(1.0, tk.END).strip()
            if not transcript:
                messagebox.showerror("Error", "Transcript is empty")
                return
        
        # Check if CIRCUIT credentials are configured
        if not self.circuit_credentials_configured():
            messagebox.showerror("Error", "CIRCUIT API credentials not configured. Please check Settings tab.")
            return
        
        # Disable button and show progress
        self.generate_minutes_btn.config(state="disabled")
        self.minutes_progress.start()
        self.minutes_status.config(text="Generating meeting minutes with CIRCUIT API...")
        
        def generate_in_thread():
            try:
                # Get access token
                token = self.get_circuit_token()
                if not token:
                    error_msg = "Failed to authenticate with CIRCUIT API"
                    self.root.after(0, lambda: self.show_minutes_error(error_msg))
                    return
                
                # Get custom prompt template and selected language
                custom_prompt = self.minutes_prompt_text.get(1.0, tk.END).strip()
                selected_language = self.minutes_language_var.get()
                
                # Determine output language
                if selected_language == "Auto (from transcript)":
                    # Try to detect language from transcript (simple detection)
                    language_instruction = "the same language as the transcript"
                else:
                    language_instruction = selected_language
                
                # Replace placeholders with actual values
                if custom_prompt and "{transcript}" in custom_prompt:
                    prompt = custom_prompt.replace("{transcript}", transcript).replace("{language}", language_instruction)
                else:
                    prompt = f"""Please create professional meeting minutes from the following transcript. Include:

1. **Meeting Summary**: Brief overview of the main topics discussed
2. **Key Decisions**: Important decisions made during the meeting
3. **Action Items**: Tasks assigned with responsible parties (if mentioned)
4. **Next Steps**: Planned follow-up actions or next meetings

Format the output in clear, professional language suitable for business documentation.

Transcript:
{transcript}"""
                
                # Call CIRCUIT API
                minutes_text = self.call_circuit_api(token, prompt)
                if minutes_text:
                    # Display the generated minutes
                    self.root.after(0, lambda: self.display_minutes(minutes_text))
                else:
                    error_msg = "Failed to generate minutes using CIRCUIT API"
                    self.root.after(0, lambda: self.show_minutes_error(error_msg))
                    
            except Exception as e:
                error_msg = f"Error generating minutes: {str(e)}"
                self.root.after(0, lambda: self.show_minutes_error(error_msg))
        
        # Start generation in background thread
        threading.Thread(target=generate_in_thread, daemon=True).start()
    
    def call_circuit_api(self, token, prompt):
        """Call CIRCUIT API to generate meeting minutes"""
        import requests
        
        # Extract actual model name from display string (remove tier info)
        model_display = self.circuit_model_var.get()
        model = model_display.split(' (')[0]  # Extract base model name
        app_key = self.app_key_var.get().strip()
        
        url = f"https://chat-ai.cisco.com/openai/deployments/{model}/chat/completions"
        
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "api-key": token
        }
        
        # Get language setting for system prompt
        selected_language = self.minutes_language_var.get()
        if selected_language == "Auto (from transcript)":
            system_prompt = "You are a professional assistant that creates high-quality meeting minutes from transcripts. Generate the minutes in the same language as the input transcript."
        else:
            system_prompt = f"You are a professional assistant that creates high-quality meeting minutes from transcripts. Generate the minutes in {selected_language}."
        
        payload = {
            "messages": [
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "user": f'{{"appkey": "{app_key}"}}',
            "stop": ["<|im_end|>"]
        }
        
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=60)
            response.raise_for_status()
            
            result = response.json()
            if 'choices' in result and len(result['choices']) > 0:
                return result['choices'][0]['message']['content']
            else:
                print(f"Debug: Unexpected API response format: {result}")
                return None
                
        except requests.exceptions.HTTPError as e:
            print(f"Debug: HTTP error {response.status_code}: {response.text}")
            return None
        except requests.exceptions.RequestException as e:
            print(f"Debug: Request error: {str(e)}")
            return None
        except Exception as e:
            print(f"Debug: Unexpected error in CIRCUIT API call: {str(e)}")
            return None
    
    
    def display_minutes(self, minutes_text):
        """Display generated meeting minutes"""
        self.minutes_text.delete(1.0, tk.END)
        self.minutes_text.insert(tk.END, minutes_text)
        
        # Re-enable controls
        self.generate_minutes_btn.config(state="normal")
        self.save_minutes_btn.config(state="normal")
        self.copy_minutes_btn.config(state="normal")
        self.minutes_progress.stop()
        self.minutes_status.config(text="Meeting minutes generated successfully with CIRCUIT API")
    
    def show_minutes_error(self, error_msg):
        """Show error during minutes generation"""
        messagebox.showerror("Minutes Generation Error", error_msg)
        self.generate_minutes_btn.config(state="normal")
        self.minutes_progress.stop()
        self.minutes_status.config(text="Error occurred during minutes generation")
    
    def save_minutes(self):
        """Save meeting minutes to file"""
        if not hasattr(self, 'minutes_text'):
            return
            
        minutes_content = self.minutes_text.get(1.0, tk.END).strip()
        if not minutes_content:
            messagebox.showwarning("Warning", "No meeting minutes to save")
            return
        
        filename = filedialog.asksaveasfilename(
            defaultextension=".md",
            filetypes=[("Markdown files", "*.md"), ("Text files", "*.txt"), ("All files", "*.*")],
            title="Save Meeting Minutes"
        )
        
        if filename:
            try:
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(minutes_content)
                messagebox.showinfo("Success", f"Meeting minutes saved to {filename}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save file: {str(e)}")
    
    def copy_minutes(self):
        """Copy meeting minutes to clipboard"""
        if not hasattr(self, 'minutes_text'):
            return
            
        minutes_content = self.minutes_text.get(1.0, tk.END).strip()
        if not minutes_content:
            messagebox.showwarning("Warning", "No meeting minutes to copy")
            return
        
        self.root.clipboard_clear()
        self.root.clipboard_append(minutes_content)
        messagebox.showinfo("Success", "Meeting minutes copied to clipboard")
    
    def save_settings(self):
        """Save CIRCUIT API settings"""
        settings = {
            "client_id": self.client_id_var.get().strip(),
            "client_secret": self.client_secret_var.get().strip(),
            "app_key": self.app_key_var.get().strip(),
            "circuit_model": self.circuit_model_var.get(),
            "minutes_language": self.minutes_language_var.get(),
            "minutes_template": self.minutes_prompt_text.get(1.0, tk.END).strip()
        }
        
        try:
            settings_file = os.path.expanduser("~/.mlx_whisper_circuit_settings.json")
            with open(settings_file, 'w') as f:
                json.dump(settings, f, indent=2)
            messagebox.showinfo("Success", "Settings saved successfully")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save settings: {str(e)}")
    
    def load_settings(self):
        """Load saved CIRCUIT API settings"""
        try:
            settings_file = os.path.expanduser("~/.mlx_whisper_circuit_settings.json")
            if os.path.exists(settings_file):
                with open(settings_file, 'r') as f:
                    settings = json.load(f)
                
                # Load API credentials
                self.client_id_var.set(settings.get("client_id", ""))
                self.client_secret_var.set(settings.get("client_secret", ""))
                self.app_key_var.set(settings.get("app_key", ""))
                
                # Handle backward compatibility for model setting
                saved_model = settings.get("circuit_model", "gpt-4o-mini")
                # If saved model doesn't have tier info, add Free Tier for free models
                if saved_model in ["gpt-4o-mini", "gpt-4.1"]:
                    saved_model = f"{saved_model} (Free Tier)"
                elif " (" not in saved_model and saved_model in ["gpt-4o", "o4-mini", "o3", "gemini-2.5-flash", "gemini-2.5-pro"]:
                    saved_model = f"{saved_model} (Premium Tier - Pay as you use)"
                elif saved_model == "gpt-4o-mini":  # Default case
                    saved_model = "gpt-4o-mini (Free Tier)"
                
                self.circuit_model_var.set(saved_model)
                self.minutes_language_var.set(settings.get("minutes_language", "Auto (from transcript)"))
                
                # Load minutes template
                minutes_template = settings.get("minutes_template", "")
                if minutes_template and hasattr(self, 'minutes_prompt_text'):
                    self.minutes_prompt_text.delete(1.0, tk.END)
                    self.minutes_prompt_text.insert(tk.END, minutes_template)
                    
        except Exception as e:
            # Silently ignore settings loading errors
            pass
    
    def run(self):
        """Start the GUI application"""
        # Check for single instance
        if not self.instance_lock.acquire_lock():
            # Try to bring existing instance to front
            self._try_focus_existing_instance()
            
            # For GUI applications, we should always prevent double launch
            # Don't show the dialog for .app bundles as it can be confusing
            try:
                # Just inform briefly and exit
                self.root.withdraw()  # Hide the window immediately
                messagebox.showinfo(
                    "MLX Whisper GUI", 
                    "MLX Whisper GUI is already running.\n\n"
                    "The existing window has been brought to the front.",
                    icon='info'
                )
            except:
                pass
            finally:
                # Always exit if another instance is running
                try:
                    self.root.quit()
                    self.root.destroy()
                except:
                    pass
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
                # First try with the bundle identifier
                try:
                    subprocess.run([
                        'osascript', '-e',
                        'tell application "MLXWhisperGUI" to activate'
                    ], capture_output=True, timeout=2)
                except:
                    # Fallback: try with process name
                    try:
                        subprocess.run([
                            'osascript', '-e',
                            'tell application "System Events" to tell process "MLXWhisperGUI" to set frontmost to true'
                        ], capture_output=True, timeout=2)
                    except:
                        # Final fallback: try to find and activate any MLX Whisper window
                        subprocess.run([
                            'osascript', '-e',
                            '''tell application "System Events"
                                set procs to every process whose name contains "MLX" or name contains "Whisper"
                                if length of procs > 0 then
                                    set frontmost of item 1 of procs to true
                                end if
                            end tell'''
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