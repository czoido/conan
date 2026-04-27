import os
import shutil
import stat

from conan.errors import ConanException
from conan.internal.paths import get_conan_user_home
from conan.tools.env.environment import Environment


class CondaEnv:
    """
    Helper that creates a local conda environment inside a recipe using micromamba
    as the solver, and exposes the resulting prefix to the rest of the Conan build.

    ``micromamba`` must be installed system-wide and available on ``PATH``.
    ``conda-pack`` is bootstrapped automatically the first time :meth:`pack`
    is called.
    """

    def __init__(self, conanfile, channels=None):
        """
        :param conanfile: The current conanfile ``self``.
        :param channels: List of conda channels in priority order. Defaults to
                         ``["conda-forge"]``.
        """
        self._conanfile = conanfile
        self._channels = list(channels) if channels else ["conda-forge"]

        generators_folder = (conanfile.generators_folder or conanfile.build_folder
                             or os.getcwd())
        self._env_dir = os.path.abspath(os.path.join(generators_folder, "condaenv"))

        self._installed = []
        self._micromamba_checked = False

    @property
    def env_dir(self):
        """Absolute path to the conda environment prefix."""
        return self._env_dir.replace("\\", "/")

    def _micromamba_cache_dir(self):
        return self._conanfile.conf.get(
            "tools.system.condaenv:root_prefix",
            default=os.path.join(get_conan_user_home(), "condaenv"))

    def _base_cmd(self):
        # micromamba needs MAMBA_ROOT_PREFIX to know where to store its package cache
        root_prefix = self._micromamba_cache_dir()
        if os.name == "nt":
            return f'set "MAMBA_ROOT_PREFIX={root_prefix}" && '
        return f'MAMBA_ROOT_PREFIX="{root_prefix}" '

    def _check_micromamba(self):
        if self._micromamba_checked:
            return
        if shutil.which("micromamba") is None:
            raise ConanException(
                "CondaEnv: 'micromamba' not found on PATH. Install it system-wide "
                "(e.g. `brew install micromamba`, or follow "
                "https://mamba.readthedocs.io/en/latest/installation/"
                "micromamba-installation.html).")
        self._micromamba_checked = True

    def _run_micromamba(self, subcommand, packages):
        self._check_micromamba()
        channel_args = []
        for ch in self._channels:
            channel_args.extend(["-c", ch])
        cmd = [
            "micromamba", subcommand,
            "-p", f'"{self._env_dir}"',
            "--yes", "--no-rc", "--no-env",
            "--strict-channel-priority",
        ] + channel_args + [f'"{p}"' for p in packages]
        self._conanfile.run(self._base_cmd() + " ".join(cmd))

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

    def _ensure_conda_pack(self):
        """Bootstrap conda-pack into a shared tools env under the root prefix."""
        tool_env = os.path.join(self._micromamba_cache_dir(), "tools", "conda-pack")
        exe = (os.path.join(tool_env, "Scripts", "conda-pack.exe") if os.name == "nt"
               else os.path.join(tool_env, "bin", "conda-pack"))
        if not os.path.isfile(exe):
            self._check_micromamba()
            cmd = (f'micromamba create -p "{tool_env}" --yes --no-rc --no-env '
                   f'--strict-channel-priority -c conda-forge "conda-pack"')
            self._conanfile.run(self._base_cmd() + cmd)
        return exe

    def pack(self, dest=None):
        """
        Produce a relocatable tarball of the current conda prefix using ``conda-pack``.
        Binaries, shebangs and scripts get rewritten to placeholder paths so the
        tarball can be extracted anywhere and re-activated with ``conda-unpack``.

        ``conda-pack`` is bootstrapped automatically into a shared tools env under the
        root prefix the first time :meth:`pack` is called.

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

        conda_pack = self._ensure_conda_pack()
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

        from conan.tools.env import VirtualBuildEnv
        vbe = VirtualBuildEnv(self._conanfile)
        build_env = vbe.environment()
        build_env.compose_env(env)
        vbe.generate()
