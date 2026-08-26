"""Background, parallel opener for multiple HDF5 files at once.

Opening N files one after another on the GUI thread -- h5py.File(...)
plus reading the root group's immediate children for the sidebar --
is what makes opening a directory with even a modest number of files
feel slow, especially when most of that time is I/O wait (a slow disk,
a network drive, or a WSL path crossing the 9p boundary into Windows)
rather than actual CPU work: the opens never overlap, so their latency
just adds up.

This runs each file's open on its own thread from a small pool instead.
h5py.File handles to *different* files don't need to be serialized the
way concurrent access to the *same* handle would -- each worker thread
here only ever touches the one file it opened, then hands it off
untouched. Results come back through a queue labeled with their
original index as soon as each file is ready, in whatever order they
actually finish (not necessarily the order they were given in) -- so a
caller can start showing/using whichever files opened first without
waiting for the slowest one. See HierarchyTree.begin_loading /
resolve_root / resolve_error and App._poll_loader for how the sidebar
uses this to fill in progressively.
"""
from __future__ import annotations

import threading
from queue import Empty, Queue
from typing import Optional

from .h5_model import H5Model

# HDF5 (via h5py) serializes actual library calls behind its own global
# lock regardless of how many threads call into it, so this isn't about
# achieving CPU parallelism -- it's about overlapping *I/O wait*, which
# threads are perfectly capable of doing (a blocking read releases the
# GIL same as any other blocking syscall). More threads than files is
# just wasted thread-creation overhead; capped so a directory with
# hundreds of files doesn't spawn hundreds of threads.
MAX_WORKERS = 8


class FileOpenResult:
    __slots__ = ("index", "path", "model", "error")

    def __init__(self, index: int, path: str, model: Optional[H5Model], error: Optional[str]):
        self.index = index
        self.path = path
        self.model = model
        self.error = error


class MultiFileLoader:
    """Opens ``paths`` concurrently across a small thread pool."""

    def __init__(self, paths: list[str]):
        self._paths = list(paths)
        self._result_queue: "Queue[FileOpenResult]" = Queue()
        self._dispatch_lock = threading.Lock()
        self._next_index = 0
        self._done_lock = threading.Lock()
        self._done_count = 0

        n_workers = max(1, min(MAX_WORKERS, len(self._paths)))
        self._threads = [threading.Thread(target=self._worker_loop, daemon=True) for _ in range(n_workers)]
        for t in self._threads:
            t.start()

    def poll_updates(self) -> list[FileOpenResult]:
        """Drain and return results that finished since the last call.
        Cheap, non-blocking -- safe to call from a UI tick."""
        out = []
        try:
            while True:
                out.append(self._result_queue.get_nowait())
        except Empty:
            pass
        return out

    def is_done(self) -> bool:
        with self._done_lock:
            return self._done_count >= len(self._paths)

    def _worker_loop(self) -> None:
        while True:
            with self._dispatch_lock:
                if self._next_index >= len(self._paths):
                    return
                index = self._next_index
                path = self._paths[index]
                self._next_index += 1

            try:
                result = FileOpenResult(index, path, H5Model(path), None)
            except Exception as exc:  # noqa: BLE001 - surface any h5py/OS error to the caller
                result = FileOpenResult(index, path, None, str(exc))

            self._result_queue.put(result)
            with self._done_lock:
                self._done_count += 1
