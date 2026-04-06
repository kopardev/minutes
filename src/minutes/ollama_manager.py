from __future__ import annotations

import atexit
import signal
import subprocess
import time
import urllib.error
import urllib.request
from typing import Optional


class OllamaManager:
    """Manages Ollama server lifecycle (start/stop)."""

    def __init__(self, base_url: str = "http://localhost:11434"):
        self._base_url = base_url.rstrip("/")
        self._process: Optional[subprocess.Popen] = None
        self._should_cleanup = False
        atexit.register(self.cleanup)
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum: int, frame: object) -> None:
        """Handle interrupt signals."""
        self.cleanup()
        raise KeyboardInterrupt()

    def is_running(self) -> bool:
        """Check if Ollama server is responding."""
        try:
            response = urllib.request.urlopen(f"{self._base_url}/api/tags", timeout=2)
            return response.status == 200
        except (urllib.error.URLError, Exception):
            return False

    def start(self, auto_shutdown: bool = False) -> bool:
        """
        Start Ollama server if not already running.
        
        Args:
            auto_shutdown: If True, register cleanup to stop server on exit.
            
        Returns:
            True if started or already running, False if failed.
        """
        if self.is_running():
            print("✓ Ollama server is already running")
            return True

        print("Starting Ollama server...")
        try:
            self._process = subprocess.Popen(
                ["ollama", "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,  # Create new process group for cleaner termination
            )
            self._should_cleanup = auto_shutdown
            time.sleep(2)  # Give server time to start

            if self.is_running():
                print(f"✓ Ollama server started on {self._base_url}")
                return True
            else:
                print("✗ Ollama server failed to respond")
                return False
        except FileNotFoundError:
            print("✗ Ollama command not found. Install Ollama or ensure it's in PATH")
            return False
        except Exception as e:
            print(f"✗ Failed to start Ollama: {e}")
            return False

    def cleanup(self) -> None:
        """Stop Ollama server if we started it."""
        if self._process and self._should_cleanup:
            try:
                print("Stopping Ollama server...")
                if self._process.poll() is None:  # Still running
                    self._process.terminate()
                    self._process.wait(timeout=5)
                print("✓ Ollama server stopped")
            except Exception:
                try:
                    self._process.kill()
                except Exception:
                    pass
