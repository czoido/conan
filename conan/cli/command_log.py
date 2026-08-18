import contextlib
import os
import platform
import re
import shlex
import sys
from datetime import datetime

from conan import __version__
from conan.cli import exit_codes
from conan.internal.cache.home_paths import HomePaths
from conan.internal.util.output_tee import LogFile, OutputTee

_EXIT_CODE_NAMES = {value: name for name, value in vars(exit_codes).items()
                    if name.isupper() and isinstance(value, int)}
_ENV_VARS = ("CC", "CXX", "CFLAGS", "CXXFLAGS", "LDFLAGS")


class _NullCommandLog:
    """ Used when the logging is not enabled, so the caller does not need to check """

    def set_exit_code(self, exit_code):
        pass


class _CommandLog:
    def __init__(self):
        self.start = datetime.now()
        self.exit_code = None

    def set_exit_code(self, exit_code):
        self.exit_code = exit_code


def _format_command(args):
    """ The command line as the user typed it, with the passwords hidden.

    Best effort only, the output of the command itself can still contain secrets, like a git
    url with an embedded token.
    """
    login = args[:2] == ["remote", "login"]
    result = []
    hide_next = False
    for arg in args:
        if hide_next:
            result.append("<hidden>")
            hide_next = False
        elif arg == "--password" or (login and arg == "-p"):
            result.append(arg)
            hide_next = True  # The value comes in the next argument
        elif arg.startswith("--password="):
            result.append("--password=<hidden>")
        elif login and arg.startswith("-p") and arg != "-p":  # -pmypassword
            result.append("-p<hidden>")
        else:
            result.append(shlex.quote(arg))
    return "conan " + " ".join(result)


def _write_header(log_file, args, home_folder):
    log_file.comment(f"Date: {datetime.now():%Y-%m-%d %H:%M:%S}")
    log_file.comment(f"Command: {_format_command(args)}")
    log_file.comment(f"Conan version: {__version__}")
    log_file.comment(f"Conan home: {home_folder}")
    log_file.comment(f"Working directory: {os.getcwd()}")
    log_file.comment(f"Platform: {platform.platform()}")
    for name in _ENV_VARS:
        if name in os.environ:
            log_file.comment(f"Env {name}: {os.environ[name]}")
    log_file.comment("-" * 60)


def _write_footer(log_file, command_log):
    log_file.comment("-" * 60)
    duration = (datetime.now() - command_log.start).total_seconds()
    log_file.comment(f"Duration: {duration:.1f}s")
    name = _EXIT_CODE_NAMES.get(command_log.exit_code)
    log_file.comment(f"Exit code: {command_log.exit_code}{f' ({name})' if name else ''}")


@contextlib.contextmanager
def command_log_context(conan_api, args):
    """ If ``core.log:enabled``, copy everything shown in the console to a file in the Conan
    home, including the output of the subprocesses launched by the recipes (cmake, git...)
    """
    if not conan_api.config.get("core.log:enabled", default=False, check_type=bool):
        yield _NullCommandLog()
        return

    log_dir = HomePaths(conan_api.home_folder).command_logs_path
    os.makedirs(log_dir, exist_ok=True)
    command = re.sub(r"[^A-Za-z0-9_.-]", "_", args[0]) if args else "conan"
    # The pid, so 2 commands launched in the same second do not overwrite each other
    log_path = os.path.join(log_dir,
                            f"{datetime.now():%Y%m%d_%H%M%S}_{command}_{os.getpid()}.log")

    log_file = LogFile(log_path)
    command_log = _CommandLog()
    _write_header(log_file, args, conan_api.home_folder)

    saved_stdout, saved_stderr = sys.stdout, sys.stderr
    sys.stdout = OutputTee(saved_stdout, log_file)
    sys.stderr = OutputTee(saved_stderr, log_file)
    try:
        yield command_log
    finally:
        sys.stdout, sys.stderr = saved_stdout, saved_stderr
        _write_footer(log_file, command_log)
        log_file.close()
