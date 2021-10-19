import json
import os
import platform
import re
import subprocess
import warnings
from collections import namedtuple
from contextlib import contextmanager

from conans.cli.output import ConanOutput
from conans.client.tools import which
from conans.client.tools.env import environment_append
from conans.client.tools.oss import OSInfo, detected_architecture, get_build_os_arch
from conans.errors import ConanException
from conans.model.version import Version
from conans.util.conan_v2_mode import conan_v2_error
from conans.util.env_reader import get_env
from conans.util.files import mkdir_tmp, save
from conans.util.runners import check_output_runner


def _system_registry_key(key, subkey, query):
    import winreg
    try:
        hkey = winreg.OpenKey(key, subkey)
    except (OSError, WindowsError):  # Raised by OpenKey/Ex if the function fails (py3, py2)
        return None
    else:
        try:
            value, _ = winreg.QueryValueEx(hkey, query)
            return value
        except EnvironmentError:
            return None
        finally:
            winreg.CloseKey(hkey)


def is_win64():
    import winreg
    return _system_registry_key(winreg.HKEY_LOCAL_MACHINE,
                                r"SOFTWARE\Microsoft\Windows\CurrentVersion",
                                "ProgramFilesDir (x86)") is not None


def _visual_compiler(version):
    """"version have to be 8.0, or 9.0 or... anything .0"""
    if Version(version) >= "15":
        vs_path = os.getenv('vs%s0comntools' % version)
        path = vs_path or vs_installation_path(version)
        if path:
            compiler = "Visual Studio"
            ConanOutput().success("Found %s %s" % (compiler, version))
            return compiler, version
        return None

    version = "%s.0" % version

    import winreg
    if is_win64():
        key_name = r'SOFTWARE\Wow6432Node\Microsoft\VisualStudio\SxS\VC7'
    else:
        key_name = r'SOFTWARE\Microsoft\VisualStudio\SxS\VC7'

    if _system_registry_key(winreg.HKEY_LOCAL_MACHINE, key_name, version):
        installed_version = Version(version).major(fill=False)
        compiler = "Visual Studio"
        ConanOutput().success("Found %s %s" % (compiler, installed_version))
        return compiler, installed_version

    return None


def latest_vs_version_installed():
    return latest_visual_studio_version_installed()


MSVS_YEAR = {"17": "2022",
             "16": "2019",
             "15": "2017",
             "14": "2015",
             "12": "2013",
             "11": "2012",
             "10": "2010",
             "9": "2008",
             "8": "2005"}


MSVS_DEFAULT_TOOLSETS = {"17": "v143",
                         "16": "v142",
                         "15": "v141",
                         "14": "v140",
                         "12": "v120",
                         "11": "v110",
                         "10": "v100",
                         "9": "v90",
                         "8": "v80"}

# inverse version of the above MSVS_DEFAULT_TOOLSETS (keys and values are swapped)
MSVS_DEFAULT_TOOLSETS_INVERSE = {"v143": "17",
                                 "v142": "16",
                                 "v141": "15",
                                 "v140": "14",
                                 "v120": "12",
                                 "v110": "11",
                                 "v100": "10",
                                 "v90": "9",
                                 "v80": "8"}


def msvs_toolset(conanfile):
    from conans.model.conan_file import ConanFile

    if isinstance(conanfile, ConanFile):
        settings = conanfile.settings
    else:
        settings = conanfile
    toolset = settings.get_safe("compiler.toolset")
    if not toolset:
        compiler = settings.get_safe("compiler")
        compiler_version = settings.get_safe("compiler.version")
        if compiler == "intel":
            compiler_version = compiler_version if "." in compiler_version else \
                "%s.0" % compiler_version
            toolset = "Intel C++ Compiler " + compiler_version
        else:
            toolset = MSVS_DEFAULT_TOOLSETS.get(compiler_version)
    return toolset


def latest_visual_studio_version_installed():
    msvc_sersions = reversed(sorted(list(MSVS_DEFAULT_TOOLSETS.keys()), key=int))
    for version in msvc_sersions:
        vs = _visual_compiler(version)
        if vs:
            return vs[1]
    return None


