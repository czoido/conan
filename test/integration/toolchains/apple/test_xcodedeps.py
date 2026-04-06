import os
import platform
import re
import textwrap

import pytest

from conan.test.assets.genconanfile import GenConanfile
from test.integration.toolchains.apple.test_xcodetoolchain import _get_filename
from conan.test.utils.tools import TestClient

_expected_dep_xconfig = [
    "SYSTEM_HEADER_SEARCH_PATHS = $(inherited) $(SYSTEM_HEADER_SEARCH_PATHS_{name}_{name})",
    "GCC_PREPROCESSOR_DEFINITIONS = $(inherited) $(GCC_PREPROCESSOR_DEFINITIONS_{name}_{name})",
    "OTHER_CFLAGS = $(inherited) $(OTHER_CFLAGS_{name}_{name})",
    "OTHER_CPLUSPLUSFLAGS = $(inherited) $(OTHER_CPLUSPLUSFLAGS_{name}_{name})",
    "FRAMEWORK_SEARCH_PATHS = $(inherited) $(FRAMEWORK_SEARCH_PATHS_{name}_{name})",
    "LIBRARY_SEARCH_PATHS = $(inherited) $(LIBRARY_SEARCH_PATHS_{name}_{name})",
    "OTHER_LDFLAGS = $(inherited) $(OTHER_LDFLAGS_{name}_{name})",
]

_expected_conf_xconfig = [
    "SYSTEM_HEADER_SEARCH_PATHS_{name}_{name}[config={configuration}][arch={architecture}][sdk={sdk}{sdk_version}] = ",
    "GCC_PREPROCESSOR_DEFINITIONS_{name}_{name}[config={configuration}][arch={architecture}][sdk={sdk}{sdk_version}] = ",
    "OTHER_CFLAGS_{name}_{name}[config={configuration}][arch={architecture}][sdk={sdk}{sdk_version}] = ",
    "OTHER_CPLUSPLUSFLAGS_{name}_{name}[config={configuration}][arch={architecture}][sdk={sdk}{sdk_version}] = ",
    "FRAMEWORK_SEARCH_PATHS_{name}_{name}[config={configuration}][arch={architecture}][sdk={sdk}{sdk_version}] = ",
    "LIBRARY_SEARCH_PATHS_{name}_{name}[config={configuration}][arch={architecture}][sdk={sdk}{sdk_version}] = ",
    "OTHER_LDFLAGS_{name}_{name}[config={configuration}][arch={architecture}][sdk={sdk}{sdk_version}] = "
]


def expected_files(current_folder, configuration, architecture, sdk_version):
    files = []
    name = _get_filename(configuration, architecture, sdk_version)
    deps = ["hello", "goodbye"]
    files.extend(
        [os.path.join(current_folder, "conan_{dep}_{dep}{name}.xcconfig".format(dep=dep, name=name)) for dep in deps])
    files.append(os.path.join(current_folder, "conandeps.xcconfig"))
    return files


def check_contents(client, deps, configuration, architecture, sdk_version):
    for dep_name in deps:
        dep_xconfig = client.load("conan_{dep}_{dep}.xcconfig".format(dep=dep_name))
        fname = _get_filename(configuration, architecture, sdk_version)
        conf_name = "conan_{}_{}{}.xcconfig".format(dep_name, dep_name, fname)

        assert '#include "{}"'.format(conf_name) in dep_xconfig
        for var in _expected_dep_xconfig:
            line = var.format(name=dep_name)
            assert line in dep_xconfig

        conan_conf = client.load(conf_name)
        for var in _expected_conf_xconfig:
            assert var.format(name=dep_name, configuration=configuration, architecture=architecture,
                              sdk="macosx", sdk_version=sdk_version) in conan_conf


@pytest.mark.skipif(platform.system() != "Darwin", reason="Only for MacOS")
def test_generator_files():
    client = TestClient()
    client.save({"hello.py": GenConanfile().with_settings("os", "arch", "compiler", "build_type")
                                           .with_package_info(cpp_info={"libs": ["hello"],
                                                                        "frameworks": ['framework_hello']})})
    client.run("export hello.py --name=hello --version=0.1")
    client.save({"goodbye.py": GenConanfile().with_settings("os", "arch", "compiler", "build_type")
                                             .with_package_info(cpp_info={"libs": ["goodbye"],
                                                                          "frameworks": ['framework_goodbye']})})
    client.run("export goodbye.py --name=goodbye --version=0.1")
    client.save({"conanfile.txt": "[requires]\nhello/0.1\ngoodbye/0.1\n"}, clean_first=True)

    for build_type in ["Release", "Debug"]:

        client.run("install . -g XcodeDeps -s build_type={} -s arch=x86_64 -s os.sdk_version=12.1 --build missing".format(build_type))

        for config_file in expected_files(client.current_folder, build_type, "x86_64", "12.1"):
            assert os.path.isfile(config_file)

        conandeps = client.load("conandeps.xcconfig")
        assert '#include "conan_hello.xcconfig"' in conandeps
        assert '#include "conan_goodbye.xcconfig"' in conandeps

        conan_config = client.load("conan_config.xcconfig")
        assert '#include "conandeps.xcconfig"' in conan_config

        check_contents(client, ["hello", "goodbye"], build_type, "x86_64", "12.1")


