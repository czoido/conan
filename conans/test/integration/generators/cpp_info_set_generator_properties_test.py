import os
import textwrap

import pytest

from conans.test.assets.genconanfile import GenConanfile
from conans.test.utils.tools import TestClient


@pytest.fixture(scope="module")
def setup_client():
    client = TestClient()
    custom_generator = textwrap.dedent("""
        from conans.model import Generator
        from conans import ConanFile
        from conans.model.conan_generator import GeneratorComponentsMixin
        import os


        class custom_generator(GeneratorComponentsMixin, Generator):
            name = "custom_generator"
            @property
            def filename(self):
                return "my-generator.txt"

            def _get_components_custom_names(self, cpp_info):
                ret = []
                for comp_name, comp in self.sorted_components(cpp_info).items():
                    comp_genname = comp.get_property("custom_name", generator=self.name)
                    ret.append("{}:{}".format(comp.name, comp_genname))
                return ret

            @property
            def content(self):
                info = []
                for pkg_name, cpp_info in self.deps_build_info.dependencies:
                    info.append("{}:{}".format(pkg_name, cpp_info.get_property("custom_name", self.name)))
                    info.extend(self._get_components_custom_names(cpp_info))
                return os.linesep.join(info)
        """)
    client.save({"custom_generator.py": custom_generator})
    client.run("config install custom_generator.py -tf generators")

    build_module = textwrap.dedent("""
        message("I am a build module")
        """)

    another_build_module = textwrap.dedent("""
        message("I am another build module")
        """)

    client.save({"consumer.py": GenConanfile("consumer", "1.0").with_requires("mypkg/1.0").
                with_generator("custom_generator").with_generator("cmake_find_package").
                with_generator("cmake_find_package_multi").with_generator("pkg_config").
                with_setting("build_type"),
                "mypkg_bm.cmake": build_module, "mypkg_anootherbm.cmake": another_build_module})
    return client


def get_files_contents(client, filenames):
    return [client.load(f) for f in filenames]


def test_same_results_components(setup_client):
    client = setup_client
    mypkg = textwrap.dedent("""
        import os
        from conans import ConanFile, CMake, tools
        class MyPkg(ConanFile):
            settings = "build_type"
            name = "mypkg"
            version = "1.0"
            exports_sources = ["mypkg_bm.cmake"]
            def package(self):
                self.copy("mypkg_bm.cmake", dst="lib")
            def package_info(self):
                self.cpp_info.set_property("cmake_file_name", "MyFileName")
                self.cpp_info.components["mycomponent"].libs = ["mycomponent-lib"]
                self.cpp_info.components["mycomponent"].set_property("cmake_target_name", "mycomponent-name")
                self.cpp_info.components["mycomponent"].set_property("cmake_build_modules", [os.path.join("lib", "mypkg_bm.cmake")])
                self.cpp_info.components["mycomponent"].set_property("custom_name", "mycomponent-name", "custom_generator")
        """)

    client.save({"mypkg.py": mypkg})
    client.run("export mypkg.py")
    client.run("install consumer.py --build missing -s build_type=Release")

    my_generator = client.load("my-generator.txt")
    assert "mycomponent:mycomponent-name" in my_generator

    files_to_compare = ["FindMyFileName.cmake", "MyFileNameConfig.cmake", "MyFileNameTargets.cmake",
                        "MyFileNameTarget-release.cmake", "MyFileNameConfigVersion.cmake", "mypkg.pc",
                        "mycomponent.pc"]
    new_approach_contents = get_files_contents(client, files_to_compare)

    mypkg = textwrap.dedent("""
        import os
        from conans import ConanFile
        class MyPkg(ConanFile):
            settings = "build_type"
            name = "mypkg"
            version = "1.0"
            exports_sources = ["mypkg_bm.cmake"]
            def package(self):
                self.copy("mypkg_bm.cmake", dst="lib")
            def package_info(self):
                self.cpp_info.components["mycomponent"].libs = ["mycomponent-lib"]
                self.cpp_info.filenames["cmake_find_package"] = "MyFileName"
                self.cpp_info.filenames["cmake_find_package_multi"] = "MyFileName"
                self.cpp_info.components["mycomponent"].names["cmake_find_package"] = "mycomponent-name"
                self.cpp_info.components["mycomponent"].names["cmake_find_package_multi"] = "mycomponent-name"
                self.cpp_info.components["mycomponent"].build_modules.append(os.path.join("lib", "mypkg_bm.cmake"))
        """)
    client.save({"mypkg.py": mypkg})
    client.run("export mypkg.py")
    client.run("install consumer.py --build=missing -s build_type=Release")

    old_approach_contents = get_files_contents(client, files_to_compare)

    assert new_approach_contents == old_approach_contents