def vs_installation_path(version, preference=None):

    if not preference:
        preference = get_env("CONAN_VS_INSTALLATION_PREFERENCE", list())
        if not preference:  # default values
            preference = ["Enterprise", "Professional", "Community", "BuildTools"]

    # Try with vswhere()
    try:
        legacy_products = vswhere(legacy=True)
        all_products = vswhere(products=["*"])
        products = legacy_products + all_products
    except ConanException:
        products = None

    vs_paths = []

    if products:
        # remove repeated products
        seen_products = []
        for product in products:
            if product not in seen_products:
                seen_products.append(product)

        # Append products with "productId" by order of preference
        for product_type in preference:
            for product in seen_products:
                product = dict(product)
                if (product["installationVersion"].startswith(("%d." % int(version)))
                        and "productId" in product):
                    if product_type in product["productId"]:
                        vs_paths.append(product["installationPath"])

        # Append products without "productId" (Legacy installations)
        for product in seen_products:
            product = dict(product)
            if (product["installationVersion"].startswith(("%d." % int(version)))
                    and "productId" not in product):
                vs_paths.append(product["installationPath"])

    # If vswhere does not find anything or not available, try with vs_comntools()
    if not vs_paths:
        vs_path = vs_comntools(version)

        if vs_path:
            sub_path_to_remove = os.path.join("", "Common7", "Tools", "")
            # Remove '\\Common7\\Tools\\' to get same output as vswhere
            if vs_path.endswith(sub_path_to_remove):
                vs_path = vs_path[:-(len(sub_path_to_remove)+1)]

        result_vs_installation_path = vs_path
    else:
        result_vs_installation_path = vs_paths[0]

    return result_vs_installation_path


def vswhere(all_=False, prerelease=False, products=None, requires=None, version="", latest=False,
            legacy=False, property_="", nologo=True):

    # 'version' option only works if Visual Studio 2017 is installed:
    # https://github.com/Microsoft/vswhere/issues/91

    products = list() if products is None else products
    requires = list() if requires is None else requires

    if legacy and (products or requires):
        raise ConanException("The 'legacy' parameter cannot be specified with either the "
                             "'products' or 'requires' parameter")

    installer_path = None
    program_files = get_env("ProgramFiles(x86)") or get_env("ProgramFiles")
    if program_files:
        expected_path = os.path.join(program_files, "Microsoft Visual Studio", "Installer",
                                     "vswhere.exe")
        if os.path.isfile(expected_path):
            installer_path = expected_path
    vswhere_path = installer_path or which("vswhere")

    if not vswhere_path:
        raise ConanException("Cannot locate vswhere in 'Program Files'/'Program Files (x86)' "
                             "directory nor in PATH")

    arguments = list()
    arguments.append(vswhere_path)

    # Output json format
    arguments.append("-format")
    arguments.append("json")

    if all_:
        arguments.append("-all")

    if prerelease:
        arguments.append("-prerelease")

    if products:
        arguments.append("-products")
        arguments.extend(products)

    if requires:
        arguments.append("-requires")
        arguments.extend(requires)

    if len(version) != 0:
        arguments.append("-version")
        arguments.append(version)

    if latest:
        arguments.append("-latest")

    if legacy:
        arguments.append("-legacy")

    if len(property_) != 0:
        arguments.append("-property")
        arguments.append(property_)

    if nologo:
        arguments.append("-nologo")

    try:
        output = check_output_runner(arguments).strip()
        # Ignore the "description" field, that even decoded contains non valid charsets for json
        # (ignored ones)
        output = "\n".join([line for line in output.splitlines()
                            if not line.strip().startswith('"description"')])

    except (ValueError, subprocess.CalledProcessError, UnicodeDecodeError) as e:
        raise ConanException("vswhere error: %s" % str(e))

    return json.loads(output)


def vs_comntools(compiler_version):
    env_var = "vs%s0comntools" % compiler_version
    vs_path = os.getenv(env_var)
    return vs_path


