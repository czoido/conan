import os
from unittest.mock import patch

import pytest

from conan.errors import ConanException, ConanInvalidConfiguration
from conan.internal.model.settings import Settings
from conan.test.utils.mocks import ConanFileMock, MockSettings
from conan.tools.system import CondaEnv
from conan.tools.system.condaenv import _conan_to_conda_subdir


@pytest.mark.parametrize("os_name, arch, expected", [
    ("Linux", "x86_64", "linux-64"),
    ("Linux", "armv8", "linux-aarch64"),
    ("Windows", "x86_64", "win-64"),
    ("Macos", "x86_64", "osx-64"),
    ("Macos", "armv8", "osx-arm64"),
])
def test_platform_mapping(os_name, arch, expected):
    settings = MockSettings({"os": os_name, "arch": arch})
    assert _conan_to_conda_subdir(settings) == expected


def test_platform_mapping_unsupported():
    settings = MockSettings({"os": "Linux", "arch": "armv7"})
    with pytest.raises(ConanInvalidConfiguration) as exc_info:
        _conan_to_conda_subdir(settings)
    assert "not supported by conda channels" in str(exc_info.value)


def _var_names(env):
    return list(env._values.keys())


def _make_conanfile(tmp_path, os_name="Linux", arch="x86_64", micromamba_path="/fake/micromamba"):
    conanfile = ConanFileMock(settings=MockSettings({"os": os_name, "arch": arch}))
    conanfile.folders.set_base_generators(str(tmp_path))
    if micromamba_path is not None:
        conanfile.conf.define("tools.system.condaenv:micromamba_path", micromamba_path)
    return conanfile


def test_default_channels(tmp_path):
    with patch("os.path.isfile", return_value=True):
        conanfile = _make_conanfile(tmp_path)
        conda = CondaEnv(conanfile)
        assert conda._channels == ["conda-forge"]


def test_explicit_channels(tmp_path):
    with patch("os.path.isfile", return_value=True):
        conanfile = _make_conanfile(tmp_path)
        conda = CondaEnv(conanfile, channels=["robostack-kilted", "conda-forge"])
        assert conda._channels == ["robostack-kilted", "conda-forge"]


def test_default_channels_from_conf(tmp_path):
    with patch("os.path.isfile", return_value=True):
        conanfile = _make_conanfile(tmp_path)
        conanfile.conf.define("tools.system.condaenv:default_channels", ["my-channel"])
        conda = CondaEnv(conanfile)
        assert conda._channels == ["my-channel"]


def test_env_dir_under_generators_folder(tmp_path):
    with patch("os.path.isfile", return_value=True):
        conanfile = _make_conanfile(tmp_path)
        conda = CondaEnv(conanfile)
        assert conda.env_dir == os.path.join(str(tmp_path), "condaenv").replace("\\", "/")


def test_install_runs_micromamba_create(tmp_path):
    with patch("os.path.isfile", return_value=True):
        conanfile = _make_conanfile(tmp_path, micromamba_path="/fake/micromamba")
        conda = CondaEnv(conanfile, channels=["conda-forge"])
        conda.install("zlib")

        assert conanfile.command is not None
        cmd = conanfile.command
        assert "/fake/micromamba" in cmd
        assert " create " in cmd
        assert "-c conda-forge" in cmd
        assert '"zlib"' in cmd
        assert "--platform linux-64" in cmd
        assert "--yes" in cmd
        assert "--strict-channel-priority" in cmd


def test_install_multiple_packages_uses_install_subcommand(tmp_path):
    with patch("os.path.isfile", return_value=True):
        conanfile = _make_conanfile(tmp_path)
        conda = CondaEnv(conanfile)

        # First call should be `create`
        conda.install("zlib")
        first = conanfile.command
        assert " create " in first

        # Now simulate that the env directory exists
        with patch("os.path.isdir", return_value=True):
            conda.install("openssl")
            second = conanfile.command
            assert " install " in second
            assert '"openssl"' in second


