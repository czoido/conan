import os
import platform
import unittest

import pytest

from conans.model.info import ConanInfo
from conans.paths import CONANINFO
from conans.test.assets.cpp_test_files import cpp_hello_conan_files
from conans.test.utils.tools import TestClient
from conans.util.files import load


@pytest.mark.slow
class BasicBuildTest(unittest.TestCase):

    @pytest.mark.tool_cmake
    def test_build_cmake(self):
        for cmd, lang, static, pure_c in [("build .", 0, True, True),
                                          ("build . -o language=1 -o static=False", 1,
                                           False, False)]:
            build(self, cmd, static, pure_c, use_cmake=True, lang=lang)

    @pytest.mark.tool_compiler
    def test_build_default(self):
        """ build default (gcc in nix, VS in win) """
        if platform.system() == "SunOS":
            return  # If is using sun-cc the gcc generator doesn't work

        for cmd, lang, static, pure_c in [("build .", 0, True, True),
                                          ("build . -o language=1 -o static=False", 1,
                                           False, False)]:
            build(self, cmd, static, pure_c, use_cmake=False, lang=lang)


def build(tester, cmd, static, pure_c, use_cmake, lang):
    client = TestClient()
    files = cpp_hello_conan_files("Hello0", "0.1", pure_c=pure_c, use_cmake=use_cmake)

    client.save(files)
    client.run(cmd)
    ld_path = ("LD_LIBRARY_PATH=`pwd`"
               if not static and not platform.system() == "Windows" else "")
    if platform.system() == "Darwin":
        ld_path += ' DYLD_LIBRARY_PATH="%s"' % os.path.join(client.current_folder, 'lib')
    command = os.sep.join([".", "bin", "say_hello"])
    client.run_command("%s %s" % (ld_path, command))
    msg = "Hello" if lang == 0 else "Hola"
    tester.assertIn("%s Hello0" % msg, client.out)
