import os
import platform
import shutil
import textwrap
import unittest

import pytest
from parameterized import parameterized


from conans.client.tools import chdir
from conans.util.files import mkdir
from conan.tools.microsoft.visual import vcvars_command
from conans.client.tools import vs_installation_path
from conans.test.assets.sources import gen_function_cpp
from conans.test.functional.utils import check_vs_runtime, check_exe_run
from conans.test.utils.tools import TestClient


sln_file = r"""
Microsoft Visual Studio Solution File, Format Version 12.00
# Visual Studio 15
VisualStudioVersion = 15.0.28307.757
MinimumVisualStudioVersion = 10.0.40219.1
Project("{8BC9CEB8-8B4A-11D0-8D11-00A0C91BC942}") = "MyApp", "MyApp\MyApp.vcxproj", "{B58316C0-C78A-4E9B-AE8F-5D6368CE3840}"
EndProject
Global
    GlobalSection(SolutionConfigurationPlatforms) = preSolution
        Debug|x64 = Debug|x64
        Debug|x86 = Debug|x86
        Release|x64 = Release|x64
        Release|x86 = Release|x86
        ReleaseShared|x64 = ReleaseShared|x64
        ReleaseShared|x86 = ReleaseShared|x86
    EndGlobalSection
    GlobalSection(ProjectConfigurationPlatforms) = postSolution
        {B58316C0-C78A-4E9B-AE8F-5D6368CE3840}.Debug|x64.ActiveCfg = Debug|x64
        {B58316C0-C78A-4E9B-AE8F-5D6368CE3840}.Debug|x64.Build.0 = Debug|x64
        {B58316C0-C78A-4E9B-AE8F-5D6368CE3840}.Debug|x86.ActiveCfg = Debug|Win32
        {B58316C0-C78A-4E9B-AE8F-5D6368CE3840}.Debug|x86.Build.0 = Debug|Win32
        {B58316C0-C78A-4E9B-AE8F-5D6368CE3840}.Release|x64.ActiveCfg = Release|x64
        {B58316C0-C78A-4E9B-AE8F-5D6368CE3840}.Release|x64.Build.0 = Release|x64
        {B58316C0-C78A-4E9B-AE8F-5D6368CE3840}.Release|x86.ActiveCfg = Release|Win32
        {B58316C0-C78A-4E9B-AE8F-5D6368CE3840}.Release|x86.Build.0 = Release|Win32
        {B58316C0-C78A-4E9B-AE8F-5D6368CE3840}.ReleaseShared|x64.ActiveCfg = ReleaseShared|x64
        {B58316C0-C78A-4E9B-AE8F-5D6368CE3840}.ReleaseShared|x64.Build.0 = ReleaseShared|x64
        {B58316C0-C78A-4E9B-AE8F-5D6368CE3840}.ReleaseShared|x86.ActiveCfg = ReleaseShared|Win32
        {B58316C0-C78A-4E9B-AE8F-5D6368CE3840}.ReleaseShared|x86.Build.0 = ReleaseShared|Win32
    EndGlobalSection
    GlobalSection(SolutionProperties) = preSolution
        HideSolutionNode = FALSE
    EndGlobalSection
    GlobalSection(ExtensibilityGlobals) = postSolution
        SolutionGuid = {DE6E462F-E299-4F9C-951A-F9404EB51521}
    EndGlobalSection
EndGlobal
"""


