import contextlib
import os
import re
import sys
from datetime import datetime

from conan.internal.cache.home_paths import HomePaths
from conan.internal.util.output_tee import LogFile, OutputTee


@contextlib.contextmanager
def command_log_context(conan_api, args):
    """ If ``core.log:enabled``, copy everything shown in the console, verbatim, to a file in
    the Conan home, including the output of the subprocesses launched by the recipes (cmake,
    git...)
    """
    if not conan_api.config.get("core.log:enabled", default=False, check_type=bool):
        yield
        return

    log_dir = HomePaths(conan_api.home_folder).command_logs_path
    os.makedirs(log_dir, exist_ok=True)
    command = re.sub(r"[^A-Za-z0-9_.-]", "_", args[0]) if args else "conan"
    # The pid, so 2 commands launched in the same second do not overwrite each other
    log_path = os.path.join(log_dir,
                            f"{datetime.now():%Y%m%d_%H%M%S}_{command}_{os.getpid()}.log")

    log_file = LogFile(log_path)
    saved_stdout, saved_stderr = sys.stdout, sys.stderr
    sys.stdout = OutputTee(saved_stdout, log_file)
    sys.stderr = OutputTee(saved_stderr, log_file)
    try:
        yield
    finally:
        sys.stdout, sys.stderr = saved_stdout, saved_stderr
        log_file.close()