def test_missing_micromamba_path_raises(tmp_path):
    conanfile = _make_conanfile(tmp_path, micromamba_path="/definitely/does/not/exist")
    conda = CondaEnv(conanfile)
    with pytest.raises(ConanException) as exc_info:
        conda.install("zlib")
    assert "micromamba_path" in str(exc_info.value)


def test_micromamba_not_found_raises_with_install_hint(tmp_path):
    """CondaEnv no longer auto-downloads micromamba; it must be on the host."""
    conanfile = ConanFileMock(settings=MockSettings({"os": "Linux", "arch": "x86_64"}))
    conanfile.folders.set_base_generators(str(tmp_path))
    with patch("shutil.which", return_value=None), \
         patch.dict(os.environ, {}, clear=False):
        os.environ.pop("CONAN_CONDAENV_MICROMAMBA", None)
        conda = CondaEnv(conanfile)
        with pytest.raises(ConanException) as exc_info:
            conda.install("zlib")
        msg = str(exc_info.value)
        assert "'micromamba' not found" in msg
        assert "brew install micromamba" in msg
        assert "tools.system.condaenv:micromamba_path" in msg


def test_environment_variables_linux(tmp_path):
    with patch("os.path.isfile", return_value=True):
        conanfile = _make_conanfile(tmp_path, os_name="Linux")
        conda = CondaEnv(conanfile)
        env = conda.environment()
        names = _var_names(env)
        assert "PATH" in names
        assert "CMAKE_PREFIX_PATH" in names
        assert "LD_LIBRARY_PATH" in names
        assert "DYLD_LIBRARY_PATH" not in names
        assert "CONDA_PREFIX" in names


def test_environment_variables_macos(tmp_path):
    with patch("os.path.isfile", return_value=True):
        conanfile = _make_conanfile(tmp_path, os_name="Macos", arch="armv8")
        conda = CondaEnv(conanfile)
        env = conda.environment()
        names = _var_names(env)
        assert "DYLD_LIBRARY_PATH" in names
        assert "LD_LIBRARY_PATH" not in names


def test_environment_variables_windows(tmp_path):
    with patch("os.path.isfile", return_value=True):
        conanfile = _make_conanfile(tmp_path, os_name="Windows")
        conda = CondaEnv(conanfile)
        env = conda.environment()
        names = _var_names(env)
        assert "PATH" in names
        assert "CMAKE_PREFIX_PATH" in names
        assert "LD_LIBRARY_PATH" not in names
        assert "DYLD_LIBRARY_PATH" not in names


def test_environment_ros_packages_add_ament(tmp_path):
    with patch("os.path.isfile", return_value=True):
        conanfile = _make_conanfile(tmp_path)
        conda = CondaEnv(conanfile)
        conda.install("ros-kilted-ros-base")
        env = conda.environment()
        assert "AMENT_PREFIX_PATH" in _var_names(env)


def test_environment_no_ament_when_no_ros(tmp_path):
    with patch("os.path.isfile", return_value=True):
        conanfile = _make_conanfile(tmp_path)
        conda = CondaEnv(conanfile)
        conda.install("zlib")
        env = conda.environment()
        assert "AMENT_PREFIX_PATH" not in _var_names(env)


# ---- pack() / unpack_archive() ------------------------------------------------


def test_pack_requires_existing_prefix(tmp_path):
    with patch("os.path.isfile", return_value=True):
        conanfile = _make_conanfile(tmp_path)
        conda = CondaEnv(conanfile)
        with pytest.raises(ConanException) as exc_info:
            conda.pack()
        assert "does not exist" in str(exc_info.value)
        assert "install()" in str(exc_info.value)


