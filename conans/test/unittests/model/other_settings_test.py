import os
import textwrap
import unittest

import pytest

from conans.model.info import ConanInfo
from conans.model.ref import PackageReference, ConanFileReference
from conans.model.settings import bad_value_msg, undefined_value
from conans.paths import CONANFILE, CONANINFO
from conans.test.assets.genconanfile import GenConanfile
from conans.test.utils.tools import TestClient
from conans.util.files import load, save


class SettingsTest(unittest.TestCase):

    def _get_conaninfo(self, reference, client):
        ref = client.cache.get_latest_rrev(ConanFileReference.loads(reference))
        pkg_ids = client.cache.get_package_ids(ref)
        pref = client.cache.get_latest_prev(pkg_ids[0])
        pkg_folder = client.cache.pkg_layout(pref).package()
        return ConanInfo.loads(client.load(os.path.join(pkg_folder, "conaninfo.txt")))

    def test_wrong_settings(self):
        settings = """os:
    None:
        subsystem: [None, msys]
"""
        client = TestClient()
        save(client.cache.settings_path, settings)
        save(client.cache.default_profile_path, "")
        conanfile = """from conans import ConanFile
class Pkg(ConanFile):
    settings = "os", "compiler"
"""
        client.save({"conanfile.py": conanfile})
        client.run("create . Pkg/0.1@lasote/testing", assert_error=True)
        self.assertIn("ERROR: settings.yml: None setting can't have subsettings", client.out)

    @pytest.mark.xfail(reason="Working in the PackageID broke this")
    def test_custom_compiler_preprocessor(self):
        # https://github.com/conan-io/conan/issues/3842
        settings = """compiler:
    mycomp:
        version: ["2.3", "2.4"]
cppstd: [None, 98, gnu98, 11, gnu11, 14, gnu14, 17, gnu17, 20, gnu20]
"""
        client = TestClient()
        save(client.cache.settings_path, settings)
        save(client.cache.default_profile_path, """[settings]
compiler=mycomp
compiler.version=2.3
cppstd=11
""")
        conanfile = """from conans import ConanFile
class Pkg(ConanFile):
    settings = "compiler", "cppstd"
"""
        client.save({"conanfile.py": conanfile})
        client.run("create . Pkg/0.1@lasote/testing")
        self.assertIn("""Configuration (profile_host):
[settings]
compiler=mycomp
compiler.version=2.3
cppstd=11""", client.out)
        self.assertIn("Pkg/0.1@lasote/testing: Package "
                      "'c2f0c2641722089d9b11cd646c47d239af044b5a' created",
                      client.out)

    @pytest.mark.xfail(reason="Working in the PackageID broke this")
    def test_custom_settings(self):
        settings = textwrap.dedent("""\
            os:
                None:
                Windows:
                    subsystem: [None, cygwin]
                Linux:
            compiler: [gcc, visual]
            """)
        client = TestClient()
        save(client.cache.settings_path, settings)
        save(client.cache.default_profile_path, "")

        client.save({"conanfile.py": GenConanfile().with_settings("os", "compiler")})
        client.run("create . Pkg/0.1@lasote/testing -s compiler=gcc")
        self.assertIn("544c1d8c53e9d269737e68e00ec66716171d2704", client.out)
        client.run("search Pkg/0.1@lasote/testing")
        self.assertNotIn("os: None", client.out)
        pref = PackageReference.loads("Pkg/0.1@lasote/testing:"
                                      "544c1d8c53e9d269737e68e00ec66716171d2704")
        info_path = os.path.join(client.get_latest_pkg_layout(pref).package(), CONANINFO)
        info = load(info_path)
        self.assertNotIn("os", info)
        # Explicitly specifying None, put it in the conaninfo.txt, but does not affect the hash
        client.run("create . Pkg/0.1@lasote/testing -s compiler=gcc -s os=None")
        self.assertIn("544c1d8c53e9d269737e68e00ec66716171d2704", client.out)
        client.run("search Pkg/0.1@lasote/testing")
        self.assertIn("os: None", client.out)
        info = load(info_path)
        self.assertIn("os", info)

    @pytest.mark.xfail(reason="Working in the PackageID broke this")
    def test_update_settings(self):
        # This test is to validate that after adding a new settings, that allows a None
        # value, this None value does not modify exisisting packages SHAs
        client = TestClient()
        save(client.cache.default_profile_path, "")
        save(client.cache.settings_path, textwrap.dedent("""
            os: [Windows, Linux]
            arch: [None, x86]
            """))

        client.save({"conanfile.py": GenConanfile().with_settings("os")})
        client.run("create . test/1.9@lasote/testing -s os=Windows")
        assert "test/1.9@lasote/testing:3475bd55b91ae904ac96fde0f106a136ab951a5e" in client.out

        # Now the new one, adding a new setting that allows none
        client.save({"conanfile.py": GenConanfile().with_settings("os", "arch")})
        client.run("create . test/1.9@lasote/testing -s os=Windows -s arch=None")
        assert "test/1.9@lasote/testing:3475bd55b91ae904ac96fde0f106a136ab951a5e" in client.out

    def test_settings_constraint_error_type(self):
        # https://github.com/conan-io/conan/issues/3022
        conanfile = """from conans import ConanFile
class Test(ConanFile):
    settings = {"os": "Linux"}
    def build(self):
        self.output.info("OS!!: %s" % self.settings.os)
    """
        client = TestClient()
        client.save({"conanfile.py": conanfile})
        client.run("create . Pkg/0.1@user/testing -s os=Linux")
        self.assertIn("Pkg/0.1@user/testing: OS!!: Linux", client.out)

    def test_settings_as_a_str(self):
        content = """
from conans import ConanFile

class SayConan(ConanFile):
    name = "Say"
    version = "0.1"
    settings = "os"
"""
        client = TestClient()
        client.save({CONANFILE: content})
        client.run("create . -s os=Windows --build missing")
        # Now read the conaninfo and verify that settings applied is only os and value is windows
        conan_info = self._get_conaninfo("Say/0.1@", client)
        self.assertEqual(conan_info.settings.os, "Windows")

        client.run("remove Say/0.1 -f")
        client.run("create . -s os=Linux --build missing")
        # Now read the conaninfo and verify that settings applied is only os and value is windows
        conan_info = self._get_conaninfo("Say/0.1@", client)
        self.assertEqual(conan_info.settings.os, "Linux")

    def test_settings_as_a_list_conanfile(self):
        # Now with conanfile as a list
        content = """
from conans import ConanFile

class SayConan(ConanFile):
    name = "Say"
    version = "0.1"
    settings = "os", "arch"
"""
        client = TestClient()
        client.save({CONANFILE: content})
        client.run("create . -s os=Windows --build missing")
        conan_info = self._get_conaninfo("Say/0.1@", client)
        self.assertEqual(conan_info.settings.os,  "Windows")
        self.assertEqual(conan_info.settings.fields, ["arch", "os"])

    def test_settings_as_a_dict_conanfile(self):
        # Now with conanfile as a dict
        # XXX: this test only works on machines w default arch "x86", "x86_64", "sparc" or "sparcv9"
        content = """
from conans import ConanFile

class SayConan(ConanFile):
    name = "Say"
    version = "0.1"
    settings = {"os": ["Windows"], "arch": ["x86", "x86_64", "sparc", "sparcv9"]}
"""
        client = TestClient()
        client.save({CONANFILE: content})
        client.run("create . -s os=Windows --build missing")
        conan_info = self._get_conaninfo("Say/0.1@", client)
        self.assertEqual(conan_info.settings.os,  "Windows")
        self.assertEqual(conan_info.settings.fields, ["arch", "os"])

    def test_invalid_settings2(self):
        # MISSING A DEFAULT VALUE BECAUSE ITS RESTRICTED TO OTHER, SO ITS REQUIRED
        content = """
from conans import ConanFile

class SayConan(ConanFile):
    name = "Say"
    version = "0.1"
    settings = {"os": ["Windows", "Linux", "Macos", "FreeBSD", "SunOS"],
                "compiler": ["Visual Studio"]}
"""
        client = TestClient()
        client.save({CONANFILE: content})
        client.run("install . -s compiler=gcc -s compiler.version=4.8 --build missing",
                   assert_error=True)
        self.assertIn(bad_value_msg("settings.compiler", "gcc", ["Visual Studio"]),
                      str(client.out))

    def test_invalid_settings3(self):
        # dict without options
        content = """
from conans import ConanFile

class SayConan(ConanFile):
    name = "Say"
    version = "0.1"
    settings = {"os": None, "compiler": ["Visual Studio"]}
"""
        client = TestClient()
        client.save({CONANFILE: content})
        client.run("install . -s compiler=gcc -s compiler.version=4.8 --build missing",
                   assert_error=True)
        self.assertIn(bad_value_msg("settings.compiler", "gcc", ["Visual Studio"]),
                      str(client.out))

        # Test wrong settings in conanfile
        content = textwrap.dedent("""
            from conans import ConanFile

            class SayConan(ConanFile):
                settings = invalid
            """)

        client.save({CONANFILE: content})
        client.run("install . --build missing", assert_error=True)
        self.assertIn("invalid' is not defined", client.out)

        # Test wrong values in conanfile
    def test_invalid_settings4(self):
        content = """
from conans import ConanFile

class SayConan(ConanFile):
    name = "Say"
    version = "0.1"
    settings = "os"
"""
        client = TestClient()
        client.save({CONANFILE: content})
        client.run("create . -s os=ChromeOS --build missing", assert_error=True)
        self.assertIn(bad_value_msg("settings.os", "ChromeOS",
                                    ['AIX', 'Android', 'Arduino', 'Emscripten', 'FreeBSD', 'Linux', 'Macos', 'Neutrino',
                                     'SunOS', 'Windows', 'WindowsCE', 'WindowsStore', 'iOS', 'tvOS', 'watchOS']),
                      client.out)

        # Now add new settings to config and try again
        config = load(client.cache.settings_path)
        config = config.replace("Windows:%s" % os.linesep,
                                "Windows:%s    ChromeOS:%s" % (os.linesep, os.linesep))

        save(client.cache.settings_path, config)
        client.run("create . -s os=ChromeOS --build missing")
        self.assertIn('Generated conaninfo.txt', client.out)

        # Settings is None
        content = """
from conans import ConanFile

class SayConan(ConanFile):
    name = "Say"
    version = "0.1"
    settings = None
"""
        client.save({CONANFILE: content})
        client.run("remove Say/0.1@ -f")
        client.run("create . --build missing")
        self.assertIn('Generated conaninfo.txt', client.out)
        conan_info = self._get_conaninfo("Say/0.1@", client)
        self.assertEqual(conan_info.settings.dumps(), "")

        # Settings is {}
        content = """
from conans import ConanFile

class SayConan(ConanFile):
    name = "Say"
    version = "0.1"
    settings = {}
"""
        client.save({CONANFILE: content})
        client.run("remove Say/0.1@ -f")
        client.run("create . --build missing")
        self.assertIn('Generated conaninfo.txt', client.out)

        conan_info = self._get_conaninfo("Say/0.1@", client)

        self.assertEqual(conan_info.settings.dumps(), "")
