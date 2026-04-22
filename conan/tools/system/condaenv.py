import os
import platform as _platform
import shutil
import stat

from conan.api.output import ConanOutput
from conan.errors import ConanException, ConanInvalidConfiguration
from conan.internal.paths import get_conan_user_home
from conan.tools.env.environment import Environment


def _conan_to_conda_subdir(settings):
    """Map Conan settings to the conda subdir string."""
    conan_os = str(settings.os) if settings.get_safe("os") else _platform.system()
    conan_arch = str(settings.arch) if settings.get_safe("arch") else None

    if conan_os == "Linux":
        if conan_arch == "x86_64":
            return "linux-64"
        if conan_arch == "armv8":
            return "linux-aarch64"
    elif conan_os == "Windows":
        if conan_arch == "x86_64":
            return "win-64"
    elif conan_os == "Macos":
        if conan_arch == "x86_64":
            return "osx-64"
        if conan_arch == "armv8":
            return "osx-arm64"
    raise ConanInvalidConfiguration(
        f"CondaEnv: Platform {conan_os}/{conan_arch} is not supported by conda channels"
    )


class CondaEnv:
    """
    Helper that creates a local conda environment inside a recipe using micromamba
    as the solver, and exposes the resulting prefix to the rest of the Conan build.

    Mirrors the design of ``conan.tools.system.PyEnv``.
    """

    def __init__(self, conanfile, channels=None, platform=None):
        """
        :param conanfile: The current conanfile ``self``.
        :param channels: List of conda channels in priority order. Defaults to
                         the value of ``tools.system.condaenv:default_channels`` or
                         ``["conda-forge"]``.
        :param platform: Optional conda subdir (e.g. ``"linux-64"``). Auto-detected
                         from ``conanfile.settings`` if not provided.
        """
        self._conanfile = conanfile

        default_channels = conanfile.conf.get("tools.system.condaenv:default_channels",
                                              check_type=list, default=None)
        self._channels = list(channels) if channels is not None else (default_channels or
                                                                      ["conda-forge"])
        # Platform is resolved lazily: it reads ``conanfile.settings``, which is
        # forbidden inside ``finalize()`` — and ``unpack_archive()`` is designed
        # to be called from there.
        self._platform_override = platform

        generators_folder = (conanfile.generators_folder or conanfile.build_folder
                             or os.getcwd())
        self._env_dir = os.path.abspath(os.path.join(generators_folder, "condaenv"))

        self._installed = []
        self._micromamba_exe = None

    @property
    def _platform(self):
        if self._platform_override:
            return self._platform_override
        return _conan_to_conda_subdir(self._conanfile.settings)

    @property
    def env_dir(self):
        """Absolute path to the conda environment prefix."""
        return self._env_dir.replace("\\", "/")

    @property
    def micromamba_exe(self):
        """
        Resolve the micromamba executable. ``CondaEnv`` does NOT install it;
        the user is expected to have it on the host. Resolution order:

        1. ``tools.system.condaenv:micromamba_path`` conf
        2. ``CONAN_CONDAENV_MICROMAMBA`` environment variable
        3. ``shutil.which("micromamba")``

        If none of these resolve, a :class:`ConanException` is raised with
        install instructions.
        """
        if self._micromamba_exe is None:
            self._micromamba_exe = self._resolve_micromamba()
        return self._micromamba_exe

    def _resolve_micromamba(self):
        conf_path = self._conanfile.conf.get("tools.system.condaenv:micromamba_path")
        if conf_path:
            if not os.path.isfile(conf_path):
                raise ConanException(
                    f"CondaEnv: 'tools.system.condaenv:micromamba_path' points to "
                    f"'{conf_path}' which does not exist")
            return conf_path

        env_path = os.environ.get("CONAN_CONDAENV_MICROMAMBA")
        if env_path:
            if not os.path.isfile(env_path):
                raise ConanException(
                    f"CondaEnv: CONAN_CONDAENV_MICROMAMBA='{env_path}' does not exist")
            return env_path

        found = shutil.which("micromamba")
        if found:
            return found

        raise ConanException(
            "CondaEnv: 'micromamba' not found. Install it system-wide (e.g. "
            "`brew install micromamba`, `conda install -n base micromamba`, or follow "
            "https://mamba.readthedocs.io/en/latest/installation/micromamba-installation.html) "
            "and add it to PATH, set the 'CONAN_CONDAENV_MICROMAMBA' environment variable, "
            "or configure 'tools.system.condaenv:micromamba_path'")

    def _micromamba_cache_dir(self):
        root = self._conanfile.conf.get("tools.system.condaenv:root_prefix",
                                        default=os.path.join(get_conan_user_home(), "condaenv"))
        return root

    def _base_cmd(self):
        root_prefix = self._micromamba_cache_dir()
        # micromamba needs MAMBA_ROOT_PREFIX to know where to store its package cache
        env_prefix = f'MAMBA_ROOT_PREFIX="{root_prefix}" ' if os.name != "nt" \
            else f'set "MAMBA_ROOT_PREFIX={root_prefix}" && '
        return env_prefix

    def _run_micromamba(self, subcommand, packages):
        channel_args = []
        for ch in self._channels:
            channel_args.extend(["-c", ch])
        cmd = [
            f'"{self.micromamba_exe}"',
            subcommand,
            "-p", f'"{self._env_dir}"',
            "--yes",
            "--no-rc",
            "--no-env",
            "--platform", self._platform,
            "--strict-channel-priority",
        ] + channel_args + [f'"{p}"' for p in packages]
        command = self._base_cmd() + " ".join(cmd)
        self._conanfile.run(command)

    def install(self, *packages):
        """
        Install one or more conda packages into the local environment. Can be called
        multiple times; additional calls install into the existing prefix.

        :param packages: Package specs, e.g. ``"numpy>=1.26"`` or ``"ros-kilted-ros-base"``.
        """
        if not packages:
            return
        pkgs = list(packages)
        subcommand = "create" if not os.path.isdir(self._env_dir) else "install"
        self._run_micromamba(subcommand, pkgs)
        self._installed.extend(pkgs)

    # ---- Packaging helpers (relocatability) ------------------------------------

    def _conda_pack_tool_env(self):
        return os.path.join(self._micromamba_cache_dir(), "tools", "conda-pack")

    def _resolve_conda_pack(self):
        """Resolve the ``conda-pack`` CLI. Same 3-tier pattern as micromamba."""
        conf_path = self._conanfile.conf.get("tools.system.condaenv:conda_pack_path")
        if conf_path:
            if not os.path.isfile(conf_path):
                raise ConanException(
                    f"CondaEnv: 'tools.system.condaenv:conda_pack_path' points to "
                    f"'{conf_path}' which does not exist")
            return conf_path

        found = shutil.which("conda-pack")
        if found:
            return found

        tool_env = self._conda_pack_tool_env()
        exe = os.path.join(tool_env, "Scripts", "conda-pack.exe") if os.name == "nt" \
            else os.path.join(tool_env, "bin", "conda-pack")
        if os.path.isfile(exe):
            return exe

        channel_args = ["-c", "conda-forge"]
        cmd = [
            f'"{self.micromamba_exe}"',
            "create",
            "-p", f'"{tool_env}"',
            "--yes", "--no-rc", "--no-env",
            "--strict-channel-priority",
        ] + channel_args + ['"conda-pack"']
        command = self._base_cmd() + " ".join(cmd)
        self._conanfile.run(command)

        if not os.path.isfile(exe):
            raise ConanException(
                f"CondaEnv: conda-pack was not materialized at {exe} after install. "
                f"Check the micromamba output above.")
        return exe

    def pack(self, dest=None):
        """
        Produce a relocatable tarball of the current conda prefix.

        Uses ``conda-pack`` under the hood: binaries, shebangs and scripts get
        rewritten to placeholder paths so the tarball can be extracted anywhere
        and re-activated with ``conda-unpack``.

        :param dest: Output tarball path. Defaults to
                     ``{generators_folder}/condaenv.tar.gz``.
        :return: Absolute path to the generated tarball.
        """
        if not os.path.isdir(self._env_dir):
            raise ConanException(
                f"CondaEnv.pack(): environment prefix {self._env_dir} does not exist. "
                f"Call install() first.")

        if dest is None:
            generators_folder = (self._conanfile.generators_folder
                                 or self._conanfile.build_folder or os.getcwd())
            dest = os.path.join(generators_folder, "condaenv.tar.gz")
        dest = os.path.abspath(dest)
        os.makedirs(os.path.dirname(dest), exist_ok=True)

        conda_pack = self._resolve_conda_pack()
        cmd = [
            f'"{conda_pack}"',
            "--prefix", f'"{self._env_dir}"',
            "--output", f'"{dest}"',
            "--format", "tar.gz",
            "--force",
        ]
        self._conanfile.run(" ".join(cmd))
        return dest

    def unpack_archive(self, archive, prefix):
        """
        Extract a ``conda-pack``-generated tarball into ``prefix`` and finalize
        path rewrites by invoking the bundled ``bin/conda-unpack`` script.

        Intended for use inside ``finalize()``:

        .. code-block:: python

            def finalize(self):
                src = os.path.join(self.folders.immutable_package_folder,
                                   "condaenv.tar.gz")
                CondaEnv(self).unpack_archive(src, self.package_folder)

        :param archive: Path to the tarball produced by :meth:`pack`.
        :param prefix: Destination directory where the env will live.
        """
        if not os.path.isfile(archive):
            raise ConanException(f"CondaEnv.unpack_archive(): archive '{archive}' "
                                 f"does not exist")
        prefix = os.path.abspath(prefix)
        os.makedirs(prefix, exist_ok=True)

        # Lazy import to keep top-level deps minimal
        from conan.tools.files import unzip
        unzip(self._conanfile, archive, destination=prefix)

        is_windows = os.name == "nt"
        unpack = (os.path.join(prefix, "Scripts", "conda-unpack.exe") if is_windows
                  else os.path.join(prefix, "bin", "conda-unpack"))
        if not os.path.isfile(unpack):
            raise ConanException(
                f"CondaEnv.unpack_archive(): conda-unpack not found at {unpack}. "
                f"Was the archive produced by conda-pack?")
        if not is_windows:
            st = os.stat(unpack)
            os.chmod(unpack, st.st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
        self._conanfile.run(f'"{unpack}"')
        return prefix

    def environment(self):
        """
        Build a :class:`conan.tools.env.Environment` populated with the variables
        needed to consume the conda prefix from CMake and at runtime.
        """
        env = Environment()
        prefix = self._env_dir
        is_windows = str(self._conanfile.settings.get_safe("os")) == "Windows"

        if is_windows:
            env.prepend_path("PATH", os.path.join(prefix, "Library", "bin"))
            env.prepend_path("PATH", os.path.join(prefix, "Scripts"))
            env.prepend_path("PATH", prefix)
            env.prepend_path("CMAKE_PREFIX_PATH", os.path.join(prefix, "Library"))
            env.prepend_path("CMAKE_PREFIX_PATH", prefix)
            env.prepend_path("PKG_CONFIG_PATH", os.path.join(prefix, "Library", "lib",
                                                             "pkgconfig"))
        else:
            env.prepend_path("PATH", os.path.join(prefix, "bin"))
            env.prepend_path("CMAKE_PREFIX_PATH", prefix)
            env.prepend_path("PKG_CONFIG_PATH", os.path.join(prefix, "lib", "pkgconfig"))
            if str(self._conanfile.settings.get_safe("os")) == "Macos":
                env.prepend_path("DYLD_LIBRARY_PATH", os.path.join(prefix, "lib"))
            else:
                env.prepend_path("LD_LIBRARY_PATH", os.path.join(prefix, "lib"))

        env.define_path("CONDA_PREFIX", prefix)

        if self._has_ros_packages():
            env.prepend_path("AMENT_PREFIX_PATH", prefix)

        return env

    def _has_ros_packages(self):
        for p in self._installed:
            # Strip version/build specs
            name = p.split("=", 1)[0].split("<", 1)[0].split(">", 1)[0].strip()
            if name.startswith("ros-") or name.startswith("ament-"):
                return True
        return False

    def generate(self):
        """
        Generate the environment script (``conancondaenv.sh`` / ``.bat``) and integrate
        the conda prefix with ``VirtualBuildEnv``.
        """
        env = self.environment()
        env.vars(self._conanfile).save_script("conancondaenv")

        # Also compose with VirtualBuildEnv so tools launched during build inherit the prefix
        try:
            from conan.tools.env import VirtualBuildEnv
            vbe = VirtualBuildEnv(self._conanfile)
            build_env = vbe.environment()
            build_env.compose_env(env)
            vbe.generate()
        except Exception as e:
            ConanOutput().warning(f"CondaEnv: could not integrate with VirtualBuildEnv: {e}")