def test_pack_uses_conda_pack_from_conf(tmp_path):
    conda_pack = tmp_path / "conda-pack-bin"
    conda_pack.write_text("#!/bin/sh\n")
    env_dir = tmp_path / "condaenv"
    env_dir.mkdir()

    conanfile = ConanFileMock(settings=MockSettings({"os": "Linux", "arch": "x86_64"}))
    conanfile.folders.set_base_generators(str(tmp_path))
    conanfile.conf.define("tools.system.condaenv:micromamba_path", "/fake/micromamba")
    conanfile.conf.define("tools.system.condaenv:conda_pack_path", str(conda_pack))

    with patch("os.path.isfile", return_value=True):
        conda = CondaEnv(conanfile)
        dest = conda.pack(str(tmp_path / "out.tar.gz"))

    assert dest == os.path.abspath(str(tmp_path / "out.tar.gz"))
    cmd = conanfile.command
    assert str(conda_pack) in cmd
    assert f'--prefix "{conda.env_dir}"' in cmd.replace(os.sep, "/")
    assert "--output" in cmd
    assert "--format tar.gz" in cmd
    assert "--force" in cmd


def test_pack_falls_back_to_which(tmp_path):
    env_dir = tmp_path / "condaenv"
    env_dir.mkdir()

    conanfile = _make_conanfile(tmp_path)

    with patch("os.path.isfile", return_value=True), \
         patch("shutil.which", return_value="/usr/local/bin/conda-pack"):
        conda = CondaEnv(conanfile)
        conda.pack(str(tmp_path / "out.tar.gz"))

    assert "/usr/local/bin/conda-pack" in conanfile.command


def test_pack_bootstraps_tool_env_when_not_available(tmp_path):
    env_dir = tmp_path / "condaenv"
    env_dir.mkdir()

    conanfile = _make_conanfile(tmp_path)
    commands = []

    original_run = conanfile.run

    def capture(cmd, *a, **kw):
        commands.append(cmd)
        return original_run(cmd, *a, **kw)

    conanfile.run = capture

    # isfile True for env_dir + micromamba path; False for both the 'which'
    # fallback and the cached tool-env conda-pack binary → forces bootstrap.
    real_isfile = os.path.isfile

    def isfile(path):
        sp = str(path)
        if sp.endswith(("conda-pack", "conda-pack.exe")):
            # The tool env binary doesn't exist yet → trigger install.
            return False
        if sp == "/fake/micromamba":
            return True
        return real_isfile(path)

    with patch("os.path.isfile", side_effect=isfile), \
         patch("shutil.which", return_value=None), \
         patch("conan.tools.system.condaenv.get_conan_user_home",
               return_value=str(tmp_path / "home")):
        conda = CondaEnv(conanfile)
        with pytest.raises(ConanException) as exc_info:
            # After the bootstrap command, the tool-env binary still doesn't
            # exist (because we mocked run() as a no-op) — so pack() raises.
            conda.pack(str(tmp_path / "out.tar.gz"))
        assert "conda-pack" in str(exc_info.value)

    # First command should be the micromamba create for the conda-pack tool env
    assert any("conda-pack" in c and "create" in c and "/fake/micromamba" in c
               for c in commands), f"bootstrap command missing from: {commands}"


def test_unpack_archive_missing_file(tmp_path):
    with patch("os.path.isfile", return_value=True):
        conanfile = _make_conanfile(tmp_path)
        conda = CondaEnv(conanfile)
    with pytest.raises(ConanException) as exc_info:
        conda.unpack_archive(str(tmp_path / "does-not-exist.tar.gz"),
                             str(tmp_path / "prefix"))
    assert "does not exist" in str(exc_info.value)


def test_unpack_archive_missing_conda_unpack(tmp_path):
    archive = tmp_path / "env.tar.gz"
    archive.write_bytes(b"")
    prefix = tmp_path / "prefix"

    with patch("os.path.isfile") as mock_isfile, \
         patch("conan.tools.files.unzip") as mock_unzip:
        # micromamba_path + archive exist; but conda-unpack inside prefix does not
        def isfile(path):
            return path in {str(archive), "/fake/micromamba"}
        mock_isfile.side_effect = isfile
        mock_unzip.return_value = None

        conanfile = _make_conanfile(tmp_path)
        conda = CondaEnv(conanfile)
        with pytest.raises(ConanException) as exc_info:
            conda.unpack_archive(str(archive), str(prefix))
        assert "conda-unpack" in str(exc_info.value)