myapp_vcxproj = r"""<?xml version="1.0" encoding="utf-8"?>
<Project DefaultTargets="Build" ToolsVersion="15.0"
          xmlns="http://schemas.microsoft.com/developer/msbuild/2003">
  <ItemGroup Label="ProjectConfigurations">
    <ProjectConfiguration Include="Debug|Win32">
      <Configuration>Debug</Configuration>
      <Platform>Win32</Platform>
    </ProjectConfiguration>
    <ProjectConfiguration Include="ReleaseShared|Win32">
      <Configuration>ReleaseShared</Configuration>
      <Platform>Win32</Platform>
    </ProjectConfiguration>
    <ProjectConfiguration Include="ReleaseShared|x64">
      <Configuration>ReleaseShared</Configuration>
      <Platform>x64</Platform>
    </ProjectConfiguration>
    <ProjectConfiguration Include="Release|Win32">
      <Configuration>Release</Configuration>
      <Platform>Win32</Platform>
    </ProjectConfiguration>
    <ProjectConfiguration Include="Debug|x64">
      <Configuration>Debug</Configuration>
      <Platform>x64</Platform>
    </ProjectConfiguration>
    <ProjectConfiguration Include="Release|x64">
      <Configuration>Release</Configuration>
      <Platform>x64</Platform>
    </ProjectConfiguration>
  </ItemGroup>
  <PropertyGroup Label="Globals">
    <VCProjectVersion>15.0</VCProjectVersion>
    <ProjectGuid>{B58316C0-C78A-4E9B-AE8F-5D6368CE3840}</ProjectGuid>
    <Keyword>Win32Proj</Keyword>
    <RootNamespace>MyApp</RootNamespace>
  </PropertyGroup>
  <Import Project="$(VCTargetsPath)\Microsoft.Cpp.Default.props" />
  <PropertyGroup Condition="'$(Configuration)|$(Platform)'=='ReleaseShared|Win32'" Label="Configuration">
    <ConfigurationType>Application</ConfigurationType>
    <UseDebugLibraries>false</UseDebugLibraries>
    <PlatformToolset>v141</PlatformToolset>
    <WholeProgramOptimization>true</WholeProgramOptimization>
    <CharacterSet>Unicode</CharacterSet>
  </PropertyGroup>
  <PropertyGroup Condition="'$(Configuration)|$(Platform)'=='ReleaseShared|x64'" Label="Configuration">
    <ConfigurationType>Application</ConfigurationType>
    <UseDebugLibraries>false</UseDebugLibraries>
    <PlatformToolset>v141</PlatformToolset>
    <WholeProgramOptimization>true</WholeProgramOptimization>
    <CharacterSet>Unicode</CharacterSet>
  </PropertyGroup>
  <PropertyGroup Condition="'$(Configuration)|$(Platform)'=='Debug|Win32'" Label="Configuration">
    <ConfigurationType>Application</ConfigurationType>
    <UseDebugLibraries>true</UseDebugLibraries>
    <PlatformToolset>v141</PlatformToolset>
    <CharacterSet>Unicode</CharacterSet>
  </PropertyGroup>
  <PropertyGroup Condition="'$(Configuration)|$(Platform)'=='Release|Win32'" Label="Configuration">
    <ConfigurationType>Application</ConfigurationType>
    <UseDebugLibraries>false</UseDebugLibraries>
    <PlatformToolset>v141</PlatformToolset>
    <WholeProgramOptimization>true</WholeProgramOptimization>
    <CharacterSet>Unicode</CharacterSet>
  </PropertyGroup>
  <PropertyGroup Condition="'$(Configuration)|$(Platform)'=='Debug|x64'" Label="Configuration">
    <ConfigurationType>Application</ConfigurationType>
    <UseDebugLibraries>true</UseDebugLibraries>
    <PlatformToolset>v141</PlatformToolset>
    <CharacterSet>Unicode</CharacterSet>
  </PropertyGroup>
  <PropertyGroup Condition="'$(Configuration)|$(Platform)'=='Release|x64'" Label="Configuration">
    <ConfigurationType>Application</ConfigurationType>
    <UseDebugLibraries>false</UseDebugLibraries>
    <PlatformToolset>v141</PlatformToolset>
    <WholeProgramOptimization>true</WholeProgramOptimization>
    <CharacterSet>Unicode</CharacterSet>
  </PropertyGroup>
  <!-- Very IMPORTANT this should go BEFORE the Microsoft.Cpp.props.
  If it goes after, the Toolset definition is ignored -->
  <ImportGroup Label="PropertySheets">
    <Import Project="..\conan\conan_hello.props" />
    <Import Project="..\conan\conantoolchain.props" />
  </ImportGroup>
  <Import Project="$(VCTargetsPath)\Microsoft.Cpp.props" />
  <ImportGroup Label="ExtensionSettings">
  </ImportGroup>
  <ImportGroup Label="Shared">
  </ImportGroup>
  <ImportGroup Label="PropertySheets" Condition="'$(Configuration)|$(Platform)'=='Debug|Win32'">
    <Import Project="$(UserRootDir)\Microsoft.Cpp.$(Platform).user.props"
    Condition="exists('$(UserRootDir)\Microsoft.Cpp.$(Platform).user.props')"
    Label="LocalAppDataPlatform" />
  </ImportGroup>
  <ImportGroup Label="PropertySheets" Condition="'$(Configuration)|$(Platform)'=='Release|Win32'">
    <Import Project="$(UserRootDir)\Microsoft.Cpp.$(Platform).user.props"
    Condition="exists('$(UserRootDir)\Microsoft.Cpp.$(Platform).user.props')"
    Label="LocalAppDataPlatform" />
  </ImportGroup>
   <ImportGroup Label="PropertySheets" Condition="'$(Configuration)|$(Platform)'=='ReleaseShared|Win32'">
    <Import Project="$(UserRootDir)\Microsoft.Cpp.$(Platform).user.props"
    Condition="exists('$(UserRootDir)\Microsoft.Cpp.$(Platform).user.props')"
    Label="LocalAppDataPlatform" />
  </ImportGroup>
   <ImportGroup Label="PropertySheets" Condition="'$(Configuration)|$(Platform)'=='ReleaseShared|Win32'">
    <Import Project="$(UserRootDir)\Microsoft.Cpp.$(Platform).user.props"
    Condition="exists('$(UserRootDir)\Microsoft.Cpp.$(Platform).user.props')"
    Label="LocalAppDataPlatform" />
  </ImportGroup>
  <ImportGroup Label="PropertySheets" Condition="'$(Configuration)|$(Platform)'=='Debug|x64'">
    <Import Project="$(UserRootDir)\Microsoft.Cpp.$(Platform).user.props"
    Condition="exists('$(UserRootDir)\Microsoft.Cpp.$(Platform).user.props')"
    Label="LocalAppDataPlatform" />
  </ImportGroup>
  <ImportGroup Label="PropertySheets" Condition="'$(Configuration)|$(Platform)'=='Release|x64'">
    <Import Project="$(UserRootDir)\Microsoft.Cpp.$(Platform).user.props"
    Condition="exists('$(UserRootDir)\Microsoft.Cpp.$(Platform).user.props')"
    Label="LocalAppDataPlatform" />
  </ImportGroup>
  <PropertyGroup Label="UserMacros" />
  <PropertyGroup Condition="'$(Configuration)|$(Platform)'=='Debug|Win32'">
    <LinkIncremental>true</LinkIncremental>
  </PropertyGroup>
  <PropertyGroup Condition="'$(Configuration)|$(Platform)'=='Debug|x64'">
    <LinkIncremental>true</LinkIncremental>
  </PropertyGroup>
  <PropertyGroup Condition="'$(Configuration)|$(Platform)'=='Release|Win32'">
    <LinkIncremental>false</LinkIncremental>
  </PropertyGroup>
  <PropertyGroup Condition="'$(Configuration)|$(Platform)'=='Release|x64'">
    <LinkIncremental>false</LinkIncremental>
  </PropertyGroup>
  <PropertyGroup Condition="'$(Configuration)|$(Platform)'=='ReleaseShared|Win32'">
    <LinkIncremental>false</LinkIncremental>
  </PropertyGroup>
  <PropertyGroup Condition="'$(Configuration)|$(Platform)'=='ReleaseShared|x64'">
    <LinkIncremental>false</LinkIncremental>
  </PropertyGroup>
  <ItemDefinitionGroup Condition="'$(Configuration)|$(Platform)'=='Debug|Win32'">
    <ClCompile>
      <PrecompiledHeader>NotUsing</PrecompiledHeader>
      <WarningLevel>Level3</WarningLevel>
      <Optimization>Disabled</Optimization>
      <SDLCheck>true</SDLCheck>
      <PreprocessorDefinitions>WIN32;_DEBUG;_CONSOLE;%(PreprocessorDefinitions)
      </PreprocessorDefinitions>
      <ConformanceMode>true</ConformanceMode>
    </ClCompile>
    <Link>
      <SubSystem>Console</SubSystem>
      <GenerateDebugInformation>true</GenerateDebugInformation>
    </Link>
  </ItemDefinitionGroup>
  <ItemDefinitionGroup Condition="'$(Configuration)|$(Platform)'=='ReleaseShared|Win32'">
    <ClCompile>
      <PrecompiledHeader>NotUsing</PrecompiledHeader>
      <WarningLevel>Level3</WarningLevel>
      <Optimization>MaxSpeed</Optimization>
      <FunctionLevelLinking>true</FunctionLevelLinking>
      <IntrinsicFunctions>true</IntrinsicFunctions>
      <SDLCheck>true</SDLCheck>
      <PreprocessorDefinitions>WIN32;NDEBUG;_CONSOLE;%(PreprocessorDefinitions)
      </PreprocessorDefinitions>
      <ConformanceMode>true</ConformanceMode>
    </ClCompile>
    <Link>
      <SubSystem>Console</SubSystem>
      <EnableCOMDATFolding>true</EnableCOMDATFolding>
      <OptimizeReferences>true</OptimizeReferences>
      <GenerateDebugInformation>true</GenerateDebugInformation>
    </Link>
  </ItemDefinitionGroup>
  <ItemDefinitionGroup Condition="'$(Configuration)|$(Platform)'=='ReleaseShared|x64'">
    <ClCompile>
      <PrecompiledHeader>NotUsing</PrecompiledHeader>
      <WarningLevel>Level3</WarningLevel>
      <Optimization>MaxSpeed</Optimization>
      <FunctionLevelLinking>true</FunctionLevelLinking>
      <IntrinsicFunctions>true</IntrinsicFunctions>
      <SDLCheck>true</SDLCheck>
      <PreprocessorDefinitions>NDEBUG;_CONSOLE;%(PreprocessorDefinitions)</PreprocessorDefinitions>
      <ConformanceMode>true</ConformanceMode>
    </ClCompile>
    <Link>
      <SubSystem>Console</SubSystem>
      <EnableCOMDATFolding>true</EnableCOMDATFolding>
      <OptimizeReferences>true</OptimizeReferences>
      <GenerateDebugInformation>true</GenerateDebugInformation>
    </Link>
  </ItemDefinitionGroup>
  <ItemDefinitionGroup Condition="'$(Configuration)|$(Platform)'=='Debug|x64'">
    <ClCompile>
      <PrecompiledHeader>NotUsing</PrecompiledHeader>
      <WarningLevel>Level3</WarningLevel>
      <Optimization>Disabled</Optimization>
      <SDLCheck>true</SDLCheck>
      <PreprocessorDefinitions>_DEBUG;_CONSOLE;%(PreprocessorDefinitions)</PreprocessorDefinitions>
      <ConformanceMode>true</ConformanceMode>
    </ClCompile>
    <Link>
      <SubSystem>Console</SubSystem>
      <GenerateDebugInformation>true</GenerateDebugInformation>
    </Link>
  </ItemDefinitionGroup>
  <ItemDefinitionGroup Condition="'$(Configuration)|$(Platform)'=='Release|Win32'">
    <ClCompile>
      <PrecompiledHeader>NotUsing</PrecompiledHeader>
      <WarningLevel>Level3</WarningLevel>
      <Optimization>MaxSpeed</Optimization>
      <FunctionLevelLinking>true</FunctionLevelLinking>
      <IntrinsicFunctions>true</IntrinsicFunctions>
      <SDLCheck>true</SDLCheck>
      <PreprocessorDefinitions>WIN32;NDEBUG;_CONSOLE;%(PreprocessorDefinitions)
      </PreprocessorDefinitions>
      <ConformanceMode>true</ConformanceMode>
    </ClCompile>
    <Link>
      <SubSystem>Console</SubSystem>
      <EnableCOMDATFolding>true</EnableCOMDATFolding>
      <OptimizeReferences>true</OptimizeReferences>
      <GenerateDebugInformation>true</GenerateDebugInformation>
    </Link>
  </ItemDefinitionGroup>
  <ItemDefinitionGroup Condition="'$(Configuration)|$(Platform)'=='Release|x64'">
    <ClCompile>
      <PrecompiledHeader>NotUsing</PrecompiledHeader>
      <WarningLevel>Level3</WarningLevel>
      <Optimization>MaxSpeed</Optimization>
      <FunctionLevelLinking>true</FunctionLevelLinking>
      <IntrinsicFunctions>true</IntrinsicFunctions>
      <SDLCheck>true</SDLCheck>
      <PreprocessorDefinitions>NDEBUG;_CONSOLE;%(PreprocessorDefinitions)</PreprocessorDefinitions>
      <ConformanceMode>true</ConformanceMode>
    </ClCompile>
    <Link>
      <SubSystem>Console</SubSystem>
      <EnableCOMDATFolding>true</EnableCOMDATFolding>
      <OptimizeReferences>true</OptimizeReferences>
      <GenerateDebugInformation>true</GenerateDebugInformation>
    </Link>
  </ItemDefinitionGroup>
  <ItemGroup>
    <ClCompile Include="MyApp.cpp" />
  </ItemGroup>
  <Import Project="$(VCTargetsPath)\Microsoft.Cpp.targets" />
  <ImportGroup Label="ExtensionTargets">
  </ImportGroup>
</Project>
"""


