import textwrap

import pytest

from conans.test.utils.tools import TestClient


class TestConanToolFiles:

    def test_imports(self):
        conanfile = textwrap.dedent("""
            from conans import ConanFile
            from conan.tools.files import load, save, mkdir, download, get, ftp_download

            class Pkg(ConanFile):
                pass
            """)
        client = TestClient()
        client.save({"conanfile.py": conanfile})
        client.run("install .")

    @pytest.mark.parametrize("tool", ["load", "save", "mkdir",
                                      "download", "get", "ftp_download"])
    def test_old_imports_warning(self, tool):
        conanfile = textwrap.dedent("""
            from conans import ConanFile
            from conans.client.tools import {}

            class Pkg(ConanFile):
                pass
            """.format(tool))
        client = TestClient()
        client.save({"conanfile.py": conanfile})
        client.run("install .")