@pytest.mark.skipif(platform.system() != "Darwin", reason="Only for MacOS")
def test_generator_files_with_custom_config():
    client = TestClient()

    client.save({"hello.py": GenConanfile().with_settings("os", "arch", "compiler", "build_type")
                                           .with_package_info(cpp_info={"libs": ["hello"]})})
    client.run("export hello.py --name=hello --version=0.1")

    client.save({"goodbye.py": GenConanfile().with_settings("os", "arch", "compiler", "build_type")
                                             .with_package_info(cpp_info={"libs": ["goodbye"]})})
    client.run("export goodbye.py --name=goodbye --version=0.1")

    conanfile_py = textwrap.dedent("""
        from conan import ConanFile
        from conan.tools.apple import XcodeDeps
        class LibConan(ConanFile):
            settings = "os", "compiler", "build_type", "arch"
            options = {"XcodeConfigName": [None, "ANY"]}
            default_options = {"XcodeConfigName": None}
            requires = "hello/0.1", "goodbye/0.1"

            def generate(self):
                xcode = XcodeDeps(self)
                if self.options.get_safe("XcodeConfigName"):
                    xcode.configuration = str(self.options.get_safe("XcodeConfigName"))
                xcode.generate()
        """)

    client.save({"conanfile.py": conanfile_py})
    custom_config_name = "CustomConfig"

    for use_custom_config in [True, False]:
        for build_type in ["Release", "Debug"]:
            cli_command = "install . -s build_type={} -s arch=x86_64 -s os.sdk_version=12.1  --build missing".format(build_type)
            if use_custom_config:
                cli_command += " -o XcodeConfigName={}".format(custom_config_name)
                configuration_name = custom_config_name
            else:
                configuration_name = build_type

            client.run(cli_command)

            for config_file in expected_files(client.current_folder, configuration_name, "x86_64", "12.1"):
                assert os.path.isfile(config_file)

            conandeps = client.load("conandeps.xcconfig")
            assert '#include "conan_hello.xcconfig"' in conandeps
            assert '#include "conan_goodbye.xcconfig"' in conandeps

            conan_config = client.load("conan_config.xcconfig")
            assert '#include "conandeps.xcconfig"' in conan_config

            check_contents(client, ["hello", "goodbye"],  configuration_name, "x86_64", "12.1",)


@pytest.mark.skipif(platform.system() != "Darwin", reason="Only for MacOS")
def test_xcodedeps_aggregate_components():
    client = TestClient()

    conanfile_py = textwrap.dedent("""
        from conan import ConanFile
        class LibConan(ConanFile):
            settings = "os", "compiler", "build_type", "arch"
            def package_info(self):
                self.cpp_info.includedirs = ["liba_include"]
        """)

    client.save({"conanfile.py": conanfile_py})

    client.run("create . --name=liba --version=1.0")

    r""""
        1   a
       / \ /
      2   3
       \ /
        4   5  6
        |   |  /
         \ / /
           7
    """

    conanfile_py = textwrap.dedent("""
        from conan import ConanFile
        class LibConan(ConanFile):
            settings = "os", "compiler", "build_type", "arch"
            requires = "liba/1.0"
            def package_info(self):
                self.cpp_info.components["libb_comp1"].includedirs = ["libb_comp1"]
                self.cpp_info.components["libb_comp1"].libdirs = ["mylibdir"]
                self.cpp_info.components["libb_comp2"].includedirs = ["libb_comp2"]
                self.cpp_info.components["libb_comp2"].libdirs = ["mylibdir"]
                self.cpp_info.components["libb_comp2"].requires = ["libb_comp1"]
                self.cpp_info.components["libb_comp3"].includedirs = ["libb_comp3"]
                self.cpp_info.components["libb_comp3"].libdirs = ["mylibdir"]
                self.cpp_info.components["libb_comp3"].requires = ["libb_comp1", "liba::liba"]
                self.cpp_info.components["libb_comp4"].includedirs = ["libb_comp4"]
                self.cpp_info.components["libb_comp4"].libdirs = ["mylibdir"]
                self.cpp_info.components["libb_comp4"].requires = ["libb_comp2", "libb_comp3"]
                self.cpp_info.components["libb_comp5"].includedirs = ["libb_comp5"]
                self.cpp_info.components["libb_comp5"].libdirs = ["mylibdir"]
                self.cpp_info.components["libb_comp6"].includedirs = ["libb_comp6"]
                self.cpp_info.components["libb_comp6"].libdirs = ["mylibdir"]
                self.cpp_info.components["libb_comp7"].includedirs = ["libb_comp7"]
                self.cpp_info.components["libb_comp7"].libdirs = ["mylibdir"]
                self.cpp_info.components["libb_comp7"].requires = ["libb_comp4", "libb_comp5", "libb_comp6"]
        """)

    client.save({"conanfile.py": conanfile_py})

    client.run("create . --name=libb --version=1.0")

    client.run("install --requires=libb/1.0 -g XcodeDeps")

    lib_entry = client.load("conan_libb.xcconfig")

    for index in range(1, 8):
        assert f"conan_libb_libb_comp{index}.xcconfig" in lib_entry

    component7_entry = client.load("conan_libb_libb_comp7.xcconfig")
    # External deps are now inlined in the props file, not included in the wrapper
    assert '#include "conan_liba.xcconfig"' not in component7_entry

    arch_setting = client.get_default_host_profile().settings['arch']
    arch = "arm64" if arch_setting == "armv8" else arch_setting

    component7_vars = client.load(f"conan_libb_libb_comp7_release_{arch}.xcconfig")

    # all of the transitive required components and the component itself are added
    for index in range(1, 8):
        assert f"libb_comp{index}" in component7_vars

    assert "mylibdir" in component7_vars

    component4_vars = client.load(f"conan_libb_libb_comp4_release_{arch}.xcconfig")

    # all of the transitive required components and the component itself are added
    for index in range(1, 5):
        assert f"libb_comp{index}" in component4_vars

    for index in range(5, 8):
        assert f"libb_comp{index}" not in component4_vars

    # folders are aggregated
    assert "mylibdir" in component4_vars


