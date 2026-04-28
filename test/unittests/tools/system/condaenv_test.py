import os
from unittest.mock import patch

import pytest

from conan.errors import ConanException
from conan.test.utils.mocks import ConanFileMock, MockSettings
from conan.tools.system import CondaEnv


def _make_conanfile(tmp_path, os_name="Linux", with_package=False):
    cf = ConanFileMock(settings=MockSettings({"os": os_name, "arch": "x86_64"}))
    cf.folders.set_base_generators(str(tmp_path))
    if with_package:
        (tmp_path / "p").mkdir(exist_ok=True)
        cf.folders.set_base_package(str(tmp_path / "p"))
    cf.conf.define("tools.system.condaenv:micromamba_path", "/fake/micromamba")
    return cf


def test_construction(tmp_path):
    conda = CondaEnv(_make_conanfile(tmp_path))
    assert conda._channels == ["conda-forge"]
    assert conda.env_dir == os.path.join(str(tmp_path), "condaenv").replace("\\", "/")

    conda = CondaEnv(_make_conanfile(tmp_path), channels=["robostack-kilted"])
    assert conda._channels == ["robostack-kilted"]


def test_install_runs_micromamba(tmp_path):
    with patch("os.path.isfile", return_value=True):
        cf = _make_conanfile(tmp_path)
        conda = CondaEnv(cf)
        conda.install("zlib")
        cmd = cf.command
        assert "/fake/micromamba" in cmd
        assert " create " in cmd
        assert "-c conda-forge" in cmd
        assert '"zlib"' in cmd
        assert "--strict-channel-priority" in cmd

        # Second call switches to install once env exists.
        with patch("os.path.isdir", return_value=True):
            conda.install("openssl")
            assert " install " in cf.command


def test_micromamba_not_found(tmp_path):
    cf = ConanFileMock(settings=MockSettings({"os": "Linux", "arch": "x86_64"}))
    cf.folders.set_base_generators(str(tmp_path))
    with patch("shutil.which", return_value=None):
        with pytest.raises(ConanException) as exc:
            CondaEnv(cf).install("zlib")
        assert "'micromamba' not found" in str(exc.value)
        assert "tools.system.condaenv:micromamba_path" in str(exc.value)


@pytest.mark.parametrize("os_name, expected, missing", [
    ("Linux", "LD_LIBRARY_PATH", "DYLD_LIBRARY_PATH"),
    ("Macos", "DYLD_LIBRARY_PATH", "LD_LIBRARY_PATH"),
    ("Windows", "PATH", "LD_LIBRARY_PATH"),
])
def test_environment(tmp_path, os_name, expected, missing):
    env = CondaEnv(_make_conanfile(tmp_path, os_name=os_name)).environment()
    names = list(env._values.keys())
    assert "PATH" in names
    assert "CMAKE_PREFIX_PATH" in names
    assert "CONDA_PREFIX" in names
    assert expected in names
    assert missing not in names


def test_pack(tmp_path):
    cf = _make_conanfile(tmp_path, with_package=True)
    conda = CondaEnv(cf)

    # No env yet -> error.
    with pytest.raises(ConanException, match="install"):
        conda.pack()

    (tmp_path / "condaenv").mkdir()
    dest = conda.pack()
    assert dest == os.path.join(str(tmp_path / "p"), "condaenv.tar.gz")
    cmd = cf.command
    assert "conda-pack" in cmd
    assert "--format tar.gz" in cmd


def test_unpack_errors(tmp_path):
    cf = _make_conanfile(tmp_path, with_package=True)
    conda = CondaEnv(cf)

    # Missing archive.
    with pytest.raises(ConanException, match="does not exist"):
        conda.unpack()

    # Archive present but conda-unpack script missing post-extract.
    (tmp_path / "p" / "condaenv.tar.gz").write_bytes(b"")
    with patch("conan.tools.system.condaenv.unzip", return_value=None):
        with pytest.raises(ConanException, match="conda-unpack"):
            conda.unpack()
