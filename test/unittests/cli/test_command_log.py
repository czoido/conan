import io
import os
import re
import sys

from conan.api.conan_api import ConanAPI
from conan.api.output import _color_enabled
from conan.cli.command_log import command_log_context, _format_command
from conan.internal.cache.home_paths import HomePaths
from conan.internal.util.files import save
from conan.internal.util.output_tee import LogFile, OutputTee
from conan.internal.util.runners import conan_run
from conan.test.utils.test_files import temp_folder


def _conan_api(global_conf=""):
    folder = temp_folder()
    home_paths = HomePaths(folder)
    save(os.path.join(home_paths.profiles_path, "default"), "")
    save(home_paths.global_conf_path, global_conf)
    return ConanAPI(folder)


def _log_content(conan_api):
    log_dir = HomePaths(conan_api.home_folder).command_logs_path
    log_files = os.listdir(log_dir)
    assert len(log_files) == 1
    with open(os.path.join(log_dir, log_files[0]), encoding="utf-8") as handler:
        return log_files[0], handler.read()


def test_disabled_by_default():
    conan_api = _conan_api()
    saved_stderr = sys.stderr
    with command_log_context(conan_api, ["--version"]) as command_log:
        assert sys.stderr is saved_stderr  # the streams are not wrapped at all
        command_log.set_exit_code(0)  # no-op, but it must not raise
    assert not os.path.exists(HomePaths(conan_api.home_folder).command_logs_path)


def test_header_output_and_footer():
    conan_api = _conan_api("core.log:enabled=True")
    with command_log_context(conan_api, ["install", "."]) as command_log:
        sys.stderr.write("a message of conan\n")
        sys.stdout.write("output of a formatter\n")
        command_log.set_exit_code(0)

    name, content = _log_content(conan_api)
    assert name.endswith(f"_install_{os.getpid()}.log")
    assert "# Command: conan install .\n" in content
    assert f"# Conan home: {conan_api.home_folder}\n" in content
    assert "# Conan version:" in content
    assert "# Working directory:" in content
    assert "# Platform:" in content
    assert "a message of conan\n" in content
    assert "output of a formatter\n" in content
    assert re.search(r"# Duration: \d+\.\d+s\n", content)
    assert "# Exit code: 0 (SUCCESS)" in content


def test_streams_are_restored_on_error():
    conan_api = _conan_api("core.log:enabled=True")
    saved_stdout, saved_stderr = sys.stdout, sys.stderr
    try:
        with command_log_context(conan_api, ["install", "."]) as command_log:
            command_log.set_exit_code(1)
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    assert (sys.stdout, sys.stderr) == (saved_stdout, saved_stderr)
    _, content = _log_content(conan_api)
    assert "# Exit code: 1 (ERROR_GENERAL)" in content


def test_ansi_codes_are_stripped():
    conan_api = _conan_api("core.log:enabled=True")
    with command_log_context(conan_api, ["install", "."]) as command_log:
        sys.stderr.write("\x1b[31mthis was red\x1b[0m\n")
        command_log.set_exit_code(0)
    _, content = _log_content(conan_api)
    assert "this was red\n" in content
    assert "\x1b" not in content


def test_subprocess_output_is_logged():
    conan_api = _conan_api("core.log:enabled=True")
    with command_log_context(conan_api, ["build", "."]) as command_log:
        # This is what ConanFile.run() ends up calling, with the default streams
        retcode = conan_run(f'"{sys.executable}" -c "print(\'from the subprocess\')"')
        command_log.set_exit_code(0)
    assert retcode == 0
    _, content = _log_content(conan_api)
    assert "from the subprocess" in content


def test_subprocess_error_output_is_logged():
    conan_api = _conan_api("core.log:enabled=True")
    code = "import sys; sys.stderr.write('to the stderr\\n'); sys.exit(3)"
    with command_log_context(conan_api, ["build", "."]) as command_log:
        retcode = conan_run(f'"{sys.executable}" -c "{code}"')
        command_log.set_exit_code(0)
    assert retcode == 3
    _, content = _log_content(conan_api)
    assert "to the stderr" in content


def test_subprocess_explicit_stream_is_not_intercepted():
    """ A recipe capturing the output in its own stream keeps working, and that output does not
    reach the log, the user never saw it in the console either. The stream that the recipe did
    not capture keeps going to the console, so it is still logged """
    conan_api = _conan_api("core.log:enabled=True")
    stream = io.StringIO()
    code = "import sys; print('captured'); sys.stderr.write('shown in the console\\n')"
    with command_log_context(conan_api, ["build", "."]) as command_log:
        conan_run(f'"{sys.executable}" -c "{code}"', stdout=stream)
        command_log.set_exit_code(0)
    assert "captured" in stream.getvalue()
    _, content = _log_content(conan_api)
    assert "captured" not in content
    assert "shown in the console" in content


def test_subprocess_separate_streams_are_kept_apart():
    """ Both streams are captured by the caller, each one in its own buffer, like the diff of
    'conan report' does """
    conan_api = _conan_api("core.log:enabled=True")
    out, err = io.StringIO(), io.StringIO()
    code = "import sys; print('to the stdout'); sys.stderr.write('to the stderr\\n')"
    with command_log_context(conan_api, ["report", "diff"]) as command_log:
        conan_run(f'"{sys.executable}" -c "{code}"', stdout=out, stderr=err)
        command_log.set_exit_code(0)
    assert out.getvalue().strip() == "to the stdout"
    assert err.getvalue().strip() == "to the stderr"


def test_log_name_without_args():
    conan_api = _conan_api("core.log:enabled=True")
    with command_log_context(conan_api, []) as command_log:
        command_log.set_exit_code(0)
    name, _ = _log_content(conan_api)
    assert name.endswith(f"_conan_{os.getpid()}.log")


def test_passwords_are_hidden():
    assert _format_command(["remote", "login", "r", "user", "-p", "secret"]) == \
           "conan remote login r user -p <hidden>"
    assert _format_command(["remote", "login", "r", "user", "-psecret"]) == \
           "conan remote login r user -p<hidden>"
    assert _format_command(["remote", "login", "r", "user", "--password", "secret"]) == \
           "conan remote login r user --password <hidden>"
    assert _format_command(["remote", "login", "r", "user", "--password=secret"]) == \
           "conan remote login r user --password=<hidden>"
    # '-p' is '--provider' here, not a password, it must be kept
    assert _format_command(["audit", "scan", "-p", "myprovider"]) == \
           "conan audit scan -p myprovider"


def test_arguments_with_spaces_are_quoted():
    assert _format_command(["install", ".", "-o", "pkg/*:opt=a b"]) == \
           "conan install . -o 'pkg/*:opt=a b'"


def test_tee_keeps_the_terminal_answers(monkeypatch):
    """ The reason to wrap the streams instead of duplicating the file descriptors: the color
    detection of conan asks the stream object, and a wrapper can still answer for the console """
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("CLICOLOR_FORCE", raising=False)

    class FakeTerminal(io.StringIO):
        encoding = "utf-8"

        def isatty(self):
            return True

    terminal = FakeTerminal()
    log_file = LogFile(os.path.join(temp_folder(), "some.log"))
    tee = OutputTee(terminal, log_file)
    try:
        assert tee.isatty() is True
        assert _color_enabled(tee) is True
        assert tee.encoding == "utf-8"  # delegated to the real stream
        tee.write("hello\n")
    finally:
        log_file.close()
    assert terminal.getvalue() == "hello\n"