@pytest.mark.skipif(platform.system() != "Darwin", reason="Only for MacOS")
def test_xcodedeps_traits():
    client = TestClient()
    conanfile_py = textwrap.dedent("""
        from conan import ConanFile
        class LibConan(ConanFile):
            settings = "os", "compiler", "build_type", "arch"
            {package_info}
            {requirements}
        """)

    package_info = """
    def package_info(self):
        self.cpp_info.components["cmp1"].includedirs = ["cmp1_includedir"]
        self.cpp_info.components["cmp2"].includedirs = ["cmp2_includedir"]

        self.cpp_info.components["cmp1"].libdirs = ["cmp1_libdir"]
        self.cpp_info.components["cmp2"].libdirs = ["cmp2_libdir"]
        self.cpp_info.components["cmp1"].libs = ["cmp1_lib"]
        self.cpp_info.components["cmp2"].libs = ["cmp2_lib"]
        self.cpp_info.components["cmp1"].system_libs = ["cmp1_system_lib"]
        self.cpp_info.components["cmp2"].system_libs = ["cmp2_system_lib"]
        self.cpp_info.components["cmp1"].frameworkdirs = ["cmp1_frameworkdir"]
        self.cpp_info.components["cmp2"].frameworkdirs = ["cmp2_frameworkdir"]
        self.cpp_info.components["cmp1"].frameworks = ["cmp1_framework"]
        self.cpp_info.components["cmp2"].frameworks = ["cmp2_framework"]

        self.cpp_info.components["cmp1"].defines = ["cmp1_define"]
        self.cpp_info.components["cmp2"].defines = ["cmp2_define"]
        self.cpp_info.components["cmp1"].cflags = ["cmp1_cflag"]
        self.cpp_info.components["cmp2"].cflags = ["cmp2_cflag"]
        self.cpp_info.components["cmp1"].cxxflags = ["cmp1_cxxflag"]
        self.cpp_info.components["cmp2"].cxxflags = ["cmp2_cxxflag"]
        self.cpp_info.components["cmp1"].sharedlinkflags = ["cmp1_sharedlinkflag"]
        self.cpp_info.components["cmp2"].sharedlinkflags = ["cmp2_sharedlinkflag"]
        self.cpp_info.components["cmp1"].exelinkflags = ["cmp1_exelinkflag"]
        self.cpp_info.components["cmp2"].exelinkflags = ["cmp2_exelinkflag"]
        """

    client.save({"lib_a.py": conanfile_py.format(requirements="", package_info=package_info)})

    client.run("create lib_a.py --name=lib_a --version=1.0")

    requirements = """
    def requirements(self):
        self.requires("lib_a/1.0", headers=False)
    """

    client.save({"lib_b.py": conanfile_py.format(requirements=requirements, package_info="")},
                clean_first=True)

    client.run("install lib_b.py -g XcodeDeps")

    arch_setting = client.get_default_host_profile().settings['arch']
    arch = "arm64" if arch_setting == "armv8" else arch_setting

    comp1_info = client.load(f"conan_lib_a_cmp1_release_{arch}.xcconfig")
    comp2_info = client.load(f"conan_lib_a_cmp2_release_{arch}.xcconfig")

    assert "cmp1_include" not in comp1_info
    assert "cmp2_include" not in comp2_info

    requirements = """
    def requirements(self):
        self.requires("lib_a/1.0", libs=False)
    """

    client.save({"lib_b.py": conanfile_py.format(requirements=requirements, package_info="")},
                clean_first=True)
    client.run("install lib_b.py -g XcodeDeps")

    comp1_info = client.load(f"conan_lib_a_cmp1_release_{arch}.xcconfig")
    comp2_info = client.load(f"conan_lib_a_cmp2_release_{arch}.xcconfig")

    assert "cmp1_frameworkdir" not in comp1_info
    assert "cmp2_frameworkdir" not in comp2_info

    assert "-lcmp1_lib -lcmp1_system_lib -framework cmp1_framework" not in comp1_info
    assert "-lcmp2_lib -lcmp2_system_lib -framework cmp2_framework" not in comp2_info

    requirements = """
    def requirements(self):
        self.requires("lib_a/1.0", headers=False, libs=False)
    """

    client.save({"lib_b.py": conanfile_py.format(requirements=requirements, package_info="")},
                clean_first=True)
    client.run("install lib_b.py -g XcodeDeps")

    # this changed from non-existing to existing after https://github.com/conan-io/conan/pull/15128
    existing = [f"conan_lib_a_cmp1_release_{arch}.xcconfig", "conan_lib_a_cmp1.xcconfig",
                f"conan_lib_a_cmp2_release_{arch}.xcconfig", "conan_lib_a_cmp2.xcconfig",
                "conan_lib_a.xcconfig"]

    for file in existing:
        assert os.path.exists(os.path.join(client.current_folder, file))

    assert '#include "conan_lib_a.xcconfig"' in client.load("conandeps.xcconfig")

    requirements = """
    def requirements(self):
        self.requires("lib_a/1.0", headers=False, libs=False, run=True)
    """

    client.save({"lib_b.py": conanfile_py.format(requirements=requirements, package_info="")},
                clean_first=True)

    client.run("install lib_b.py -g XcodeDeps")

    comp1_info = client.load(f"conan_lib_a_cmp1_release_{arch}.xcconfig")
    comp2_info = client.load(f"conan_lib_a_cmp2_release_{arch}.xcconfig")

    assert "cmp1_define" not in comp1_info
    assert "cmp2_define" not in comp2_info
    assert "cmp1_cflag" not in comp1_info
    assert "cmp2_cflag" not in comp2_info
    assert "cmp1_cxxflag" not in comp1_info
    assert "cmp2_cxxflag" not in comp2_info
    assert "cmp1_sharedlinkflag" not in comp1_info
    assert "cmp2_sharedlinkflag" not in comp2_info
    assert "cmp1_exelinkflag" not in comp1_info
    assert "cmp2_exelinkflag" not in comp2_info


