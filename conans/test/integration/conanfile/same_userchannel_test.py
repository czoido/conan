import unittest

import pytest

from conans.test.assets.genconanfile import GenConanfile
from conans.test.utils.tools import TestClient


class UserChannelTestPackage(unittest.TestCase):

    def test(self):
        # https://github.com/conan-io/conan/issues/2501
        client = TestClient()
        conanfile = """from conans import ConanFile
class SayConan(ConanFile):
    pass
"""
        test = """from conans import ConanFile
class SayConan(ConanFile):
    def requirements(self):
        self.output.info("USER: %s!!" % self.user)
        self.output.info("CHANNEL: %s!!" % self.channel)

    def test(self):
        pass
"""

        client.save({"conanfile.py": conanfile,
                     "test_package/conanfile.py": test})
        client.run("create . Pkg/0.1@conan/testing")
        self.assertIn("Pkg/0.1@conan/testing (test package): USER: conan!!", client.out)
        self.assertIn("Pkg/0.1@conan/testing (test package): CHANNEL: testing!!", client.out)


class SameUserChannelTest(unittest.TestCase):

    def setUp(self):
        self.client = TestClient()
        conanfile = """
from conans import ConanFile

class SayConan(ConanFile):
    name = "Say"
    version = "0.1"
    build_policy = "missing"

    def build(self):
        self.output.info("Building %s")
"""
        for channel in ("lasote/stable", "other/testing"):
            self.client.save({"conanfile.py": conanfile % channel})
            self.client.run("export . %s" % channel)

        self.conanfile = """
from conans import ConanFile

class HelloConan(ConanFile):
    name = "Hello"
    version = "0.1"
    build_policy = "missing"

    def requirements(self):
        user_channel = "{}/{}".format(self.user, self.channel) if self.user else ""
        self.requires("Say/0.1@{}".format(user_channel))

    def build(self):
        self.output.info("Building %s/%s" % (self.user, self.channel) )
"""

        self.test_conanfile = str(GenConanfile().with_test("pass"))
        self.client.save({"conanfile.py": self.conanfile,
                          "test/conanfile.py": self.test_conanfile})

    def test_create(self):
        self.client.run("create . lasote/stable")
        self.assertIn("Say/0.1@lasote/stable: Building lasote/stable", self.client.out)
        self.assertIn("Hello/0.1@lasote/stable: Building lasote/stable", self.client.out)
        self.assertNotIn("other/testing", self.client.out)

        self.client.save({"conanfile.py": self.conanfile,
                          "test/conanfile.py": self.test_conanfile.replace("lasote/stable",
                                                                           "other/testing")})
        self.client.run("create . other/testing")
        self.assertIn("Say/0.1@other/testing: Building other/testing", self.client.out)
        self.assertIn("Hello/0.1@other/testing: Building other/testing", self.client.out)
        self.assertNotIn("lasote/stable", self.client.out)

    def test_local_commands(self):
        self.client.run("install .", assert_error=True)
        self.assertIn("ERROR: Package 'Say/0.1' not resolved: No remote defined",
                      self.client.out)

        self.client.run("install . @lasote/stable")
        self.assertIn("Say/0.1@lasote/stable: Building lasote/stable", self.client.out)
        self.assertNotIn("other/testing", self.client.out)

        self.client.run("install . @other/testing")
        self.assertIn("Say/0.1@other/testing: Building other/testing", self.client.out)
        self.assertNotIn("lasote/stable", self.client.out)

        # Now use the default_ methods to declare user and channel
        self.client = TestClient()
        conanfile = """
from conans import ConanFile

class SayConan(ConanFile):
    name = "Say"
    version = "0.1"
    build_policy = "missing"
    user = "userfoo"

    def build(self):
        self.output.info("Building %s/%s" % (self.user, self.channel) )

    @property
    def channel(self):
        return "channelbar"
"""
        self.client.save({"conanfile.py": conanfile})
        self.client.run("install .")
        self.client.run("build .")
        self.assertIn("Building userfoo/channelbar", self.client.out)


@pytest.mark.xfail(reason="Using env-vars to define user/channel will be removed")
class BuildRequireUserChannelTest(unittest.TestCase):
    def test(self):
        # https://github.com/conan-io/conan/issues/2254
        client = TestClient()
        conanfile = """
from conans import ConanFile

class SayConan(ConanFile):
    def build_requirements(self):
        self.output.info("MYUSER: %s" % self.user)
        self.output.info("MYCHANNEL: %s" % self.channel)
"""
        client.save({"conanfile.py": conanfile})
        client.run("install . @myuser/mychannel")
        self.assertIn("MYUSER: myuser", client.out)
        self.assertIn("MYCHANNEL: mychannel", client.out)
