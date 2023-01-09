import textwrap

from conans.test.assets.genconanfile import GenConanfile
from conans.test.utils.tools import TestClient

conanfile = textwrap.dedent("""
        from conan import ConanFile
        from conan.tools.files import copy, get

        class PkgConan(ConanFile):
            name = "mylib"
            version = "1.0"

            def source(self):
                pass
    """)

def test_progress_bars_download():
    client = TestClient(default_server_user=True)
    client.save({"conanfile.py": conanfile})
    client.run("create . --name=mylib --version=1.0")
    client.run("upload * --confirm -r default")
    client.run("remove * -c")
    client.run("install --requires=mylib/1.0@ -r default")
    print(".....")