@pytest.mark.skipif(platform.system() != "Darwin", reason="Only for MacOS")
def test_xcodedeps_frameworkdirs():
    client = TestClient()

    conanfile_py = textwrap.dedent("""
        from conan import ConanFile
        class LibConan(ConanFile):
            name = "lib_a"
            version = "1.0"
            settings = "os", "compiler", "build_type", "arch"
            def package_info(self):
                self.cpp_info.frameworkdirs = ["lib_a_frameworkdir"]
        """)

    client.save({"conanfile.py": conanfile_py})
    client.run("create .")

    arch_setting = client.get_default_host_profile().settings['arch']
    arch = "arm64" if arch_setting == "armv8" else arch_setting

    client.run("install --requires=lib_a/1.0 -g XcodeDeps")

    lib_a_xcconfig = client.load(f"conan_lib_a_lib_a_release_{arch}.xcconfig")

    assert "lib_a_frameworkdir" in lib_a_xcconfig


@pytest.mark.skipif(platform.system() != "Darwin", reason="Only for MacOS")
def test_xcodedeps_cppinfo_requires():

    """
    lib_a: has four components cmp1, cmp2, cmp3, cmp4
    lib_b --> uses libA cmp1 so cpp_info.requires = ["lib_a::cmp1"]
    lib_c --> uses libA cmp2 so cpp_info.requires = ["lib_a::cmp2"]
    consumer --> libB, libC
    """
    client = TestClient()
    lib_a = textwrap.dedent("""
        from conan import ConanFile
        class lib_aConan(ConanFile):
            name = "lib_a"
            version = "1.0"
            settings = "os", "compiler", "build_type", "arch"
            def package_info(self):
                self.cpp_info.components["cmp1"].includedirs = ["include_cmp1"]
                self.cpp_info.components["cmp2"].includedirs = ["include_cmp2"]
                self.cpp_info.components["cmp3"].includedirs = ["include_cmp3"]
                self.cpp_info.components["cmp4"].includedirs = ["include_cmp4"]
        """)

    lib = textwrap.dedent("""
        from conan import ConanFile
        class lib_{name}Conan(ConanFile):
            name = "lib_{name}"
            version = "1.0"
            settings = "os", "compiler", "build_type", "arch"
            def requirements(self):
                self.requires("lib_a/1.0")
            def package_info(self):
                self.cpp_info.requires = {cppinfo_comps}
        """)

    consumer = textwrap.dedent("""
    from conan import ConanFile
    class ConsumerConan(ConanFile):
        name = "consumer"
        version = "1.0"
        settings = "os", "compiler", "build_type", "arch"
        generators = "XcodeDeps"
        def requirements(self):
            self.requires("lib_b/1.0")
            self.requires("lib_c/1.0")
    """)

    client.save({
        'lib_a/conanfile.py': lib_a,
        'lib_b/conanfile.py': lib.format(name="b", cppinfo_comps='["lib_a::cmp1"]'),
        'lib_c/conanfile.py': lib.format(name="c", cppinfo_comps='["lib_a::cmp2"]'),
        'consumer/conanfile.py': consumer,
    })

    client.run("create lib_a")

    client.run("create lib_b")

    client.run("create lib_c")

    client.run("install consumer")

    # External deps are inlined in the props file - verify only the required
    # component's data is included, not other components
    arch_setting = client.get_default_host_profile().settings['arch']
    arch = "arm64" if arch_setting == "armv8" else arch_setting

    lib_b_vars = client.load(os.path.join("consumer", f"conan_lib_b_lib_b_release_{arch}.xcconfig"))
    assert "include_cmp1" in lib_b_vars
    assert "include_cmp2" not in lib_b_vars
    assert "include_cmp3" not in lib_b_vars
    assert "include_cmp4" not in lib_b_vars

    lib_c_vars = client.load(os.path.join("consumer", f"conan_lib_c_lib_c_release_{arch}.xcconfig"))
    assert "include_cmp1" not in lib_c_vars
    assert "include_cmp2" in lib_c_vars
    assert "include_cmp3" not in lib_c_vars
    assert "include_cmp4" not in lib_c_vars


