import os

from conan.tools.apple.apple import to_apple_arch
from conans.errors import ConanException


class XcodeBuild(object):
    def __init__(self, conanfile):
        self._conanfile = conanfile
        self.build_type = conanfile.settings.get_safe("build_type")
        self.arch = to_apple_arch(conanfile.settings.get_safe("arch"))
        self._sdk = conanfile.settings.get_safe("os.sdk") or ""
        self._sdk_version = conanfile.settings.get_safe("os.sdk_version") or ""

    @property
    def verbosity(self):
        verbosity = self._conanfile.conf["tools.apple.xcodebuild:verbosity"]
        if not verbosity:
            return ""
        elif verbosity == "quiet" or verbosity == "verbose":
            return "-{}".format(verbosity)
        else:
            raise ConanException("Value {} for 'tools.apple.xcodebuild:verbosity' is not valid".format(verbosity))

    @property
    def sdk(self):
        # TODO: probably move to tools if other build systems use the same argument
        # User's sdk_path has priority, then if specified try to compose sdk argument
        # with sdk/sdk_version settings, leave blank otherwise and the sdk will be automatically
        # chosen by the build system
        sdk = self._conanfile.conf["tools.apple:sdk_path"]
        if not sdk and self._sdk:
            sdk = "{}{}".format(self._sdk, self._sdk_version)
        return "-sdk={}".format(sdk) if sdk else ""

    def build(self, xcodeproj, use_xcconfig=True):
        xcconfig = " -xcconfig {}".format(os.path.join(self._conanfile.folders.generators,
                                                       "conandeps.xcconfig")) if use_xcconfig else ""
        cmd = "xcodebuild -project {}{} {} -configuration {} -arch {} {}".format(xcodeproj,
                                                                                 xcconfig,
                                                                                 self.sdk,
                                                                                 self.build_type,
                                                                                 self.arch,
                                                                                 self.verbosity)
        self._conanfile.run(cmd)
