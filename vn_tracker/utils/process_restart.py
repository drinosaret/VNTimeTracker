"""Process restart utility for handling critical failures."""

import os
import sys
import subprocess
import time
from typing import Optional

class ProcessRestarter:
    """Handles automatic process restart on critical failures."""
    
    def __init__(self, max_restarts: int = 3, restart_delay: float = 5.0):
        self.max_restarts = max_restarts
        self.restart_delay = restart_delay
        self.restart_count = 0
        self.last_restart_time = 0.0
        
    def should_restart(self) -> bool:
        """Check if process should be restarted."""
        current_time = time.time()
        
        # Reset counter if enough time has passed since last restart
        if current_time - self.last_restart_time > 300:  # 5 minutes
            self.restart_count = 0
        
        return self.restart_count < self.max_restarts
    
    def restart_process(self, crash_logger: Optional[object] = None) -> bool:
        """Restart the current process."""
        if not self.should_restart():
            if crash_logger:
                crash_logger.log_error("Maximum restart attempts reached")
            return False
        
        self.restart_count += 1
        self.last_restart_time = time.time()
        
        if crash_logger:
            crash_logger.log_info(f"Restarting process (attempt {self.restart_count}/{self.max_restarts})")
        
        try:
            # Get current executable and arguments
            if getattr(sys, 'frozen', False):
                # Running as compiled executable
                executable = sys.executable
                args = sys.argv[1:]  # Skip the executable name
            else:
                # Running as script
                executable = sys.executable
                args = [sys.argv[0]] + sys.argv[1:]
            
            # Add restart delay to prevent rapid restart loops
            time.sleep(self.restart_delay)
            
            # Start new process
            subprocess.Popen([executable] + args, 
                           cwd=os.getcwd(),
                           creationflags=subprocess.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0)
            
            return True
            
        except Exception as e:
            if crash_logger:
                crash_logger.log_error(f"Process restart failed: {e}")
            return False

# Global restart manager
restart_manager = ProcessRestarter()