@pytest.mark.skipif(platform.system() != "Darwin", reason="Only for MacOS")
def test_dependency_of_dependency_components():
    # testing: https://github.com/conan-io/conan/pull/11772

    """
    When a dependency of a dependency would have components, only the default
    name conan_dep_dep.xconfig would be included. However, this file was never
    generated, as they are in the form conan_dep_component.xconfig.

    lib_a -> lib_b -> lib_c (with components)
    """
    client = TestClient()
    lib_a = GenConanfile("lib_a", "1.0").with_require("lib_b/1.0").with_settings("os", "arch", "build_type", "compiler")
    lib_b = GenConanfile("lib_b", "1.0").with_require("lib_c/1.0").with_settings("os", "arch", "build_type", "compiler")

    lib_c = textwrap.dedent("""
        from conan import ConanFile
        class lib_aConan(ConanFile):
            name = "lib_c"
            version = "1.0"
            settings = "os", "compiler", "build_type", "arch"
            def package_info(self):
                self.cpp_info.components["cmp1"].includedirs = ["include_cmp1"]
                self.cpp_info.components["cmp2"].includedirs = ["include_cmp2"]
        """)

    client.save({
        'conanfile.py': lib_a,
        'lib_b/conanfile.py': lib_b,
        'lib_c/conanfile.py': lib_c,
    })

    client.run("create lib_c")

    client.run("create lib_b")

    client.run("install . -g XcodeDeps")

    lib_b_xconfig = client.load("conan_lib_b_lib_b.xcconfig")

    # External deps are inlined in the props file, not included in the wrapper
    assert '#include "conan_lib_c_cmp1.xcconfig"' not in lib_b_xconfig
    assert '#include "conan_lib_c_lib_c.xcconfig"' not in lib_b_xconfig

    # Verify lib_c's include dirs are merged into lib_b's props file
    arch_setting = client.get_default_host_profile().settings['arch']
    arch = "arm64" if arch_setting == "armv8" else arch_setting
    lib_b_vars = client.load(f"conan_lib_b_lib_b_release_{arch}.xcconfig")
    assert "include_cmp1" in lib_b_vars
    assert "include_cmp2" in lib_b_vars


def test_skipped_not_included():
    # https://github.com/conan-io/conan/issues/13818
    client = TestClient()
    pkg_info = {"components": {"component": {"defines": ["SOMEDEFINE"]}}}

    client.save({"dep/conanfile.py": GenConanfile().with_package_type("header-library")
                                                   .with_package_info(cpp_info=pkg_info),
                 "pkg/conanfile.py": GenConanfile().with_requirement("dep/0.1")
                                                   .with_package_type("library")
                                                   .with_shared_option(),
                 "consumer/conanfile.py": GenConanfile().with_requires("pkg/0.1")
                                                        .with_settings("os", "build_type", "arch")})
    client.run("create dep --name=dep --version=0.1")
    client.run("create pkg --name=pkg --version=0.1")
    client.run("install consumer -g XcodeDeps -s arch=x86_64 -s build_type=Release")
    assert re.search(r"Skipped binaries\n\s+(.*?)", client.out, re.DOTALL)
    dep_xconfig = client.load("consumer/conan_pkg_pkg.xcconfig")
    assert "conan_dep.xcconfig" not in dep_xconfig


