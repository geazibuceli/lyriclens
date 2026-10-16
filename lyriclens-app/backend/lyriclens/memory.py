import threading


class PeakMemory:
    """Optional sampled sum of process-tree RSS, not a VRAM measurement."""
    def __init__(self):
        self.peak = None
        self.stop_event = threading.Event()
        self.thread = None

    def start(self):
        try:
            import psutil
        except ImportError:
            return self
        process = psutil.Process()
        def sample():
            while not self.stop_event.is_set():
                total = 0
                for proc in [process, *process.children(recursive=True)]:
                    try:
                        total += proc.memory_info().rss
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
                self.peak = max(self.peak or 0, total)
                self.stop_event.wait(.05)
        self.thread = threading.Thread(target=sample, daemon=True)
        self.thread.start()
        return self

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=1)
        return self.peak