def test_same_results_without_components(setup_client):
    client = setup_client
    mypkg = textwrap.dedent("""
        import os
        from conans import ConanFile
        class MyPkg(ConanFile):
            settings = "build_type"
            name = "mypkg"
            version = "1.0"
            exports_sources = ["mypkg_bm.cmake"]
            def package(self):
                self.copy("mypkg_bm.cmake", dst="lib")
            def package_info(self):
                self.cpp_info.set_property("cmake_file_name", "MyFileName")
                self.cpp_info.set_property("cmake_target_name", "mypkg-name")
                self.cpp_info.set_property("cmake_build_modules",[os.path.join("lib",
                                                                 "mypkg_bm.cmake")])
                self.cpp_info.set_property("custom_name", "mypkg-name", "custom_generator")
        """)

    client.save({"mypkg.py": mypkg})
    client.run("export mypkg.py")

    client.run("install consumer.py --build missing -s build_type=Release")

    with open(os.path.join(client.current_folder, "my-generator.txt")) as custom_gen_file:
        assert "mypkg:mypkg-name" in custom_gen_file.read()

    files_to_compare = ["FindMyFileName.cmake", "MyFileNameConfig.cmake", "MyFileNameTargets.cmake",
                        "MyFileNameTarget-release.cmake", "MyFileNameConfigVersion.cmake", "mypkg.pc"]
    new_approach_contents = get_files_contents(client, files_to_compare)

    mypkg = textwrap.dedent("""
        import os
        from conans import ConanFile
        class MyPkg(ConanFile):
            settings = "build_type"
            name = "mypkg"
            version = "1.0"
            exports_sources = ["mypkg_bm.cmake"]
            def package(self):
                self.copy("mypkg_bm.cmake", dst="lib")
            def package_info(self):
                self.cpp_info.filenames["cmake_find_package"] = "MyFileName"
                self.cpp_info.filenames["cmake_find_package_multi"] = "MyFileName"
                self.cpp_info.names["cmake_find_package"] = "mypkg-name"
                self.cpp_info.names["cmake_find_package_multi"] = "mypkg-name"
                self.cpp_info.names["custom_generator"] = "mypkg-name"
                self.cpp_info.build_modules.append(os.path.join("lib", "mypkg_bm.cmake"))
        """)
    client.save({"mypkg.py": mypkg})
    client.run("create mypkg.py")
    client.run("install consumer.py -s build_type=Release")

    old_approach_contents = get_files_contents(client, files_to_compare)

    assert new_approach_contents == old_approach_contents