def test_correctly_handle_transitive_components():
    # https://github.com/conan-io/conan/issues/14887
    client = TestClient()
    has_components = textwrap.dedent("""
        from conan import ConanFile
        class PkgWithComponents(ConanFile):
            name = 'has_components'
            version = '1.0'
            settings = 'os', 'compiler', 'arch', 'build_type'
            def package_info(self):
                self.cpp_info.components['first'].libs = ['first']
                self.cpp_info.components['second'].libs = ['donottouch']
                self.cpp_info.components['second'].requires = ['first']
        """)

    uses_components = textwrap.dedent("""
        from conan import ConanFile
        class PkgUsesComponent(ConanFile):
            name = 'uses_components'
            version = '1.0'
            settings = 'os', 'compiler', 'arch', 'build_type'
            def requirements(self):
                self.requires('has_components/1.0')
            def package_info(self):
                self.cpp_info.libs = ['uses_only_first']
                self.cpp_info.requires = ['has_components::first']
        """)

    consumer = textwrap.dedent("""
        [requires]
        uses_components/1.0
        """)

    client.save({"has_components.py": has_components,
                 "uses_components.py": uses_components,
                 "consumer.txt": consumer})
    client.run("create has_components.py")
    client.run("create uses_components.py")
    client.run("install consumer.txt -g XcodeDeps")
    conandeps = client.load("conandeps.xcconfig")
    assert '#include "conan_has_components.xcconfig"' not in conandeps
    assert '#include "conan_uses_components.xcconfig"' in conandeps
    conan_uses_xcconfig = client.load("conan_uses_components_uses_components.xcconfig")
    # External deps are inlined in the props file, not included in the wrapper
    assert '#include "conan_has_components_first.xcconfig"' not in conan_uses_xcconfig
    assert '#include "conan_has_components_second.xcconfig"' not in conan_uses_xcconfig

    # Verify only the 'first' component libs are inlined (not 'second')
    arch_setting = client.get_default_host_profile().settings['arch']
    arch = "arm64" if arch_setting == "armv8" else arch_setting
    uses_vars = client.load(f"conan_uses_components_uses_components_release_{arch}.xcconfig")
    assert "-lfirst" in uses_vars
    assert "-luses_only_first" in uses_vars
    assert "-ldonottouch" not in uses_vars


def test_dont_add_skipped_xcconfigs_when_required_by_components():
    client = TestClient()
    regular_lib = textwrap.dedent("""
        from conan import ConanFile
        class PkgWithComponents(ConanFile):
            name = 'regular_lib'
            version = '1.0'
            settings = 'os', 'compiler', 'arch', 'build_type'
            def requirements(self):
                self.requires('header_skip/1.0')
                self.requires('header_transitive/1.0', transitive_headers=True)
            def package_info(self):
                self.cpp_info.components['component'].requires = ['header_skip::header_skip',
                                                                  'header_transitive::header_transitive']
        """)

    header_transitive = textwrap.dedent("""
        from conan import ConanFile
        class PkgUsesComponent(ConanFile):
            name = 'header_transitive'
            version = '1.0'
            settings = 'os', 'compiler', 'arch', 'build_type'
            package_type = 'header-library'
            def package_info(self):
                self.cpp_info.includedirs = ["include"]
        """)

    header_skip = textwrap.dedent("""
        from conan import ConanFile
        class PkgUsesComponent(ConanFile):
            name = 'header_skip'
            version = '1.0'
            settings = 'os', 'compiler', 'arch', 'build_type'
            package_type = 'header-library'
            def package_info(self):
                self.cpp_info.includedirs = ["include"]
        """)

    client.save({"header_transitive.py": header_transitive,
                 "header_skip.py": header_skip,
                 "regular_lib.py": regular_lib})
    client.run("create header_transitive.py")
    client.run("create header_skip.py")
    client.run("create regular_lib.py")
    client.run("install --requires=regular_lib/1.0 -g XcodeDeps")

    conandeps = client.load("conan_regular_lib_component.xcconfig")
    # External deps are inlined in the props file, not included in the wrapper
    assert '#include "conan_header_skip.xcconfig"' not in conandeps
    assert '#include "conan_header_transitive.xcconfig"' not in conandeps

    # Verify that header_skip xcconfig files are NOT generated (skipped dependency)
    skip_files = [f for f in os.listdir(client.current_folder) if 'header_skip' in f and f.endswith('.xcconfig')]
    assert len(skip_files) == 0, f"Header skip files should not be generated: {skip_files}"

    # Verify that header_transitive xcconfig files ARE generated (transitive dependency)
    transitive_files = [f for f in os.listdir(client.current_folder) if 'header_transitive' in f and f.endswith('.xcconfig')]
    assert len(transitive_files) > 0, f"Header transitive files should be generated: {transitive_files}"


