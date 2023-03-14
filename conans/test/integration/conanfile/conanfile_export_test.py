import os
import platform
import shutil
import textwrap

import pytest

from conans.client.tools import environment_append
from conans.test.utils.tools import TestClient


@pytest.mark.skipif(platform.system() == "Windows", reason="...")
def test_inherited_baseclass():

    c = TestClient()

    conanfile_base = textwrap.dedent("""
        from conan import ConanFile
        import os

        class Base(ConanFile):
            version = "0.1"

            def export(self):
                self.copy('*', src=os.path.dirname(__file__), dst=self.export_folder)
                assert os.path.isfile( os.path.join(self.export_folder, os.path.basename(__file__)) )

            def build(self):
                self.output.info(f"build of {self.name}")

            def package_info(self):
                self.output.info(f"package_info of {self.name}")
                self.output.info(f"using conanfile_base {__file__}")
    """)

    conanfile_pkg = textwrap.dedent("""
        import conanfile_base

        class Pkg(conanfile_base.Base):
            name = "{name}"
            exports = "conanfile_base.py"

    """)

    conanfile_app = textwrap.dedent("""
        import conanfile_base

        class Pkg(conanfile_base.Base):
            name = "app"
            exports = "conanfile_base.py"

            def requirements(self):
                self.requires("pkg1/0.1")
                self.requires("pkg2/0.1")
                self.output.info(f"using conanfile_base {conanfile_base.__file__}")
    """)

    c.save({"pkg1/conanfile.py": conanfile_pkg.format(name="pkg1"),
            "pkg2/conanfile.py": conanfile_pkg.format(name="pkg2"),
            "base/conanfile_base.py": conanfile_base,
            "app/conanfile.py": conanfile_app})

    base_path = os.path.join(c.current_folder, "base")
    app_path = os.path.join(c.current_folder, "app")

    # copy the base python file to all projects that use that
    # you can do this easily with a scripts that reads the
    # conanfile and detect the recipes that are importing the
    # base module
    shutil.copyfile(os.path.join(c.current_folder, "base", "conanfile_base.py"),
                    os.path.join(c.current_folder, "pkg1", "conanfile_base.py"))
    shutil.copyfile(os.path.join(c.current_folder, "base", "conanfile_base.py"),
                    os.path.join(c.current_folder, "pkg2", "conanfile_base.py"))
    shutil.copyfile(os.path.join(c.current_folder, "base", "conanfile_base.py"),
                    os.path.join(c.current_folder, "app", "conanfile_base.py"))

    c.run("export pkg1")
    c.run("export pkg2")
    c.run("install app --build=missing")
    print(c.out)

    assert f"pkg1/0.1: build of pkg1" in c.out
    assert f"pkg1/0.1: package_info of pkg1" in c.out
    assert f"pkg1/0.1: using conanfile_base {c.cache_folder}/data/pkg1/0.1/_/_/export/conanfile_base.py" in c.out

    assert f"pkg2/0.1: package_info of pkg2" in c.out
    assert f"pkg2/0.1: build of pkg2" in c.out
    assert f"pkg2/0.1: using conanfile_base {c.cache_folder}/data/pkg2/0.1/_/_/export/conanfile_base.py" in c.out

    assert f"conanfile.py (app/0.1): using conanfile_base {app_path}/conanfile_base.py" in c.out

    # you could clean after this
    os.remove(os.path.join(c.current_folder, "pkg1", "conanfile_base.py"))
    os.remove(os.path.join(c.current_folder, "pkg2", "conanfile_base.py"))
    os.remove(os.path.join(c.current_folder, "app", "conanfile_base.py"))


def test_inherited_baseclass_importing():

    c = TestClient()

    conanfile_base = textwrap.dedent("""
        import os
        from conan import ConanFile
        from conan.tools.files import copy

        class Base(ConanFile):
            version = "0.1"
            def export(self):
                copy(self, '*', src=self.recipe_folder, dst=self.export_folder)
            def package_info(self):
                self.output.info(f"package_info of {self.name}")
                assert os.path.dirname(__file__) == self.recipe_folder
    """)

    conanfile_pkg = textwrap.dedent("""
        import shutil, os
        try:
            current = os.path.dirname(__file__)
            shutil.copy2(os.path.join(current, "..", "base", "conanfile_base.py"), current)
        except Exception as e:
            pass

        import conanfile_base
        class Pkg(conanfile_base.Base):
            name = "{name}"
            # version and export is inherited
    """)

    conanfile_app = textwrap.dedent("""
        import shutil, os
        try:
            current = os.path.dirname(__file__)
            shutil.copy2(os.path.join(current, "..", "base", "conanfile_base.py"), current)
        except Exception as e:
            pass

        import conanfile_base
        class Pkg(conanfile_base.Base):
            name = "app"
            def requirements(self):
                self.requires("pkg1/0.1")
                self.requires("pkg2/0.1")
    """)

    c.save({"pkg1/conanfile.py": conanfile_pkg.format(name="pkg1"),
            "pkg2/conanfile.py": conanfile_pkg.format(name="pkg2"),
            "base/conanfile_base.py": conanfile_base,
            "app/conanfile.py": conanfile_app})

    c.run("export pkg1")
    c.run("export pkg2")
    c.run("install app --build=missing")

    assert f"pkg1/0.1: package_info of pkg1" in c.out
    assert f"pkg2/0.1: package_info of pkg2" in c.out