def test_same_results_specific_generators(setup_client):
    client = setup_client
    mypkg = textwrap.dedent("""
        import os
        from conans import ConanFile
        class MyPkg(ConanFile):
            settings = "build_type"
            name = "mypkg"
            version = "1.0"
            exports_sources = ["mypkg_bm.cmake", "mypkg_anootherbm.cmake"]
            def package(self):
                self.copy("mypkg_bm.cmake", dst="lib")
                self.copy("mypkg_anootherbm.cmake", dst="lib")
            def package_info(self):
                self.cpp_info.set_property("cmake_file_name", "MyFileName", "cmake_find_package")
                self.cpp_info.set_property("cmake_file_name", "MyFileNameMulti", "cmake_find_package_multi")
                self.cpp_info.set_property("cmake_target_name", "mypkg-name", "cmake_find_package")
                self.cpp_info.set_property("cmake_target_name", "mypkg-name-multi", "cmake_find_package_multi")
                self.cpp_info.set_property("cmake_build_modules",[os.path.join("lib",
                                                                 "mypkg_bm.cmake")], "cmake_find_package")
                self.cpp_info.set_property("cmake_build_modules",[os.path.join("lib",
                                                                 "mypkg_anootherbm.cmake")], "cmake_find_package_multi")
        """)

    client.save({"mypkg.py": mypkg})
    client.run("export mypkg.py")

    client.run("install consumer.py --build missing -s build_type=Release")

    files_to_compare = ["FindMyFileName.cmake", "MyFileNameMultiConfig.cmake", "MyFileNameMultiTargets.cmake",
                        "MyFileNameMultiTarget-release.cmake", "MyFileNameMultiConfigVersion.cmake"]
    new_approach_contents = get_files_contents(client, files_to_compare)

    mypkg = textwrap.dedent("""
        import os
        from conans import ConanFile
        class MyPkg(ConanFile):
            settings = "build_type"
            name = "mypkg"
            version = "1.0"
            exports_sources = ["mypkg_bm.cmake", "mypkg_anootherbm.cmake"]
            def package(self):
                self.copy("mypkg_bm.cmake", dst="lib")
                self.copy("mypkg_anootherbm.cmake", dst="lib")
            def package_info(self):
                self.cpp_info.filenames["cmake_find_package"] = "MyFileName"
                self.cpp_info.filenames["cmake_find_package_multi"] = "MyFileNameMulti"
                self.cpp_info.names["cmake_find_package"] = "mypkg-name"
                self.cpp_info.names["cmake_find_package_multi"] = "mypkg-name-multi"
                self.cpp_info.build_modules["cmake_find_package"].append(os.path.join("lib", "mypkg_bm.cmake"))
                self.cpp_info.build_modules["cmake_find_package_multi"].append(os.path.join("lib", "mypkg_anootherbm.cmake"))
        """)
    client.save({"mypkg.py": mypkg})
    client.run("create mypkg.py")
    client.run("install consumer.py -s build_type=Release")

    old_approach_contents = get_files_contents(client, files_to_compare)

    assert new_approach_contents == old_approach_contents


def test_cmake_find_package_new_properties():
    # test new properties support for cmake_find_package, necessary for migration in cci
    # cmake_target_name --> cmake_module_target_name
    # cmake_file_name --> cmake_module_file_name
    # https://github.com/conan-io/conan/issues/9825

    client = TestClient()

    greetings = textwrap.dedent("""
        import os
        from conans import ConanFile
        class MyPkg(ConanFile):
            settings = "build_type"
            name = "greetings"
            version = "1.0"
            def package_info(self):
                self.cpp_info.set_property("cmake_module_target_name", "MyChat")
                self.cpp_info.set_property("cmake_module_file_name", "MyChat")
                self.cpp_info.components["sayhello"].set_property("cmake_module_target_name", "MySay")
                self.cpp_info.components["sayhellobye"].set_property("cmake_module_target_name", "MySayBye")
        """)
    client.save({"greetings.py": greetings})
    client.run("create greetings.py greetings/1.0@")
    client.run("install greetings/1.0@ -g cmake_find_package")
    find_package_contents = client.load("FindMyChat.cmake")
    assert "add_library(MyChat::MyChat" in find_package_contents
    assert "set(MyChat_COMPONENTS MyChat::MySay MyChat::MySayBye)" in find_package_contents

    # check the generated files are the same with cmake_target_name and cmake_file_name
    greetings = textwrap.dedent("""
        import os
        from conans import ConanFile
        class MyPkg(ConanFile):
            settings = "build_type"
            name = "greetings"
            version = "1.0"
            def package_info(self):
                self.cpp_info.set_property("cmake_target_name", "MyChat")
                self.cpp_info.set_property("cmake_file_name", "MyChat")
                self.cpp_info.components["sayhello"].set_property("cmake_target_name", "MySay")
                self.cpp_info.components["sayhellobye"].set_property("cmake_target_name", "MySayBye")
        """)
    client.save({"greetings.py": greetings})
    client.run("create greetings.py greetings/1.0@")
    client.run("install greetings/1.0@ -g cmake_find_package")
    find_package_contents_old = client.load("FindMyChat.cmake")
    assert find_package_contents_old == find_package_contents