def test_xcodedeps_diamond_with_components():
    """Diamond dependency graph with components:
        consumer -> lib_a -> lib_common (components: core, utils)
        consumer -> lib_b -> lib_common (components: core, utils)
    Verifies deduplication of inlined CppInfo from shared transitive deps.
    """
    client = TestClient()

    lib_common = textwrap.dedent("""
        from conan import ConanFile
        class LibCommon(ConanFile):
            name = "lib_common"
            version = "1.0"
            settings = "os", "compiler", "build_type", "arch"
            def package_info(self):
                self.cpp_info.components["core"].includedirs = ["include_core"]
                self.cpp_info.components["core"].libs = ["common_core"]
                self.cpp_info.components["utils"].includedirs = ["include_utils"]
                self.cpp_info.components["utils"].libs = ["common_utils"]
                self.cpp_info.components["utils"].requires = ["core"]
        """)

    lib_a = textwrap.dedent("""
        from conan import ConanFile
        class LibA(ConanFile):
            name = "lib_a"
            version = "1.0"
            settings = "os", "compiler", "build_type", "arch"
            requires = "lib_common/1.0"
            def package_info(self):
                self.cpp_info.libs = ["lib_a"]
                self.cpp_info.requires = ["lib_common::utils"]
        """)

    lib_b = textwrap.dedent("""
        from conan import ConanFile
        class LibB(ConanFile):
            name = "lib_b"
            version = "1.0"
            settings = "os", "compiler", "build_type", "arch"
            requires = "lib_common/1.0"
            def package_info(self):
                self.cpp_info.libs = ["lib_b"]
                self.cpp_info.requires = ["lib_common::core"]
        """)

    consumer = GenConanfile().with_requires("lib_a/1.0", "lib_b/1.0") \
                             .with_settings("os", "arch", "build_type", "compiler")

    client.save({"lib_common/conanfile.py": lib_common,
                 "lib_a/conanfile.py": lib_a,
                 "lib_b/conanfile.py": lib_b,
                 "conanfile.py": consumer})

    client.run("create lib_common")
    client.run("create lib_a")
    client.run("create lib_b")
    client.run("install . -g XcodeDeps")

    arch_setting = client.get_default_host_profile().settings['arch']
    arch = "arm64" if arch_setting == "armv8" else arch_setting

    # lib_a requires lib_common::utils (which requires core) - both inlined
    lib_a_vars = client.load(f"conan_lib_a_lib_a_release_{arch}.xcconfig")
    assert "-llib_a" in lib_a_vars
    assert "-lcommon_utils" in lib_a_vars
    assert "-lcommon_core" in lib_a_vars
    assert "include_utils" in lib_a_vars
    assert "include_core" in lib_a_vars

    # lib_b requires only lib_common::core - only core inlined, not utils
    lib_b_vars = client.load(f"conan_lib_b_lib_b_release_{arch}.xcconfig")
    assert "-llib_b" in lib_b_vars
    assert "-lcommon_core" in lib_b_vars
    assert "include_core" in lib_b_vars
    assert "-lcommon_utils" not in lib_b_vars
    assert "include_utils" not in lib_b_vars

    # No external #includes in wrappers
    lib_a_wrapper = client.load("conan_lib_a_lib_a.xcconfig")
    assert '#include "conan_lib_common' not in lib_a_wrapper
    lib_b_wrapper = client.load("conan_lib_b_lib_b.xcconfig")
    assert '#include "conan_lib_common' not in lib_b_wrapper


def test_xcodedeps_special_chars_in_names():
    """Packages and components with special characters (-, +, .) in names.
    Verifies normalization works consistently for both lookup and generation.
    """
    client = TestClient()

    base_pkg = textwrap.dedent("""
        from conan import ConanFile
        class BasePkg(ConanFile):
            name = "my-base.lib"
            version = "1.0"
            settings = "os", "compiler", "build_type", "arch"
            def package_info(self):
                self.cpp_info.components["core-impl++"].includedirs = ["include_core"]
                self.cpp_info.components["core-impl++"].libs = ["base_core"]
                self.cpp_info.components["net.utils"].includedirs = ["include_net"]
                self.cpp_info.components["net.utils"].libs = ["base_net"]
                self.cpp_info.components["net.utils"].requires = ["core-impl++"]
        """)

    consumer_pkg = textwrap.dedent("""
        from conan import ConanFile
        class ConsumerPkg(ConanFile):
            name = "app-client"
            version = "1.0"
            settings = "os", "compiler", "build_type", "arch"
            requires = "my-base.lib/1.0"
            def package_info(self):
                self.cpp_info.libs = ["app_client"]
                self.cpp_info.requires = ["my-base.lib::net.utils"]
        """)

    consumer = GenConanfile().with_requires("app-client/1.0") \
                             .with_settings("os", "arch", "build_type", "compiler")

    client.save({"base/conanfile.py": base_pkg,
                 "consumer_pkg/conanfile.py": consumer_pkg,
                 "conanfile.py": consumer})

    client.run("create base")
    client.run("create consumer_pkg")
    client.run("install . -g XcodeDeps")

    arch_setting = client.get_default_host_profile().settings['arch']
    arch = "arm64" if arch_setting == "armv8" else arch_setting

    # Verify the normalized files exist and contain the right data
    app_vars = client.load(f"conan_app_client_app_client_release_{arch}.xcconfig")
    assert "-lapp_client" in app_vars
    assert "-lbase_net" in app_vars
    assert "-lbase_core" in app_vars
    assert "include_net" in app_vars
    assert "include_core" in app_vars

    # No external includes in wrapper
    app_wrapper = client.load("conan_app_client_app_client.xcconfig")
    assert '#include "conan_my_base_lib' not in app_wrapper


