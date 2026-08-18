import os
import subprocess
import sys
import textwrap

from conan.internal.cache.home_paths import HomePaths
from conan.internal.util.files import save
from conan.test.utils.test_files import temp_folder


def _run_conan(args, conan_home):
    """ A real subprocess is needed, TestClient calls Cli.run() directly and skips main(), which
    is where the console output starts being copied to the log file """
    env = dict(os.environ, CONAN_HOME=conan_home)
    return subprocess.run([sys.executable, "-c", "from conans.conan import run; run()"] + args,
                          env=env, capture_output=True, text=True)


def _log_content(conan_home):
    log_dir = HomePaths(conan_home).command_logs_path
    logs = sorted(os.listdir(log_dir),
                  key=lambda f: os.path.getmtime(os.path.join(log_dir, f)))
    with open(os.path.join(log_dir, logs[-1]), encoding="utf-8") as handler:
        return handler.read()


def _conan_home(global_conf="core.log:enabled=True\n"):
    conan_home = temp_folder()
    home_paths = HomePaths(conan_home)
    save(os.path.join(home_paths.profiles_path, "default"),
         textwrap.dedent("""
             [settings]
             os=Linux
             arch=x86_64
             compiler=gcc
             compiler.version=11
             compiler.libcxx=libstdc++11
             build_type=Release
             """))
    save(home_paths.global_conf_path, global_conf)
    return conan_home


def test_log_full_create():
    conan_home = _conan_home()
    pkg_folder = temp_folder()
    python_exe = sys.executable.replace("\\", "/")
    save(os.path.join(pkg_folder, "conanfile.py"), textwrap.dedent(f"""
        from conan import ConanFile

        class Pkg(ConanFile):
            name = "pkg"
            version = "1.0"
            settings = "os", "arch", "compiler", "build_type"

            def build(self):
                self.run('"{python_exe}" -c "print(\\'output of the build\\')"')
        """))

    result = _run_conan(["create", pkg_folder], conan_home)
    assert result.returncode == 0, result.stderr

    content = _log_content(conan_home)
    assert "# Command: conan create" in content
    assert "pkg/1.0: Calling build()" in content  # the output of conan itself
    assert "output of the build" in content  # the output of the subprocess
    assert "# Exit code: 0 (SUCCESS)" in content
    # Everything the user saw in the console is in the log
    assert result.stderr.strip() in content


def test_log_error_exit_code():
    conan_home = _conan_home()
    result = _run_conan(["install", os.path.join(temp_folder(), "missing")], conan_home)
    assert result.returncode == 1

    content = _log_content(conan_home)
    assert "# Exit code: 1 (ERROR_GENERAL)" in content
    assert "ERROR" in content


def test_no_log_when_disabled():
    conan_home = _conan_home(global_conf="")
    result = _run_conan(["--version"], conan_home)
    assert result.returncode == 0
    assert not os.path.exists(HomePaths(conan_home).command_logs_path)