@pytest.mark.parametrize("generator", ["cmake_find_package_multi", "cmake_find_package"])
def test_cmake_find_package_target_namespace(generator):
    # https://github.com/conan-io/conan/issues/9946
    client = TestClient()
    hello = textwrap.dedent("""
        import os
        from conans import ConanFile
        class MyHello(ConanFile):
            settings = "build_type"
            name = "hello"
            version = "1.0"
            def package_info(self):
                self.cpp_info.components["helloworld"].set_property("cmake_target_name", "HelloWorld")
                {}

        """)

    greetings = textwrap.dedent("""
        import os
        from conans import ConanFile
        class MyPkg(ConanFile):
            settings = "build_type"
            name = "greetings"
            version = "1.0"
            requires = "hello/1.0"
            def package_info(self):
                self.cpp_info.components["greetingshello"].requires = ["hello::helloworld"]
                {}
        """)

    client.save({"hello.py": hello.format('self.cpp_info.set_property("cmake_target_namespace", "hello_namespace")'),
                 "greetings.py": greetings.format('self.cpp_info.set_property("cmake_target_namespace", "greetings_namespace")')})
    client.run("create hello.py hello/1.0@")
    client.run("create greetings.py greetings/1.0@")
    client.run("install greetings/1.0@ -g {}".format(generator))
    if generator == "cmake_find_package_multi":
        hello_config = client.load("hello-config.cmake")
        assert "set_property(TARGET hello_namespace::HelloWorld" in hello_config
        hello_targets_release = client.load("helloTarget-release.cmake")
        assert "set(hello_COMPONENTS_RELEASE hello_namespace::HelloWorld)" in hello_targets_release
        hello_target = client.load("helloTargets.cmake")
        assert "add_library(hello_namespace::HelloWorld" in hello_target
        assert "add_library(hello_namespace::hello" in hello_target
        greetings_config = client.load("greetings-config.cmake")
        assert "set_property(TARGET greetings_namespace::greetings" in greetings_config
        greetings_targets_release = client.load("greetingsTarget-release.cmake")
        assert "set(greetings_COMPONENTS_RELEASE greetings_namespace::greetingshello)" in greetings_targets_release
        greetings_target = client.load("greetingsTargets.cmake")
        assert "add_library(greetings_namespace::greetingshello INTERFACE IMPORTED)" in greetings_target
        assert "add_library(greetings_namespace::greetings INTERFACE IMPORTED)" in greetings_target
    else:
        hello_contents = client.load("Findhello.cmake")
        assert "set(hello_COMPONENTS hello_namespace::HelloWorld)" in hello_contents
        assert "add_library(hello_namespace::HelloWorld INTERFACE IMPORTED)" in hello_contents
        assert "add_library(hello_namespace::hello INTERFACE IMPORTED)" in hello_contents
        greetings_contents = client.load("Findgreetings.cmake")
        assert "set(greetings_COMPONENTS greetings_namespace::greetingshello)" in greetings_contents
        assert "add_library(greetings_namespace::greetingshello INTERFACE IMPORTED)" in greetings_contents
        assert "add_library(greetings_namespace::greetings INTERFACE IMPORTED)" in greetings_contents

    # check that the contents with the namespace that equals the default
    # generates exactly the same files
    client.save({"hello.py": hello.format('self.cpp_info.set_property("cmake_target_namespace", "hello")'),
                 "greetings.py": greetings.format('self.cpp_info.set_property("cmake_target_namespace", "greetings")')},
                clean_first=True)
    client.run("create hello.py hello/1.0@")
    client.run("create greetings.py greetings/1.0@")
    client.run("install greetings/1.0@ -g {}".format(generator))

    if generator == "cmake_find_package_multi":
        files_to_compare = ["greetings-config.cmake", "greetingsTarget-release.cmake", "greetingsTargets.cmake",
                            "hello-config.cmake", "helloTarget-release.cmake", "helloTargets.cmake"]
    else:
        files_to_compare = ["Findhello.cmake", "Findgreetings.cmake"]

    files_namespace = [client.load(file) for file in files_to_compare]

    client.save({"hello.py": hello.format(''),
                 "greetings.py": greetings.format('')},
                clean_first=True)
    client.run("create hello.py hello/1.0@")
    client.run("create greetings.py greetings/1.0@")
    client.run("install greetings/1.0@ -g {}".format(generator))

    files_no_namespace = [client.load(file) for file in files_to_compare]

    assert files_namespace == files_no_namespace


