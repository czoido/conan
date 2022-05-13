import os
import platform
import textwrap

import pytest

from conans.test.assets.genconanfile import GenConanfile
from conans.test.utils.tools import TestClient


@pytest.mark.skipif(platform.system() != "Darwin", reason="Only for MacOS")
@pytest.mark.tool_cmake
@pytest.mark.tool_xcodebuild
@pytest.mark.tool_xcodegen
def test_xcodedeps_build_configurations():
    client = TestClient(path_with_spaces=False)

    client.run("new hello/0.1 -m=cmake_lib")
    client.run("export .")

    client.run("new bye/0.1 -m=cmake_lib")
    client.run("export .")

    main = textwrap.dedent("""
        #include <iostream>
        #include "hello.h"
        #include "bye.h"
        int main(int argc, char *argv[]) {
            hello();
            bye();
            #ifndef DEBUG
            std::cout << "App Release!" << std::endl;
            #else
            std::cout << "App Debug!" << std::endl;
            #endif
        }
        """)

    xcode_project = textwrap.dedent("""
        name: app
        targets:
          app:
            type: tool
            platform: macOS
            sources:
              - main.cpp
            configFiles:
              Debug: conan_config.xcconfig
              Release: conan_config.xcconfig
        """)

    client.save({
        "conanfile.txt": "[requires]\nhello/0.1\nbye/0.1\n",
        "main.cpp": main,
        "project.yml": xcode_project,
    }, clean_first=True)

    for config in ["Release", "Debug"]:
        client.run("install . -s build_type={} -s arch=x86_64 --build=missing -g XcodeDeps".format(config))

    client.run_command("xcodegen generate")

    for config in ["Release", "Debug"]:
        client.run_command("xcodebuild -project app.xcodeproj -xcconfig conandeps.xcconfig "
                           "-configuration {} -arch x86_64".format(config))
        client.run_command("./build/{}/app".format(config))
        assert "App {}!".format(config) in client.out
        assert "hello/0.1: Hello World {}!".format(config).format(config) in client.out


@pytest.mark.skipif(platform.system() != "Darwin", reason="Only for MacOS")
@pytest.mark.tool_cmake
@pytest.mark.tool_xcodebuild
def test_frameworks():
    client = TestClient(path_with_spaces=False)

    client.save({"hello.py": GenConanfile().with_settings("os", "arch", "compiler", "build_type")
                                           .with_package_info(cpp_info={"frameworks":
                                                                        ['CoreFoundation']},
                                                              env_info={})})
    client.run("export hello.py hello/0.1@")

    main = textwrap.dedent("""
        #include <CoreFoundation/CoreFoundation.h>
        int main(int argc, char *argv[]) {
            CFShow(CFSTR("Hello!"));
        }
        """)

    project_name = "app"
    client.save({"conanfile.txt": "[requires]\nhello/0.1\n"}, clean_first=True)
    create_xcode_project(client, project_name, main)

    client.run("install . -s build_type=Release -s arch=x86_64 --build=missing -g XcodeDeps")

    client.run_command("xcodebuild -project {}.xcodeproj -xcconfig conandeps.xcconfig "
                       "-configuration Release -arch x86_64".format(project_name))
    client.run_command("./build/Release/{}".format(project_name))
    assert "Hello!" in client.out


@pytest.mark.skipif(platform.system() != "Darwin", reason="Only for MacOS")
@pytest.mark.tool_xcodebuild
def test_xcodedeps_dashes_names_and_arch():
    # https://github.com/conan-io/conan/issues/9949
    client = TestClient(path_with_spaces=False)
    client.save({"conanfile.py": GenConanfile().with_name("hello-dashes").with_version("0.1")})
    client.run("export .")
    client.save({"conanfile.txt": "[requires]\nhello-dashes/0.1\n"}, clean_first=True)
    main = "int main(int argc, char *argv[]) { return 0; }"
    create_xcode_project(client, "app", main)
    client.run("install . -s arch=armv8 --build=missing -g XcodeDeps")
    assert os.path.exists(os.path.join(client.current_folder,
                                       "conan_hello_dashes_hello_dashes_vars_release_arm64.xcconfig"))
    client.run_command("xcodebuild -project app.xcodeproj -xcconfig conandeps.xcconfig -arch arm64")


@pytest.mark.skipif(platform.system() != "Darwin", reason="Only for MacOS")
@pytest.mark.tool_xcodebuild
def test_xcodedeps_definitions_escape():
    client = TestClient(path_with_spaces=False)
    conanfile = textwrap.dedent('''
        from conans import ConanFile

        class HelloLib(ConanFile):
            def package_info(self):
                self.cpp_info.defines.append("USER_CONFIG=\\"user_config.h\\"")
                self.cpp_info.defines.append('OTHER="other.h"')
        ''')
    client.save({"conanfile.py": conanfile})
    client.run("export . hello/1.0@")
    client.save({"conanfile.txt": "[requires]\nhello/1.0\n"}, clean_first=True)
    main = textwrap.dedent("""
                                #include <stdio.h>
                                #define STR(x)   #x
                                #define SHOW_DEFINE(x) printf("%s=%s", #x, STR(x))
                                int main(int argc, char *argv[]) {
                                    SHOW_DEFINE(USER_CONFIG);
                                    SHOW_DEFINE(OTHER);
                                    return 0;
                                }
                                """)
    create_xcode_project(client, "app", main)
    client.run("install . --build=missing -g XcodeDeps")
    client.run_command("xcodebuild -project app.xcodeproj -xcconfig conandeps.xcconfig")
    client.run_command("build/Release/app")
    assert 'USER_CONFIG="user_config.h"' in client.out
    assert 'OTHER="other.h"' in client.out
