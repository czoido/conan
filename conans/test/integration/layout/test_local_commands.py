import os
import textwrap

from conans.model.ref import ConanFileReference, PackageReference
from conans.test.assets.genconanfile import GenConanfile
from conans.test.utils.tools import TestClient


def test_local_build():
    """If we configure a build folder in the layout, the installed files in a "conan build ."
    go to the specified folder: "my_build"
    """
    # FIXME: The configure is not valid to change the layout, we need the settings and options
    #        ready
    client = TestClient()
    conan_file = str(GenConanfile().with_import("from conans import tools"))
    conan_file += """

    def configure(self):
        self.layout.build.folder = "my_build"

    def build(self):
        tools.save("build_file.dll", "bar")

"""
    client.save({"conanfile.py": conan_file})
    client.run("install . -if=my_install")
    # FIXME: This should change to "build ." when "conan build" computes the graph
    client.run("build . -if=my_install")
    dll = os.path.join(client.current_folder, "my_build", "build_file.dll")
    assert os.path.exists(dll)


def test_local_build_change_base():
    """If we configure a build folder in the layout, the build files in a "conan build ."
    go to the specified folder: "my_build under the modified base one "common"
    """
    # FIXME: The configure is not valid to change the layout, we need the settings and options
    #        ready
    client = TestClient()
    conan_file = str(GenConanfile().with_import("from conans import tools"))
    conan_file += """
    def configure(self):
        self.layout.build.folder = "my_build"
    def build(self):
        tools.save("build_file.dll", "bar")
    """
    client.save({"conanfile.py": conan_file})
    client.run("install . -if=common")
    client.run("build . -if=common -bf=common")
    dll = os.path.join(client.current_folder, "common", "my_build", "build_file.dll")
    assert os.path.exists(dll)


def test_local_source():
    """If we configure a source folder in the layout, the downloaded files in a "conan source ."
    go to the specified folder: "my_source"
    """
    # FIXME: The configure is not valid to change the layout, we need the settings and options
    #        ready
    client = TestClient()
    conan_file = str(GenConanfile().with_import("from conans import tools"))
    conan_file += """
    def configure(self):
        self.layout.source.folder = "my_source"

    def source(self):
        tools.save("downloaded.h", "bar")
    """
    client.save({"conanfile.py": conan_file})
    client.run("install . -if=my_install")
    # FIXME: This should change to "source ." when "conan source" computes the graph
    client.run("source .")
    header = os.path.join(client.current_folder, "my_source", "downloaded.h")
    assert os.path.exists(header)


def test_local_source_change_base():
    """If we configure a source folder in the layout, the souce files in a "conan source ."
    go to the specified folder: "my_source under the modified base one "all_source"
    """
    # FIXME: The configure is not valid to change the layout, we need the settings and options
    #        ready
    client = TestClient()
    conan_file = str(GenConanfile().with_import("from conans import tools"))
    conan_file += """
    def configure(self):
        self.layout.source.folder = "my_source"

    def source(self):
        tools.save("downloaded.h", "bar")
    """
    client.save({"conanfile.py": conan_file})
    client.run("install . -if=common")
    client.run("source . -sf=common")
    header = os.path.join(client.current_folder, "common", "my_source", "downloaded.h")
    assert os.path.exists(header)


def test_export_pkg():
    """The export-pkg, calling the "package" method, follows the layout if `cache_package_layout` """
    # FIXME: The configure is not valid to change the layout, we need the settings and options
    #        ready
    client = TestClient()
    conan_file = textwrap.dedent("""
        from conans import ConanFile
        from conans import tools

        class HelloConan(ConanFile):
            no_copy_source = True

            def configure(self):
                self.layout.source.folder = "my_source"
                self.layout.build.folder = "my_build"

            def source(self):
                tools.save("downloaded.h", "bar")

            def build(self):
                tools.save("library.lib", "bar")
                tools.save("generated.h", "bar")

            def package(self):
                self.output.warn("Source folder: {}".format(self.source_folder))
                self.output.warn("Build folder: {}".format(self.build_folder))
                self.output.warn("Package folder: {}".format(self.package_folder))
                self.copy("*.h")
                self.copy("*.lib")
        """)

    client.save({"conanfile.py": conan_file})
    client.run("install . -if=my_install")
    client.run("source .")
    client.run("build . -if=my_install")
    client.run("export-pkg . lib/1.0@")
    ref = ConanFileReference.loads("lib/1.0@")
    pref = PackageReference(ref, "5ab84d6acfe1f23c4fae0ab88f26e3a396351ac9")
    sf = os.path.join(client.current_folder, "my_source")
    bf = os.path.join(client.current_folder, "my_build")
    pf = client.cache.package_layout(ref).package(pref)

    assert "WARN: Source folder: {}".format(sf) in client.out
    assert "WARN: Build folder: {}".format(bf) in client.out
    assert "WARN: Package folder: {}".format(pf) in client.out

    # Check the artifacts packaged
    assert os.path.exists(os.path.join(pf, "generated.h"))
    assert os.path.exists(os.path.join(pf, "library.lib"))


def test_export_pkg_local():
    """The export-pkg, without calling "package" method, with local package, follows the layout"""
    # FIXME: The configure is not valid to change the layout, we need the settings and options
    #        ready
    client = TestClient()
    conan_file = textwrap.dedent("""
        from conans import ConanFile
        from conans import tools

        class HelloConan(ConanFile):
            no_copy_source = True

            def configure(self):
                self.layout.source.folder = "my_source"
                self.layout.build.folder = "my_build"

            def source(self):
                tools.save("downloaded.h", "bar")

            def build(self):
                tools.save("library.lib", "bar")
                tools.save("generated.h", "bar")

            def package(self):
                self.output.warn("Source folder: {}".format(self.source_folder))
                self.output.warn("Build folder: {}".format(self.build_folder))
                self.output.warn("Package folder: {}".format(self.package_folder))
                self.copy("*.h")
                self.copy("*.lib")
        """)

    client.save({"conanfile.py": conan_file})
    client.run("install . -if=my_install")
    client.run("source .")
    client.run("build .")

    client.run("export-pkg . lib/1.0@")
    sf = os.path.join(client.current_folder, "my_source")
    bf = os.path.join(client.current_folder, "my_build")
    assert "WARN: Source folder: {}".format(sf) in client.out
    assert "WARN: Build folder: {}".format(bf) in client.out

    ref = ConanFileReference.loads("lib/1.0@")
    pref = PackageReference(ref, "5ab84d6acfe1f23c4fae0ab88f26e3a396351ac9")
    pf_cache = client.cache.package_layout(ref).package(pref)

    # Check the artifacts packaged
    assert os.path.exists(os.path.join(pf_cache, "generated.h"))
    assert os.path.exists(os.path.join(pf_cache, "library.lib"))