def test_xcodedeps_mixed_components_no_components_chain():
    """Chain mixing packages with and without components:
        consumer -> pkg_with_comps (components: a, b) -> pkg_no_comps -> pkg_leaf (components: x, y)
    Verifies resolution works across mixed package types at different depths.
    """
    client = TestClient()

    pkg_leaf = textwrap.dedent("""
        from conan import ConanFile
        class PkgLeaf(ConanFile):
            name = "pkg_leaf"
            version = "1.0"
            settings = "os", "compiler", "build_type", "arch"
            def package_info(self):
                self.cpp_info.components["x"].libs = ["leaf_x"]
                self.cpp_info.components["x"].includedirs = ["include_x"]
                self.cpp_info.components["y"].libs = ["leaf_y"]
                self.cpp_info.components["y"].includedirs = ["include_y"]
        """)

    pkg_no_comps = textwrap.dedent("""
        from conan import ConanFile
        class PkgNoComps(ConanFile):
            name = "pkg_no_comps"
            version = "1.0"
            settings = "os", "compiler", "build_type", "arch"
            requires = "pkg_leaf/1.0"
            def package_info(self):
                self.cpp_info.libs = ["no_comps"]
                self.cpp_info.requires = ["pkg_leaf::x"]
        """)

    pkg_with_comps = textwrap.dedent("""
        from conan import ConanFile
        class PkgWithComps(ConanFile):
            name = "pkg_with_comps"
            version = "1.0"
            settings = "os", "compiler", "build_type", "arch"
            requires = "pkg_no_comps/1.0"
            def package_info(self):
                self.cpp_info.components["a"].libs = ["comp_a"]
                self.cpp_info.components["a"].requires = ["pkg_no_comps::pkg_no_comps"]
                self.cpp_info.components["b"].libs = ["comp_b"]
        """)

    consumer = GenConanfile().with_requires("pkg_with_comps/1.0") \
                             .with_settings("os", "arch", "build_type", "compiler")

    client.save({"pkg_leaf/conanfile.py": pkg_leaf,
                 "pkg_no_comps/conanfile.py": pkg_no_comps,
                 "pkg_with_comps/conanfile.py": pkg_with_comps,
                 "conanfile.py": consumer})

    client.run("create pkg_leaf")
    client.run("create pkg_no_comps")
    client.run("create pkg_with_comps")
    client.run("install . -g XcodeDeps")

    arch_setting = client.get_default_host_profile().settings['arch']
    arch = "arm64" if arch_setting == "armv8" else arch_setting

    # Component "a" requires pkg_no_comps which requires pkg_leaf::x
    # All three levels should be inlined
    comp_a_vars = client.load(f"conan_pkg_with_comps_a_release_{arch}.xcconfig")
    assert "-lcomp_a" in comp_a_vars
    assert "-lno_comps" in comp_a_vars
    assert "-lleaf_x" in comp_a_vars
    assert "-lleaf_y" not in comp_a_vars

    # Component "b" has no external deps
    comp_b_vars = client.load(f"conan_pkg_with_comps_b_release_{arch}.xcconfig")
    assert "-lcomp_b" in comp_b_vars
    assert "-lno_comps" not in comp_b_vars
    assert "-lleaf_x" not in comp_b_vars

    # No external includes in wrappers
    comp_a_wrapper = client.load("conan_pkg_with_comps_a.xcconfig")
    assert '#include "conan_pkg_no_comps' not in comp_a_wrapper
    assert '#include "conan_pkg_leaf' not in comp_a_wrapper


def test_xcodedeps_include_depth_is_constant():
    """Verify the include chain depth is constant (max 3: umbrella -> wrapper -> props)
    regardless of the number of transitive dependencies.
    """
    client = TestClient()

    # Create a chain: dep_0 -> dep_1 -> dep_2 -> dep_3
    for i in range(4):
        req = f'requires = "dep_{i-1}/1.0"' if i > 0 else ""
        dep_req = f'self.cpp_info.requires = ["dep_{i-1}::dep_{i-1}"]' if i > 0 else ""
        conanfile = textwrap.dedent(f"""
            from conan import ConanFile
            class Dep{i}(ConanFile):
                name = "dep_{i}"
                version = "1.0"
                settings = "os", "compiler", "build_type", "arch"
                {req}
                def package_info(self):
                    self.cpp_info.libs = ["dep_{i}"]
                    {dep_req}
            """)
        client.save({f"dep_{i}/conanfile.py": conanfile})
        client.run(f"create dep_{i}")

    consumer = GenConanfile().with_requires("dep_3/1.0") \
                             .with_settings("os", "arch", "build_type", "compiler")
    client.save({"conanfile.py": consumer})
    client.run("install . -g XcodeDeps")

    # Verify wrapper has exactly 1 include (its own props file) and no external includes
    dep3_wrapper = client.load("conan_dep_3_dep_3.xcconfig")
    includes = [line.strip() for line in dep3_wrapper.splitlines() if line.strip().startswith('#include')]
    assert len(includes) == 1, f"Wrapper should have exactly 1 #include (props), got: {includes}"
    assert "dep_3_dep_3_release_" in includes[0]

    # Umbrella includes only its own component wrapper
    dep3_umbrella = client.load("conan_dep_3.xcconfig")
    umbrella_includes = [l.strip() for l in dep3_umbrella.splitlines() if l.strip().startswith('#include')]
    assert len(umbrella_includes) == 1
    assert "conan_dep_3_dep_3.xcconfig" in umbrella_includes[0]

    arch_setting = client.get_default_host_profile().settings['arch']
    arch = "arm64" if arch_setting == "armv8" else arch_setting

    # Verify all transitive libs are inlined in the props file
    dep3_vars = client.load(f"conan_dep_3_dep_3_release_{arch}.xcconfig")
    for i in range(4):
        assert f"-ldep_{i}" in dep3_vars, f"dep_{i} lib should be inlined in dep_3 props"
