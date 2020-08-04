import logging
import os
import re
import sys

from colorama import Fore, Style

from conans.errors import ConanException
from conans.util.env_reader import get_env

strip_ansi_colors_re = re.compile(r"\033\[[;?0-9]*[a-zA-Z]")


def colorama_initialize():
    if "NO_COLOR" in os.environ:
        return False

    clicolor_force = get_env("CLICOLOR_FORCE")
    if clicolor_force is not None and clicolor_force != "0":
        import colorama
        colorama.init(convert=False, strip=False)
        return True

    isatty = hasattr(sys.stdout, "isatty") and sys.stdout.isatty()

    clicolor = get_env("CLICOLOR")
    if clicolor is not None:
        if clicolor == "0" or not isatty:
            return False
        import colorama
        colorama.init()
        return True

    # Respect color env setting or check tty if unset
    color_set = "CONAN_COLOR_DISPLAY" in os.environ
    if ((color_set and get_env("CONAN_COLOR_DISPLAY", 1))
        or (not color_set and isatty)):
        import colorama
        if get_env("PYCHARM_HOSTED"):  # in PyCharm disable convert/strip
            colorama.init(convert=False, strip=False)
        else:
            colorama.init()
        color = True
    else:
        color = False
    return color


class Color(object):
    """ Wrapper around colorama colors that are undefined in importing
    """
    RED = Fore.RED  # @UndefinedVariable
    WHITE = Fore.WHITE  # @UndefinedVariable
    CYAN = Fore.CYAN  # @UndefinedVariable
    GREEN = Fore.GREEN  # @UndefinedVariable
    MAGENTA = Fore.MAGENTA  # @UndefinedVariable
    BLUE = Fore.BLUE  # @UndefinedVariable
    YELLOW = Fore.YELLOW  # @UndefinedVariable
    BLACK = Fore.BLACK  # @UndefinedVariable

    BRIGHT_RED = Style.BRIGHT + Fore.RED  # @UndefinedVariable
    BRIGHT_BLUE = Style.BRIGHT + Fore.BLUE  # @UndefinedVariable
    BRIGHT_YELLOW = Style.BRIGHT + Fore.YELLOW  # @UndefinedVariable
    BRIGHT_GREEN = Style.BRIGHT + Fore.GREEN  # @UndefinedVariable
    BRIGHT_CYAN = Style.BRIGHT + Fore.CYAN   # @UndefinedVariable
    BRIGHT_WHITE = Style.BRIGHT + Fore.WHITE   # @UndefinedVariable
    BRIGHT_MAGENTA = Style.BRIGHT + Fore.MAGENTA   # @UndefinedVariable


if get_env("CONAN_COLOR_DARK", 0):
    Color.WHITE = Fore.BLACK
    Color.CYAN = Fore.BLUE
    Color.YELLOW = Fore.MAGENTA
    Color.BRIGHT_WHITE = Fore.BLACK
    Color.BRIGHT_CYAN = Fore.BLUE
    Color.BRIGHT_YELLOW = Fore.MAGENTA
    Color.BRIGHT_GREEN = Fore.GREEN

try:
    from logging import NullHandler
except ImportError:
    class NullHandler(logging.Handler):
        def handle(self, record):
            pass

        def emit(self, record):
            pass

        def createLock(self):
            self.lock = None


def style_text(message, fg=None, bg=None):
    return "%s%s%s%s" % (fg or '', bg or '', message, Style.RESET_ALL)


class ConanOutput(object):
    """ wraps an output stream, so it can be pretty colored,
    and auxiliary info, success, warn methods for convenience.
    """

    def __init__(self, stdout=None, stderr=None):
        self._stream = stdout
        self._stream_err = stderr

        if self._stream is None and self._stream_err is None:
            logging.getLogger("conan.output").addHandler(NullHandler())
            logging.getLogger("conan.cli").addHandler(NullHandler())

        self._color = colorama_initialize()

        if self._stream_err:
            stderr_handler = logging.StreamHandler(self._stream_err)
            stderr_formatter = logging.Formatter("%(message)s")
            stderr_handler.setFormatter(stderr_formatter)
            logging.getLogger("conan.output").addHandler(stderr_handler)
            logging.getLogger("conan.output").setLevel(logging.INFO)

        if self._stream:
            stdout_handler = logging.StreamHandler(self._stream)
            stdout_formatter = logging.Formatter("%(message)s")
            stdout_handler.setFormatter(stdout_formatter)
            logging.getLogger("conan.cli").addHandler(stdout_handler)
            logging.getLogger("conan.cli").setLevel(logging.INFO)

    @property
    def is_terminal(self):
        return hasattr(self._stream, "isatty") and self._stream.isatty()

    def writeln(self, data, level=logging.INFO):
        self.write(data, level)

    def write(self, data, level=logging.INFO, logger="conan.output"):
        # We should give all the control to colorama
        # because the stripping of ANSI color codes may occur twice
        if not self._color:
            data = strip_ansi_colors_re.sub("", data)

        # https://github.com/conan-io/conan/issues/4277
        # Windows output locks produce IOErrors
        for _ in range(3):
            try:
                logger = logging.getLogger(logger)
                if level == logging.WARNING:
                    logger.warning(data)
                elif level == logging.ERROR:
                    logger.error(data)
                elif level == logging.INFO:
                    logger.info(data)
                else:
                    raise ConanException("No valid level '{}' for output message", level)
                break
            except IOError:
                import time
                time.sleep(0.02)
            except UnicodeError:
                data = data.encode("utf8").decode("ascii", "ignore")

        self.flush()

    def cli(self, data):
        self.write(data, logger="conan.cli")

    def info(self, data):
        self.writeln(style_text(data, Color.BRIGHT_CYAN))

    def highlight(self, data):
        self.writeln(style_text(data, Color.BRIGHT_MAGENTA))

    def success(self, data):
        self.writeln(style_text(data, Color.BRIGHT_GREEN))

    def warn(self, data):
        self.writeln(style_text("WARN: {}".format(data), Color.BRIGHT_YELLOW), logging.WARNING)

    def error(self, data):
        self.writeln(style_text("ERROR: {}".format(data), Color.BRIGHT_RED), logging.ERROR)

    def input_text(self, data):
        self.write(data, Color.GREEN)

    def rewrite_line(self, line):
        tmp_color = self._color
        self._color = False
        TOTAL_SIZE = 70
        LIMIT_SIZE = 32  # Hard coded instead of TOTAL_SIZE/2-3 that fails in Py3 float division
        if len(line) > TOTAL_SIZE:
            line = line[0:LIMIT_SIZE] + " ... " + line[-LIMIT_SIZE:]
        self.write("\r%s%s" % (line, " " * (TOTAL_SIZE - len(line))))
        self._stream.flush()
        self._color = tmp_color

    def flush(self):
        if self._stream:
            self._stream.flush()
        if self._stream_err:
            self._stream_err.flush()


class ScopedOutput(ConanOutput):
    def __init__(self, scope, output):
        self.scope = scope
        self._stream = output._stream
        self._stream_err = output._stream_err
        self._color = output._color

    def write(self, data, front=None, back=None, newline=False, error=False):
        assert self.scope != "virtual", "printing with scope==virtual"
        super(ScopedOutput, self).write("%s: " % self.scope, front=front, back=back,
                                        newline=False, error=error)
        super(ScopedOutput, self).write("%s" % data, front=Color.BRIGHT_WHITE, back=back,
                                        newline=newline, error=error)
