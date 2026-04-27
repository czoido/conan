import os
from unittest.mock import patch

import pytest

from conan.errors import ConanException
from conan.test.utils.mocks import ConanFileMock, MockSettings
from conan.tools.system import CondaEnv


def _make_conanfile(tmp_path, os_name="Linux", arch="x86_64",
                    micromamba_path="/fake/micromamba", with_package=False):
    conanfile = ConanFileMock(settings=MockSettings({"os": os_name, "arch": arch}))
    conanfile.folders.set_base_generators(str(tmp_path))
    if with_package:
        conanfile.folders.set_base_package(str(tmp_path / "p"))
    if micromamba_path is not None:
        conanfile.conf.define("tools.system.condaenv:micromamba_path", micromamba_path)
    return conanfile


def test_default_channels(tmp_path):
    conda = CondaEnv(_make_conanfile(tmp_path))
    assert conda._channels == ["conda-forge"]


def test_explicit_channels(tmp_path):
    conda = CondaEnv(_make_conanfile(tmp_path), channels=["robostack-kilted", "conda-forge"])
    assert conda._channels == ["robostack-kilted", "conda-forge"]


def test_env_dir_under_generators_folder(tmp_path):
    conda = CondaEnv(_make_conanfile(tmp_path))
    assert conda.env_dir == os.path.join(str(tmp_path), "condaenv").replace("\\", "/")


def test_install_runs_micromamba_create(tmp_path):
    with patch("os.path.isfile", return_value=True):
        conanfile = _make_conanfile(tmp_path)
        conda = CondaEnv(conanfile, channels=["conda-forge"])
        conda.install("zlib")

        cmd = conanfile.command
        assert "/fake/micromamba" in cmd
        assert " create " in cmd
        assert "-c conda-forge" in cmd
        assert '"zlib"' in cmd
        assert "--yes" in cmd
        assert "--strict-channel-priority" in cmd


def test_install_uses_install_subcommand_when_env_exists(tmp_path):
    with patch("os.path.isfile", return_value=True):
        conanfile = _make_conanfile(tmp_path)
        conda = CondaEnv(conanfile)

        conda.install("zlib")
        assert " create " in conanfile.command

        with patch("os.path.isdir", return_value=True):
            conda.install("openssl")
            assert " install " in conanfile.command


def test_micromamba_path_must_exist(tmp_path):
    conanfile = _make_conanfile(tmp_path, micromamba_path="/definitely/does/not/exist")
    conda = CondaEnv(conanfile)
    with pytest.raises(ConanException) as exc_info:
        conda.install("zlib")
    assert "micromamba_path" in str(exc_info.value)


def test_micromamba_not_found_raises_with_install_hint(tmp_path):
    conanfile = ConanFileMock(settings=MockSettings({"os": "Linux", "arch": "x86_64"}))
    conanfile.folders.set_base_generators(str(tmp_path))
    with patch("shutil.which", return_value=None):
        conda = CondaEnv(conanfile)
        with pytest.raises(ConanException) as exc_info:
            conda.install("zlib")
        msg = str(exc_info.value)
        assert "'micromamba' not found" in msg
        assert "tools.system.condaenv:micromamba_path" in msg


def _var_names(env):
    return list(env._values.keys())


def test_environment_variables_linux(tmp_path):
    conda = CondaEnv(_make_conanfile(tmp_path, os_name="Linux"))
    names = _var_names(conda.environment())
    assert "PATH" in names
    assert "CMAKE_PREFIX_PATH" in names
    assert "LD_LIBRARY_PATH" in names
    assert "DYLD_LIBRARY_PATH" not in names
    assert "CONDA_PREFIX" in names


def test_environment_variables_macos(tmp_path):
    conda = CondaEnv(_make_conanfile(tmp_path, os_name="Macos", arch="armv8"))
    names = _var_names(conda.environment())
    assert "DYLD_LIBRARY_PATH" in names
    assert "LD_LIBRARY_PATH" not in names


def test_environment_variables_windows(tmp_path):
    conda = CondaEnv(_make_conanfile(tmp_path, os_name="Windows"))
    names = _var_names(conda.environment())
    assert "PATH" in names
    assert "CMAKE_PREFIX_PATH" in names
    assert "LD_LIBRARY_PATH" not in names
    assert "DYLD_LIBRARY_PATH" not in names


def test_pack_requires_existing_prefix(tmp_path):
    conanfile = _make_conanfile(tmp_path, with_package=True)
    conda = CondaEnv(conanfile)
    with pytest.raises(ConanException) as exc_info:
        conda.pack()
    assert "does not exist" in str(exc_info.value)
    assert "install()" in str(exc_info.value)


def test_pack_runs_conda_pack(tmp_path):
    (tmp_path / "condaenv").mkdir()
    conanfile = _make_conanfile(tmp_path, with_package=True)
    (tmp_path / "p").mkdir()
    conda = CondaEnv(conanfile)
    dest = conda.pack()

    assert dest == os.path.join(str(tmp_path / "p"), "condaenv.tar.gz")
    cmd = conanfile.command
    assert "conda-pack" in cmd
    assert "--format tar.gz" in cmd
    assert "--force" in cmd


def test_unpack_missing_archive(tmp_path):
    conanfile = _make_conanfile(tmp_path, with_package=True)
    (tmp_path / "p").mkdir()
    conda = CondaEnv(conanfile)
    with pytest.raises(ConanException) as exc_info:
        conda.unpack()
    assert "does not exist" in str(exc_info.value)


def test_unpack_missing_conda_unpack_script(tmp_path):
    pkg = tmp_path / "p"
    pkg.mkdir()
    archive = pkg / "condaenv.tar.gz"
    archive.write_bytes(b"")

    conanfile = _make_conanfile(tmp_path, with_package=True)

    with patch("conan.tools.system.condaenv.unzip", return_value=None):
        conda = CondaEnv(conanfile)
        with pytest.raises(ConanException) as exc_info:
            conda.unpack()
    assert "conda-unpack" in str(exc_info.value)
