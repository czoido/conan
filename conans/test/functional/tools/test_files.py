import os
import textwrap

import patch_ng
import pytest
from bottle import static_file

from conans.test.assets.genconanfile import GenConanfile
from conans.test.utils.test_files import temp_folder
from conans.test.utils.tools import TestClient, StoppableThreadBottle
from conans.util.files import save


class MockPatchset:
    apply_args = None

    def apply(self, root, strip, fuzz):
        self.apply_args = (root, strip, fuzz)
        return True


@pytest.fixture
def mock_patch_ng(monkeypatch):
    mock = MockPatchset()

    monkeypatch.setattr(patch_ng, "fromfile", lambda _: mock)
    return mock


class TestConanToolFiles:

    def test_imports(self):
        conanfile = GenConanfile().with_import("from conan.tools.files import load, save, "
                                               "mkdir, download, get, ftp_download")
        client = TestClient()
        client.save({"conanfile.py": conanfile})
        client.run("install .")

    def test_load_save_mkdir(self):
        conanfile = textwrap.dedent("""
            from conans import ConanFile
            from conan.tools.files import load, save, mkdir

            class Pkg(ConanFile):
                name = "mypkg"
                version = "1.0"
                def source(self):
                    mkdir(self, "myfolder")
                    save(self, "./myfolder/myfile", "some_content")
                    assert load(self, "./myfolder/myfile") == "some_content"
            """)
        client = TestClient()
        client.save({"conanfile.py": conanfile})
        client.run("source .")

    def test_download(self):
        http_server = StoppableThreadBottle()
        file_path = os.path.join(temp_folder(), "myfile.txt")
        save(file_path, "some content")

        @http_server.server.get("/myfile.txt")
        def get_file():
            return static_file(os.path.basename(file_path), os.path.dirname(file_path))

        http_server.run_server()

        profile = textwrap.dedent("""\
            [conf]
            tools.files.download:retry=1
            tools.files.download:retry_wait=0
            """)

        conanfile = textwrap.dedent("""
            import os
            from conans import ConanFile
            from conan.tools.files import download

            class Pkg(ConanFile):
                name = "mypkg"
                version = "1.0"
                def source(self):
                    download(self, "http://localhost:{}/myfile.txt", "myfile.txt")
                    assert os.path.exists("myfile.txt")
            """.format(http_server.port))

        client = TestClient()
        client.save({"conanfile.py": conanfile})
        client.save({"profile": profile})
        client.run("create . -pr=profile")


def test_patch(mock_patch_ng):
    conanfile = textwrap.dedent("""
        from conans import ConanFile
        from conan.tools.files import patch

        class Pkg(ConanFile):
            name = "mypkg"
            version = "1.0"

            def build(self):
                patch(self, patch_file='path/to/patch-file', patch_type='security')
        """)

    client = TestClient()
    client.save({"conanfile.py": conanfile})
    client.run('create .')

    assert mock_patch_ng.apply_args == (None, 0, False)
    assert 'mypkg/1.0: Apply patch (security)' in str(client.out)


def test_apply_conandata_patches(mock_patch_ng):
    conanfile = textwrap.dedent("""
        from conans import ConanFile
        from conan.tools.files import apply_conandata_patches

        class Pkg(ConanFile):
            name = "mypkg"
            version = "1.11.0"

            def build(self):
                apply_conandata_patches(self)
        """)
    conandata_yml = textwrap.dedent("""
        patches:
          "1.11.0":
            - patch_file: "patches/0001-buildflatbuffers-cmake.patch"
              base_path: "source_subfolder"
            - patch_file: "patches/0002-implicit-copy-constructor.patch"
              base_path: "source_subfolder"
              patch_type: backport
              patch_source: https://github.com/google/flatbuffers/pull/5650
              patch_description: Needed to build with modern clang compilers.
          "1.12.0":
            - patch_file: "patches/0001-buildflatbuffers-cmake.patch"
              base_path: "source_subfolder"
    """)

    client = TestClient()
    client.save({'conanfile.py': conanfile,
                 'conandata.yml': conandata_yml})
    client.run('create .')

    assert mock_patch_ng.apply_args == ('source_subfolder', 0, False)
    assert 'mypkg/1.11.0: Apply patch (backport): Needed to build with modern' \
           ' clang compilers.' in str(client.out)
