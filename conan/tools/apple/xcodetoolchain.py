import os
import textwrap

from conan.tools._check_build_profile import check_using_build_profile
from conan.tools.apple.apple import to_apple_arch
from conan.tools.build import build_jobs
from conan.tools.intel.intel_cc import IntelCC
from conan.tools.microsoft.visual import VCVars
from conans.errors import ConanException
from conans.util.files import save, load


class XcodeToolchain(object):
    filename = "conantoolchain.xcconfig"

    _vars_xconfig = textwrap.dedent("""\
        // Definition of Conan variables for {{name}}
        OTHER_CFLAGS[config={{configuration}}][arch={{architecture}}] = $(inherited) {{c_compiler_flags}}
        OTHER_CPLUSPLUSFLAGS[config={{configuration}}][arch={{architecture}}] = $(inherited) {{cxx_compiler_flags}}
        OTHER_LDFLAGS[config={{configuration}}][arch={{architecture}}] = $(inherited) {{linker_flags}}
        GCC_PREPROCESSOR_DEFINITIONS[config={{configuration}}][arch={{architecture}}] = $(inherited) {{definitions}}
        """)

    _all_xconfig = textwrap.dedent("""\
        // Conan XcodeDeps generated file
        // Includes all direct dependencies
        """)

    def __init__(self, conanfile):
        self._conanfile = conanfile
        self.preprocessor_definitions = {}
        self.compile_options = {}
        self.configuration = conanfile.settings.build_type
        self.cppstd = conanfile.settings.get_safe("compiler.cppstd") # CLANG_CXX_LANGUAGE_STANDARD
        # self.libstd = # CLANG_CXX_LIBRARY
        arch = conanfile.settings.get_safe("arch")
        self.architecture = to_apple_arch(arch) or arch
        self.os_version = conanfile.settings.get_safe("os.version")
        self._sdk = conanfile.settings.get_safe("os.sdk") or ""
        self._sdk_version = conanfile.settings.get_safe("os.sdk_version") or ""
        check_using_build_profile(self._conanfile)

    def generate(self):
        if self.configuration is None:
            raise ConanException("XcodeToolchain.configuration is None, it should have a value")
        if self.architecture is None:
            raise ConanException("XcodeToolchain.architecture is None, it should have a value")
        generator_files = self._content()
        for generator_file, content in generator_files.items():
            save(generator_file, content)

    def _config_filename(self):
        # Default name
        props = [("configuration", self.configuration),
                 ("architecture", self.architecture)]
        name = "".join("_{}".format(v) for _, v in props if v is not None)
        name = self.filename + name + ".xcconfig"
        return name.lower()

    def _vars_xconfig_file(self, dep, name, cpp_info):
        """
        content for conan_vars_poco_x86_release.xcconfig, containing the variables
        """
        # returns a .xcconfig file with the variables definition for one package for one configuration

        pkg_placeholder = "$(CONAN_{}_ROOT_FOLDER_{})/".format(name, self.configuration)
        fields = {
            'name': name,
            'configuration': self.configuration,
            'architecture': self.architecture,
            'definitions': " ".join(cpp_info.defines),
            'c_compiler_flags': " ".join(cpp_info.cflags),
            'cxx_compiler_flags': " ".join(cpp_info.cxxflags),
            'linker_flags': " ".join(cpp_info.sharedlinkflags),
            'exe_flags': " ".join(cpp_info.exelinkflags),
        }
        formatted_template = Template(self._vars_xconfig).render(**fields)
        return formatted_template

    def _conf_xconfig_file(self, dep_name, vars_xconfig_name):
        """
        content for conan_poco_x86_release.xcconfig, containing the activation
        """
        # TODO: when it's more clear what to do with the sdk, add the condition for it and also
        #  we are not taking into account the version for the sdk because we probably
        #  want to model also the sdk version decoupled of the compiler version
        #  for example XCode 13 is now using sdk=macosx11.3
        #  related to: https://github.com/conan-io/conan/issues/9608
        template = Template(self._conf_xconfig)
        content_multi = template.render(name=dep_name, vars_filename=vars_xconfig_name)
        return content_multi

    def _dep_xconfig_file(self, name, name_general, dep_xconfig_filename, deps):
        # Current directory is the generators_folder
        multi_path = name_general
        if os.path.isfile(multi_path):
            content_multi = load(multi_path)
        else:
            content_multi = self._dep_xconfig
            content_multi = Template(content_multi).render({"name": name,
                                                            "dep_xconfig_filename": dep_xconfig_filename,
                                                            "deps": deps})

        if dep_xconfig_filename not in content_multi:
            content_multi = content_multi.replace('.xcconfig"',
                                                  '.xcconfig"\n#include "{}"'.format(dep_xconfig_filename),
                                                  1)

        return content_multi

    def _add_xconfig_file_to_general(self, conf):
        """
        this is a .xcconfig file including all declared dependencies
        """
        content_multi = self._all_xconfig
        content_multi = content_multi + '\n#include "{}"\n'.format(conf)
        return content_multi

    def _content(self):
        result = {}
        general_name = self.filename
        result[general_name] = self._add_xconfig_file_to_general(self._config_filename())
        result[self._config_filename()] =

            # One file per configuration, with just the variables
            vars_xconfig_name = "conan_{}_vars{}.xcconfig".format(dep_name, conf_name)
            result[vars_xconfig_name] = self._vars_xconfig_file(dep, dep_name, cpp_info)
            props_name = "conan_{}{}.xcconfig".format(dep_name, conf_name)
            result[props_name] = self._conf_xconfig_file(dep_name, vars_xconfig_name)

            # The entry point for each package
            file_dep_name = "conan_{}.xcconfig".format(dep_name)
            dep_content = self._dep_xconfig_file(dep_name, file_dep_name, props_name, public_deps)
            result[file_dep_name] = dep_content

        # Include all direct build_requires for host context.
        direct_deps = self._conanfile.dependencies.filter({"direct": True, "build": False})

        return result