def test_legacy_cmake_is_not_affected_by_set_property_usage():
    """
    "set_property" will have no effect on "cmake" legacy generator

    Originally posted: https://github.com/conan-io/conan-center-index/issues/7925
    """

    client = TestClient()

    greetings = textwrap.dedent("""
        import os
        from conans import ConanFile
        class MyPkg(ConanFile):
            settings = "build_type"
            name = "greetings"
            version = "1.0"

            def package_info(self):
                self.cpp_info.set_property("cmake_file_name", "MyChat")
                self.cpp_info.set_property("cmake_target_name", "MyChat")
                self.cpp_info.components["sayhello"].set_property("cmake_target_name", "MySay")
        """)
    client.save({"greetings.py": greetings})
    client.run("create greetings.py greetings/1.0@")
    client.run("install greetings/1.0@ -g cmake")
    conanbuildinfo = client.load("conanbuildinfo.cmake")
    # Let's check our final target is the pkg name instead of "MyChat"
    assert "set_property(TARGET CONAN_PKG::greetings" in conanbuildinfo
    assert "add_library(CONAN_PKG::greetings" in conanbuildinfo
    assert "set(CONAN_TARGETS CONAN_PKG::greetings)" in conanbuildinfo


def test_pkg_config_names(setup_client):
    client = setup_client
    mypkg = textwrap.dedent("""
        import os
        from conans import ConanFile
        class MyPkg(ConanFile):
            settings = "build_type"
            name = "mypkg"
            version = "1.0"
            def package_info(self):
                self.cpp_info.components["mycomponent"].libs = ["mycomponent-lib"]
                self.cpp_info.components["mycomponent"].set_property("pkg_config_name", "mypkg-config-name")
        """)

    client.save({"mypkg.py": mypkg})
    client.run("export mypkg.py")
    client.run("install consumer.py --build missing")

    with open(os.path.join(client.current_folder, "mypkg-config-name.pc")) as gen_file:
        assert "mypkg-config-name" in gen_file.read()


def test_set_properties_simplified():
    client = TestClient()
    conanfile = textwrap.dedent("""
        from conans import ConanFile
        class LibcurlConan(ConanFile):
            name = "libcurl"
            version = "0.1"
            settings = "os", "arch", "compiler", "build_type"
            def package_info(self):
                self.cpp_info.set_property("cmake_target_name", "CURLNAMESPACE::CURLNAME")
                self.cpp_info.components["curl"].libs = ["libcurl"]
    """)
    client.save({"conanfile.py": conanfile})
    client.run("create .")
    client.run("install libcurl/0.1@ -g CMakeDeps")
    with open(os.path.join(client.current_folder, "libcurl-release-x86_64-data.cmake")) as data_cmake:
        # if not defined, we take the pkg name as namespace
        assert "set(libcurl_COMPONENT_NAMES ${libcurl_COMPONENT_NAMES} libcurl::curl)" in data_cmake.read()