def find_windows_10_sdk():
    """finds valid Windows 10 SDK version which can be passed to vcvarsall.bat (vcvars_command)"""
    # uses the same method as VCVarsQueryRegistry.bat
    import winreg
    hives = [
        (winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\Wow6432Node'),
        (winreg.HKEY_CURRENT_USER, r'SOFTWARE\Wow6432Node'),
        (winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE'),
        (winreg.HKEY_CURRENT_USER, r'SOFTWARE')
    ]
    for key, subkey in hives:
        subkey = r'%s\Microsoft\Microsoft SDKs\Windows\v10.0' % subkey
        installation_folder = _system_registry_key(key, subkey, 'InstallationFolder')
        if installation_folder and os.path.isdir(installation_folder):
            include_dir = os.path.join(installation_folder, 'include')
            for sdk_version in os.listdir(include_dir):
                if (os.path.isdir(os.path.join(include_dir, sdk_version))
                        and sdk_version.startswith('10.')):
                    windows_h = os.path.join(include_dir, sdk_version, 'um', 'Windows.h')
                    if os.path.isfile(windows_h):
                        return sdk_version
    return None


def vcvars_command(conanfile=None, arch=None, compiler_version=None, force=False, vcvars_ver=None,
                   winsdk_version=None, settings=None):
    # Handle input arguments (backwards compatibility with 'settings' as first argument)
    # TODO: This can be promoted to a decorator pattern for any function
    if conanfile and settings:
        raise ConanException("Do not set both arguments, 'conanfile' and 'settings',"
                             " to call 'vcvars_command' function")

    from conans.model.conan_file import ConanFile
    if conanfile and not isinstance(conanfile, ConanFile):
        return vcvars_command(settings=conanfile, arch=arch, compiler_version=compiler_version,
                              force=force, vcvars_ver=vcvars_ver, winsdk_version=winsdk_version)

    if settings:
        warnings.warning("argument 'settings' has been deprecated, use 'conanfile' instead")

    if not conanfile:
        # TODO: If Conan is using 'profile_build' here we don't have any information about it,
        #   we are falling back to the old behavior (which is probably wrong here)
        conanfile = namedtuple('_ConanFile', ['settings'])(settings)
    del settings

    # Here starts the actual implementation for this function
    output = ConanOutput()

    arch_setting = arch or conanfile.settings.get_safe("arch")

    compiler = conanfile.settings.get_safe("compiler")
    compiler_base = conanfile.settings.get_safe("compiler.base")
    if compiler == 'Visual Studio':
        compiler_version = compiler_version or conanfile.settings.get_safe("compiler.version")
    elif compiler_base == "Visual Studio":
        compiler_version = compiler_version or conanfile.settings.get_safe("compiler.base.version")
    else:
        # vcvars might be still needed for other compilers, e.g. clang-cl or Intel C++,
        # as they might be using Microsoft STL and other tools
        # (e.g. resource compiler, manifest tool, etc)
        # in this case, use the latest Visual Studio available on the machine
        last_version = latest_vs_version_installed()

        compiler_version = compiler_version or last_version
    os_setting = conanfile.settings.get_safe("os")
    if not compiler_version:
        raise ConanException("compiler.version setting required for vcvars not defined")

    # https://msdn.microsoft.com/en-us/library/f2ccy3wt.aspx
    vcvars_arch = None
    arch_setting = arch_setting or 'x86_64'

    _, settings_arch_build = get_build_os_arch(conanfile)
    arch_build = settings_arch_build
    if not hasattr(conanfile, 'settings_build'):
        arch_build = arch_build or detected_architecture()

    if os_setting == 'WindowsCE':
        vcvars_arch = "x86"
    elif arch_build == 'x86_64':
        # Only uses x64 tooling if arch_build explicitly defines it, otherwise
        # Keep the VS default, which is x86 toolset
        # This will probably be changed in conan 2.0
        if ((settings_arch_build or os.getenv("PreferredToolArchitecture") == "x64")
           and int(compiler_version) >= 12):
            x86_cross = "amd64_x86"
        else:
            x86_cross = "x86"
        vcvars_arch = {'x86': x86_cross,
                       'x86_64': 'amd64',
                       'armv7': 'amd64_arm',
                       'armv8': 'amd64_arm64'}.get(arch_setting)
    elif arch_build == 'x86':
        vcvars_arch = {'x86': 'x86',
                       'x86_64': 'x86_amd64',
                       'armv7': 'x86_arm',
                       'armv8': 'x86_arm64'}.get(arch_setting)

    if not vcvars_arch:
        raise ConanException('unsupported architecture %s' % arch_setting)

    existing_version = os.environ.get("VisualStudioVersion")

    if existing_version:
        command = ["echo Conan:vcvars already set"]
        existing_version = existing_version.split(".")[0]
        if existing_version != compiler_version:
            message = "Visual environment already set to %s\n " \
                      "Current settings visual version: %s" % (existing_version, compiler_version)
            if not force:
                raise ConanException("Error, %s" % message)
            else:
                output.warning(message)
    else:
        vs_path = vs_installation_path(str(compiler_version))

        if not vs_path or not os.path.isdir(vs_path):
            raise ConanException("VS non-existing installation: Visual Studio %s"
                                 % str(compiler_version))
        else:
            if int(compiler_version) > 14:
                vcvars_path = os.path.join(vs_path, "VC/Auxiliary/Build/vcvarsall.bat")
                command = ['set "VSCMD_START_DIR=%%CD%%" && '
                           'call "%s" %s' % (vcvars_path, vcvars_arch)]
            else:
                vcvars_path = os.path.join(vs_path, "VC/vcvarsall.bat")
                command = ['call "%s" %s' % (vcvars_path, vcvars_arch)]
        if int(compiler_version) >= 14:
            if winsdk_version:
                command.append(winsdk_version)
            if vcvars_ver:
                command.append("-vcvars_ver=%s" % vcvars_ver)

        if os_setting == 'WindowsStore':
            os_version_setting = conanfile.settings.get_safe("os.version")
            if os_version_setting == '8.1':
                winsdk_version = winsdk_version or "8.1"
                command.append('store %s' % winsdk_version)
            elif os_version_setting == '10.0':
                winsdk_version = winsdk_version or find_windows_10_sdk()
                if not winsdk_version:
                    raise ConanException("cross-compiling for WindowsStore 10 (UWP), "
                                         "but Windows 10 SDK wasn't found")
                command.append('store %s' % winsdk_version)
            else:
                raise ConanException('unsupported Windows Store version %s' % os_version_setting)
    return " ".join(command)


def vcvars_dict(conanfile=None, arch=None, compiler_version=None, force=False,
                filter_known_paths=False, vcvars_ver=None, winsdk_version=None, only_diff=True,
                settings=None):
    known_path_lists = ("include", "lib", "libpath", "path")
    cmd = vcvars_command(conanfile, settings=settings, arch=arch,
                         compiler_version=compiler_version, force=force,
                         vcvars_ver=vcvars_ver, winsdk_version=winsdk_version)
    cmd += " && set"
    ret = check_output_runner(cmd)
    new_env = {}
    for line in ret.splitlines():
        line = line.strip()

        if line == "\n" or not line:
            continue
        try:
            name_var, value = line.split("=", 1)
            new_value = value.split(os.pathsep) if name_var.lower() in known_path_lists else value
            # Return only new vars & changed ones, but only with the changed elements if the var is
            # a list
            if only_diff:
                old_value = os.environ.get(name_var)
                if name_var.lower() == "path":
                    old_values_lower = [v.lower() for v in old_value.split(os.pathsep)]
                    # Clean all repeated entries, not append if the element was already there
                    new_env[name_var] = [v for v in new_value if v.lower() not in old_values_lower]
                elif old_value and value.endswith(os.pathsep + old_value):
                    # The new value ends with separator and the old value, is a list,
                    # get only the new elements
                    new_env[name_var] = value[:-(len(old_value) + 1)].split(os.pathsep)
                elif value != old_value:
                    # Only if the vcvars changed something, we return the variable,
                    # otherwise is not vcvars related
                    new_env[name_var] = new_value
            else:
                new_env[name_var] = new_value

        except ValueError:
            pass

    if filter_known_paths:
        def relevant_path(_path):
            _path = _path.replace("\\", "/").lower()
            keywords = "msbuild", "visual", "microsoft", "/msvc/", "/vc/", "system32", "windows"
            return any(word in _path for word in keywords)

        path_key = next((name for name in new_env.keys() if "path" == name.lower()), None)
        if path_key:
            path = [entry for entry in new_env.get(path_key, "") if relevant_path(entry)]
            new_env[path_key] = ";".join(path)

    return new_env


MSYS2 = 'msys2'
MSYS = 'msys'
CYGWIN = 'cygwin'
WSL = 'wsl'  # Windows Subsystem for Linux
SFU = 'sfu'  # Windows Services for UNIX