@pytest.mark.tool_visual_studio
@pytest.mark.skipif(platform.system() != "Windows", reason="Only for windows")
def test_msvc_runtime_flag():
    client = TestClient()
    conanfile = textwrap.dedent("""
       from conans import ConanFile
       from conan.tools.microsoft import msvc_runtime_flag
       class App(ConanFile):
           settings = "os", "arch", "compiler", "build_type"

           def generate(self):
               self.output.info("MSVC FLAG={}!!".format(msvc_runtime_flag(self)))
        """)
    client.save({"conanfile.py": conanfile})
    client.run('install . -s compiler="Visual Studio" -s compiler.version=15 -s compiler.runtime=MD')
    assert "MSVC FLAG=MD!!" in client.out
    client.run('install . -s compiler=msvc -s compiler.version=19.1 -s compiler.runtime=static '
               '-s compiler.runtime_type=Debug -s compiler.cppstd=14')
    assert "MSVC FLAG=MTd!!" in client.out
    client.run('install . -s compiler=msvc -s compiler.version=19.1 -s compiler.runtime=dynamic '
               '-s compiler.cppstd=14')
    assert "MSVC FLAG=MD!!" in client.out


@pytest.mark.skipif(platform.system() != "Windows", reason="Only for windows")
@pytest.mark.tool_visual_studio
class WinTest(unittest.TestCase):

    conanfile = textwrap.dedent("""
        from conans import ConanFile
        from conan.tools.microsoft import MSBuildToolchain, MSBuild, MSBuildDeps
        class App(ConanFile):
            settings = "os", "arch", "compiler", "build_type"
            requires = "hello/0.1"
            options = {"shared": [True, False]}
            default_options = {"shared": False}

            def generate(self):
                tc = MSBuildToolchain(self)
                gen = MSBuildDeps(self)
                if self.options["hello"].shared and self.settings.build_type == "Release":
                    tc.configuration = "ReleaseShared"
                    gen.configuration = "ReleaseShared"

                tc.preprocessor_definitions["DEFINITIONS_BOTH"] = "True"
                if self.settings.build_type == "Debug":
                    tc.preprocessor_definitions["DEFINITIONS_CONFIG"] = "Debug"
                else:
                    tc.preprocessor_definitions["DEFINITIONS_CONFIG"] = "Release"

                tc.generate()
                gen.generate()

            def imports(self):
                if self.options["hello"].shared and self.settings.build_type == "Release":
                    configuration = "ReleaseShared"
                else:
                    configuration = self.settings.build_type
                self.copy("*.dll", src="bin",
                          dst="%s/%s" % (self.settings.arch, configuration),
                          keep_path=False)

            def build(self):
                msbuild = MSBuild(self)
                msbuild.build("MyProject.sln")
        """)
    app = gen_function_cpp(name="main", includes=["hello"], calls=["hello"],
                           preprocessor=["DEFINITIONS_BOTH", "DEFINITIONS_CONFIG"])

    @staticmethod
    def _run_app(client, arch, build_type, shared=None):
        if build_type == "Release" and shared:
            configuration = "ReleaseShared"
        else:
            configuration = build_type

        if arch == "x86":
            command_str = "%s\\MyApp.exe" % configuration
        else:
            command_str = "x64\\%s\\MyApp.exe" % configuration
        # To run the app without VS IDE, we need to copy the .exe to the DLLs folder
        new_cmd = "conan\\%s\\%s\\MyApp.exe" % (arch, configuration)
        with chdir(client.current_folder):
            mkdir(os.path.dirname(new_cmd))
            shutil.copy(command_str, new_cmd)
        client.run_command(new_cmd)

    @parameterized.expand([("Visual Studio", "15", "MT", "17"),
                           ("msvc", "19.1", "static", "17"),
                           ("msvc", "19.0", "static", "14")]
                          )
    @pytest.mark.tool_cmake
    def test_toolchain_win(self, compiler, version, runtime, cppstd):
        client = TestClient(path_with_spaces=False)
        settings = [("compiler", compiler),
                    ("compiler.version", version),
                    ("compiler.cppstd", cppstd),
                    ("compiler.runtime", runtime),
                    ("build_type", "Release"),
                    ("arch", "x86")]

        profile = textwrap.dedent("""
            [settings]
            os=Windows

            [conf]
            tools.microsoft.msbuild:vs_version=15
            """)
        client.save({"myprofile": profile})
        # Build the profile according to the settings provided
        settings = " ".join('-s %s="%s"' % (k, v) for k, v in settings if v)

        client.run("new hello/0.1 -m=v2_cmake")
        client.run("create . hello/0.1@ %s" % (settings, ))

        # Prepare the actual consumer package
        client.save({"conanfile.py": self.conanfile,
                     "MyProject.sln": sln_file,
                     "MyApp/MyApp.vcxproj": myapp_vcxproj,
                     "MyApp/MyApp.cpp": self.app,
                     "myprofile": profile},
                    clean_first=True)

        # Run the configure corresponding to this test case
        client.run("build . %s -if=conan -pr=myprofile" % (settings, ))
        self.assertIn("conanfile.py: MSBuildToolchain created conantoolchain_release_win32.props",
                      client.out)
        self.assertIn("Visual Studio 2017", client.out)
        self.assertIn("[vcvarsall.bat] Environment initialized for: 'x86'", client.out)

        self._run_app(client, "x86", "Release")
        self.assertIn("Hello World Release", client.out)
        compiler_version = version if compiler == "msvc" else "19.1"
        check_exe_run(client.out, "main", "msvc", compiler_version, "Release", "x86", cppstd,
                      {"DEFINITIONS_BOTH": "True",
                       "DEFINITIONS_CONFIG": "Release"})
        check_vs_runtime("Release/MyApp.exe", client, "15", static=True, build_type="Release")

    @pytest.mark.tool_cmake
    def test_toolchain_win_debug(self):
        client = TestClient(path_with_spaces=False)
        settings = [("compiler",  "Visual Studio"),
                    ("compiler.version",  "15"),
                    ("compiler.toolset",  "v140"),
                    ("compiler.runtime",  "MDd"),
                    ("build_type",  "Debug"),
                    ("arch",  "x86_64")]

        # Build the profile according to the settings provided
        settings = " ".join('-s %s="%s"' % (k, v) for k, v in settings if v)

        client.run("new hello/0.1 -s")
        client.run("create . hello/0.1@ %s" % (settings,))

        # Prepare the actual consumer package
        client.save({"conanfile.py": self.conanfile,
                     "MyProject.sln": sln_file,
                     "MyApp/MyApp.vcxproj": myapp_vcxproj,
                     "MyApp/MyApp.cpp": self.app},
                    clean_first=True)

        # Run the configure corresponding to this test case
        client.run("build . %s -if=conan" % (settings, ))
        self.assertIn("conanfile.py: MSBuildToolchain created conantoolchain_debug_x64.props",
                      client.out)
        self.assertIn("Visual Studio 2017", client.out)
        self.assertIn("[vcvarsall.bat] Environment initialized for: 'x64'", client.out)
        self._run_app(client, "x64", "Debug")
        self.assertIn("Hello World Debug", client.out)
        check_exe_run(client.out, "main", "msvc", "19.0", "Debug", "x86_64", "14",
                      {"DEFINITIONS_BOTH": "True",
                       "DEFINITIONS_CONFIG": "Debug"})
        check_vs_runtime("x64/Debug/MyApp.exe", client, "15", static=False, build_type="Debug")

    @pytest.mark.tool_cmake
    def test_toolchain_win_multi(self):
        client = TestClient(path_with_spaces=False)

        settings = [("compiler", "Visual Studio"),
                    ("compiler.version", "15"),
                    ("compiler.cppstd", "17")]

        settings = " ".join('-s %s="%s"' % (k, v) for k, v in settings if v)
        client.run("new hello/0.1 -s")
        configs = [("Release", "x86", True), ("Release", "x86_64", True),
                   ("Debug", "x86", False), ("Debug", "x86_64", False)]
        for build_type, arch, shared in configs:
            # Build the profile according to the settings provided
            runtime = "MT" if build_type == "Release" else "MTd"
            client.run("create . hello/0.1@ %s -s build_type=%s -s arch=%s -s compiler.runtime=%s "
                       " -o hello:shared=%s" % (settings, build_type, arch, runtime, shared))

        # Prepare the actual consumer package
        client.save({"conanfile.py": self.conanfile,
                     "MyProject.sln": sln_file,
                     "MyApp/MyApp.vcxproj": myapp_vcxproj,
                     "MyApp/MyApp.cpp": self.app},
                    clean_first=True)

        # Run the configure corresponding to this test case
        for build_type, arch, shared in configs:
            runtime = "MT" if build_type == "Release" else "MTd"
            client.run("install . %s -s build_type=%s -s arch=%s -s compiler.runtime=%s -if=conan"
                       " -o hello:shared=%s" % (settings, build_type, arch, runtime, shared))

        vs_path = vs_installation_path("15")
        vcvars_path = os.path.join(vs_path, "VC/Auxiliary/Build/vcvarsall.bat")

        for build_type, arch, shared in configs:
            platform_arch = "x86" if arch == "x86" else "x64"
            if build_type == "Release" and shared:
                configuration = "ReleaseShared"
            else:
                configuration = build_type

            # The "conan build" command is not good enough, cannot do the switch between configs
            cmd = ('set "VSCMD_START_DIR=%%CD%%" && '
                   '"%s" x64 && msbuild "MyProject.sln" /p:Configuration=%s '
                   '/p:Platform=%s ' % (vcvars_path, configuration, platform_arch))
            client.run_command(cmd)
            self.assertIn("Visual Studio 2017", client.out)
            self.assertIn("[vcvarsall.bat] Environment initialized for: 'x64'", client.out)

            self._run_app(client, arch, build_type, shared)
            check_exe_run(client.out, "main", "msvc", "19.1", build_type, arch, "17",
                          {"DEFINITIONS_BOTH": "True",
                           "DEFINITIONS_CONFIG": build_type})

            new_cmd = "conan\\%s\\%s\\MyApp.exe" % (arch, configuration)
            vcvars = vcvars_command(version="15", architecture="amd64")
            cmd = ('%s && dumpbin /dependents "%s"' % (vcvars, new_cmd))
            client.run_command(cmd)
            if shared:
                self.assertIn("hello.dll", client.out)
            else:
                self.assertNotIn("hello.dll", client.out)
            self.assertIn("KERNEL32.dll", client.out)
