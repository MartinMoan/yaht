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

Each file is actually opened *twice*. The first open goes through
_CountingReader, a byte-counting file-like wrapper, purely so
App._poll_loader can show real read progress for the sidebar's
percentage indicator while a file is still loading -- HDF5's own file
open doesn't expose progress on its own. That probe is closed again
right after reading the root group's immediate-children count; the
H5Model actually handed back (and kept for the rest of the file's open
lifetime, including every later dataset read) comes from a second,
plain open with no wrapper. h5py can't swap a File's backing driver
after opening, so keeping the counting wrapper around instead would
route every future dataset read through a Python-level file object too
-- a real cost for exactly the large datasets this app cares about
handling well, just to keep a progress indicator alive for a file
that's long since finished loading. A second open is a small, one-time
price for not paying that cost forever, and the OS's page cache means
it's normally fast regardless -- the probe open just filled it.
"""
from __future__ import annotations

import os
import threading
from queue import Empty, Queue
from typing import Optional

import h5py

from .h5_model import H5Model, NodeInfo

# HDF5 (via h5py) serializes actual library calls behind its own global
# lock regardless of how many threads call into it, so this isn't about
# achieving CPU parallelism -- it's about overlapping *I/O wait*, which
# threads are perfectly capable of doing (a blocking read releases the
# GIL same as any other blocking syscall). More threads than files is
# just wasted thread-creation overhead; capped so a directory with
# hundreds of files doesn't spawn hundreds of threads.
MAX_WORKERS = 8


class _CountingReader:
    """A real file opened in binary mode, wrapped to count bytes read
    through it -- everything h5py's "read from a file-like object"
    driver needs (read/readinto/seek/tell/close, seekable/readable) is
    just forwarded to the underlying file, with read/readinto also
    tallying ``bytes_read`` first."""

    def __init__(self, path: str):
        self._f = open(path, "rb")  # noqa: SIM115 - closed explicitly by the caller
        self.bytes_read = 0

    def read(self, size: int = -1) -> bytes:
        data = self._f.read(size)
        self.bytes_read += len(data)
        return data

    def readinto(self, b) -> int:
        n = self._f.readinto(b)
        self.bytes_read += n or 0
        return n

    def seek(self, offset: int, whence: int = 0) -> int:
        return self._f.seek(offset, whence)

    def tell(self) -> int:
        return self._f.tell()

    def seekable(self) -> bool:
        return True

    def readable(self) -> bool:
        return True

    def close(self) -> None:
        self._f.close()

    @property
    def closed(self) -> bool:
        return self._f.closed


class FileOpenResult:
    __slots__ = ("index", "path", "model", "root_info", "size", "error")

    def __init__(
        self,
        index: int,
        path: str,
        model: Optional[H5Model],
        root_info: Optional[NodeInfo],
        size: int,
        error: Optional[str],
    ):
        self.index = index
        self.path = path
        self.model = model
        self.root_info = root_info
        self.size = size
        self.error = error


class MultiFileLoader:
    """Opens ``paths`` concurrently across a small thread pool."""

    def __init__(self, paths: list[str]):
        self._paths = list(paths)
        n = len(self._paths)
        # Written once by whichever worker thread claims that index,
        # before it starts the (potentially slow) open -- read by the
        # GUI thread for live progress on files still in flight (see
        # progress()). Plain lists, not dicts behind a lock: each slot
        # has exactly one writer, ever, and a torn read just means one
        # stale-by-a-tick progress number, not a real correctness issue.
        self._sizes: list[int] = [0] * n
        self._readers: list[Optional[_CountingReader]] = [None] * n

        self._result_queue: "Queue[FileOpenResult]" = Queue()
        self._dispatch_lock = threading.Lock()
        self._next_index = 0
        self._done_lock = threading.Lock()
        self._done_count = 0

        n_workers = max(1, min(MAX_WORKERS, n))
        self._threads = [threading.Thread(target=self._worker_loop, daemon=True) for _ in range(n_workers)]
        for t in self._threads:
            t.start()

    def progress(self, index: int) -> tuple[int, int]:
        """(bytes_read, total_size) for the file at ``index`` while it's
        still being opened -- (0, size-or-0) before its worker has
        actually started on it yet. Meaningless (and not called) once
        that index has a result back from poll_updates()."""
        reader = self._readers[index]
        return (reader.bytes_read if reader is not None else 0, self._sizes[index])

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
                size = os.path.getsize(path)
            except OSError:
                size = 0
            self._sizes[index] = size

            try:
                reader = _CountingReader(path)
                self._readers[index] = reader
                try:
                    probe = H5Model(path, file=h5py.File(reader, "r"))
                    root_info = probe.root_info()
                    probe.close()
                finally:
                    reader.close()

                model = H5Model(path)  # plain, unwrapped open -- see module docstring
                result = FileOpenResult(index, path, model, root_info, size, None)
            except Exception as exc:  # noqa: BLE001 - surface any h5py/OS error to the caller
                result = FileOpenResult(index, path, None, None, size, str(exc))

            self._result_queue.put(result)
            with self._done_lock:
                self._done_count += 1
