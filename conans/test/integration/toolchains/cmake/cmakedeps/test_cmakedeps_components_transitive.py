import os
import platform
import textwrap


from conans.test.utils.tools import TestClient


def test_cmakedeps_propagate_components():
    """
    lib_a: has two components cmp1, cmp2, cmp3
    lib_b --> libA cmp1
    lib_c --> libA cmp2
    consumer --> libB, libC
    """
    client = TestClient()
    lib_a = textwrap.dedent("""
        import os
        from conan import ConanFile
        from conan.tools.files import copy

        class lib_aConan(ConanFile):
            name = "lib_a"
            version = "1.0"
            settings = "os", "compiler", "build_type", "arch"
            exports_sources = "include/*"

            def package(self):
                copy(self, "*.h", os.path.join(self.source_folder, "include"),
                                  os.path.join(self.package_folder, "include"))

            def package_info(self):
                self.cpp_info.components["cmp1"].includedirs = ["include"]
                self.cpp_info.components["cmp2"].includedirs = ["include"]
                self.cpp_info.components["cmp3"].includedirs = ["include"]
        """)

    cmp_include = textwrap.dedent("""
        #pragma once
        #include <iostream>
        void {cmpname}(){{ std::cout << "{cmpname}" << std::endl; }};
        """)

    client.save({
        'lib_a/conanfile.py': lib_a,
        'lib_a/include/cmp1.h': cmp_include.format(cmpname="cmp1"),
        'lib_a/include/cmp2.h': cmp_include.format(cmpname="cmp2"),
        'lib_a/include/cmp3.h': cmp_include.format(cmpname="cmp3"),
    })

    client.run("create lib_a")

    lib = textwrap.dedent("""
        import os
        from conan import ConanFile
        from conan.tools.files import copy


        class lib_{name}Conan(ConanFile):
            name = "lib_{name}"
            version = "1.0"
            settings = "os", "compiler", "build_type", "arch"
            exports_sources = "include/*"

            def requirements(self):
                self.requires("lib_a/1.0", components={components})

            def package(self):
                copy(self, "*.h", os.path.join(self.source_folder, "include"),
                                  os.path.join(self.package_folder, "include"))

        """)

    lib_include = textwrap.dedent("""
        #pragma once
        #include <iostream>
        #include {include}
        void lib_{name}(){{ {components} }};
        """)


    client.save({
        'lib_b/conanfile.py': lib.format(name="b", components='["cmp1"]'),
        'lib_b/include/lib_b.h': lib_include.format(name="b", include='"cmp1.h"', components='cmp1();'),
    })

    client.save({
        'lib_c/conanfile.py': lib.format(name="c", components='["cmp2"]'),
        'lib_c/include/lib_c.h': lib_include.format(name="c", include='"cmp2.h"', components='cmp2();'),
    })

    client.run("create lib_b")

    client.run("create lib_c")

    consumer = textwrap.dedent("""
    from conan import ConanFile

    class ConsumerConan(ConanFile):
        name = "consumer"
        version = "1.0"
        settings = "os", "compiler", "build_type", "arch"
        generators = "CMakeDeps"
        def requirements(self):
            self.requires("lib_b/1.0")
            self.requires("lib_c/1.0")
    """)

    client.save({'consumer/conanfile.py': consumer})

    client.run("install consumer")

    """
    By default if you specify self.requires("lib_a/1.0", components=["cmp1"])
    That would go as well to the self.cpp_info.requires and mean: self.cpp_info.requires = ["top::cmp1"]
    But there are cases that you may require several components but decide to only make available for
    consumers with the cpp_info some of them
    """

    assert "lib_a::cmp2" not in client.load(os.path.join("consumer", "lib_a-release-x86_64-data.cmake"))
    assert "lib_a::cmp2" not in client.load(os.path.join("consumer", "lib_a-Target-release.cmake"))
