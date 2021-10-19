import textwrap

import pytest

from conans.test.utils.tools import TestClient


@pytest.fixture
def client():
    client = TestClient()
    conanfile = textwrap.dedent("""
        from conans import ConanFile

        class Pkg(ConanFile):
            def package_id(self):
                self.info.conf = self.conf
        """)
    client.save({"conanfile.py": conanfile})
    return client


def test_package_id(client):
    profile1 = textwrap.dedent("""\
        [conf]
        tools.microsoft.msbuild:verbosity=Quiet""")
    profile2 = textwrap.dedent("""\
        [conf]
        tools.microsoft.msbuild:verbosity=Minimal""")
    client.save({"profile1": profile1,
                 "profile2": profile2})
    client.run("create . pkg/0.1@ -pr=profile1")
    assert "pkg/0.1:27eb20f75134a24f81db47d2a38d6edca921d123 - Build" in client.out
    client.run("create . pkg/0.1@ -pr=profile2")
    assert "pkg/0.1:a1eb1a27682c49deaa60371bf61aa894feed12bd - Build" in client.out
