import io
import re
import threading

_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")


class LogFile:
    """ The log file that receives a copy of everything shown in the console.

    A single instance is shared by the ``OutputTee`` wrappers of stdout and stderr, so both
    streams land in the same file, in the same order the user saw them.
    """

    def __init__(self, path):
        # newline="" so the '\n' are not translated to '\r\n' in Windows, subprocess output
        # can already contain '\r\n' and it would become '\r\r\n'
        self._file = open(path, "w", encoding="utf-8", errors="replace", newline="")
        # Conan prints from several threads, like the parallel downloads and uploads
        self._lock = threading.Lock()

    def comment(self, text):
        """ A metadata line of the header or the footer """
        with self._lock:
            if not self._file.closed:
                self._file.write(f"# {text}\n")
                self._file.flush()

    def write(self, data):
        data = _ANSI_ESCAPE_RE.sub("", data)
        if not data:
            return
        with self._lock:
            if self._file.closed:  # Late writes, after the command already finished
                return
            self._file.write(data)
            self._file.flush()

    def close(self):
        with self._lock:
            self._file.close()


class OutputTee:
    """ Wraps ``sys.stdout``/``sys.stderr`` so everything written to them is also copied to a
    ``LogFile``.

    This wrapping happens at Python level, instead of duplicating the file descriptors, so
    ``isatty()`` keeps answering for the real console and colors are not lost while logging.
    """

    def __init__(self, stream, log_file):
        self._stream = stream
        self._log = log_file

    def write(self, data):
        ret = self._stream.write(data)
        self._stream.flush()
        self._log.write(data)
        return ret

    def flush(self):
        self._stream.flush()

    def isatty(self):
        return hasattr(self._stream, "isatty") and self._stream.isatty()

    def fileno(self):
        # Not the descriptor of the console: writing to it would skip the log. Whoever wants to
        # write here has to go through ``write()``, the same as with an ``io.StringIO``
        raise io.UnsupportedOperation("fileno")

    def __getattr__(self, name):  # 'encoding', 'buffer', 'errors'... go to the real stream
        if name.startswith("_"):  # Never delegate internals, it would recurse on '_stream'
            raise AttributeError(name)
        return getattr(self._stream, name)
