import os
import unittest

from conans.model.ref import ConanFileReference
from conans.paths import CONANFILE
from conans.test.utils.tools import TestClient, GenConanfile
from conans.util.files import load


class HalfDiamondTest(unittest.TestCase):

    def setUp(self):
        self.client = TestClient()

    def _export(self, name, deps=None, export=True):

        conanfile = GenConanfile().with_name(name).with_version("0.1")\
                                  .with_option("potato", [True, False])\
                                  .with_default_option("potato", True)
        if deps:
            for dep in deps:
                ref = ConanFileReference.loads(dep)
                conanfile = conanfile.with_require(ref)

        conanfile = str(conanfile) + """
    def config_options(self):
        del self.options.potato
"""
        self.client.save({CONANFILE: conanfile}, clean_first=True)
        if export:
            self.client.run("export . lasote/stable")

    def test_check_duplicated_full_requires(self):
        self._export("Hello0")
        self._export("Hello1", ["Hello0/0.1@lasote/stable"])
        self._export("Hello2", ["Hello1/0.1@lasote/stable", "Hello0/0.1@lasote/stable"],
                     export=False)

        self.client.run("create . --build missing")
        self.assertIn("Hello2/0.1: Generated conaninfo.txt",
                      self.client.out)

        ref = ConanFileReference.loads("Hello2/0.1@")
        pkg_folder = self.client.cache.package_layout(ref).packages()
        folders = os.listdir(pkg_folder)
        pkg_folder = os.path.join(pkg_folder, folders[0])
        conaninfo = self.client.load(os.path.join(pkg_folder, "conaninfo.txt"))

        self.assertEqual(1, conaninfo.count("Hello0/0.1@lasote/stable"))
