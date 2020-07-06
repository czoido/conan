import os
import unittest
from textwrap import dedent

from nose.plugins.attrib import attr

from conans.test.utils.multi_config import multi_config_files
from conans.test.utils.tools import TestClient


@attr("slow")
class CMakeConfigsTest(unittest.TestCase):

    def test_package_configs_test(self):
        client = TestClient()
        name = "Hello0"
        files = multi_config_files(name, test=True)
        client.save(files, clean_first=True)

        client.run("create . user/testing")
        self.assertIn("Hello Release Hello0", client.out)
        self.assertIn("Hello Debug Hello0", client.out)

    def test_package_configs_del_compiler(self):
        client = TestClient()

        hello_cpp = dedent("""
            #include <iostream>
    
            void main(){
                #ifndef _DEBUG
                std::cout << "Hello World Release!" <<std::endl;
                #else
                std::cout << "Hello World Debug!" <<std::endl;
                #endif
            }
            """)

        conanfile = dedent("""
            from conans import ConanFile, CMake
            import os  
        
            class Pkg(ConanFile):
                exports = '*'
                generators = "cmake"
                settings = "os", "compiler", "build_type", "arch"
                
                def configure(self):
                    del self.settings.compiler
    
                def build(self):
                    cmake = CMake(self)
                    cmake.configure()
                    cmake.build()
                    os.chdir("bin")
                    self.run(".%shello" % os.sep)
            """)

        cmakelists_txt = dedent("""
            cmake_minimum_required(VERSION 2.8)
            project(myhello CXX)
            
            include(${CMAKE_BINARY_DIR}/conanbuildinfo.cmake)
            conan_basic_setup()
            
            add_executable(hello hello.cpp)        
        """)

        client.save({"conanfile.py": conanfile,
                     "hello.cpp": hello_cpp,
                     "CMakeLists.txt": cmakelists_txt})

        client.run("create . hello/1.0@ --settings build_type=Release")
        self.assertNotIn("Hello World Debug!", client.out)
        self.assertIn("Hello World Release!", client.out)

    def cmake_multi_test(self):
        client = TestClient()

        deps = None
        for name in ["Hello0", "Hello1", "Hello2"]:
            files = multi_config_files(name, test=False, deps=deps)
            client.save(files, clean_first=True)
            deps = [name]
            if name != "Hello2":
                client.run("export . lasote/stable")

        client.run('install . --build missing')
        client.run("build .")
        cmd = os.sep.join([".", "bin", "say_hello"])
        client.run_command(cmd)
        self.assertIn("Hello Release Hello2 Hello Release Hello1 Hello Release Hello0",
                      " ".join(str(client.out).splitlines()))
        client.run_command(cmd + "_d")
        self.assertIn("Hello Debug Hello2 Hello Debug Hello1 Hello Debug Hello0",
                      " ".join(str(client.out).splitlines()))
