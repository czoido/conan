from conans.test.assets.genconanfile import GenConanfile
from conans.test.utils.tools import TestClient


def test_basic_parallel_download():
    client = TestClient(default_server_user=True)
    client.save({"conanfile.py": GenConanfile().with_exports_sources("*")})
    client.run("create . --name=mylib --version=1.0")
    client.run("upload * --confirm -r default")
    client.run("remove * -c")
    client.run("install --requires=mylib/1.0@ -r default")
    print(".....")
