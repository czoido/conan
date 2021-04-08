import platform
import textwrap

import pytest

from conans.test.assets.sources import gen_function_cpp
from conans.test.conftest import tools_default_version
from conans.test.utils.tools import TestClient


class TestToolsCustomVersions:

    @pytest.mark.tool_cmake
    def test_default_cmake(self):
        client = TestClient()
        client.run_command('cmake --version')
        default_cmake_version = tools_default_version.get("cmake")
        assert "cmake version {}".format(default_cmake_version) in client.out

    @pytest.mark.tool_cmake(version="3.16")
    def test_custom_cmake_3_16(self):
        client = TestClient()
        client.run_command('cmake --version')
        assert "cmake version 3.16" in client.out

    @pytest.mark.tool_cmake(version="3.17")
    def test_custom_cmake_3_17(self):
        client = TestClient()
        client.run_command('cmake --version')
        assert "cmake version 3.17" in client.out

    @pytest.mark.tool_cmake(version="3.19")
    def test_custom_cmake_3_19(self):
        client = TestClient()
        client.run_command('cmake --version')
        assert "cmake version 3.19" in client.out

    @pytest.mark.tool_mingw64
    @pytest.mark.tool_cmake(version="3.16")
    @pytest.mark.skipif(platform.system() != "Windows",
                        reason="Mingw test")
    def test_custom_cmake_mingw64(self):
        client = TestClient()
        client.run_command('cmake --version')
        assert "cmake version 3.16" in client.out
        main = gen_function_cpp(name="main")
        cmakelist = textwrap.dedent("""
            cmake_minimum_required(VERSION 3.15)
            project(App C CXX)
            add_executable(app app.cpp)
            """)
        client.save({"CMakeLists.txt": cmakelist, "app.cpp": main})
        client.run_command('cmake . -G "MinGW Makefiles"')
        client.run_command("cmake --build .")
