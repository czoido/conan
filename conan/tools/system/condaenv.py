import os
import shutil
import stat

from conan.errors import ConanException
from conan.internal.paths import get_conan_user_home
from conan.tools.env import Environment, VirtualBuildEnv
from conan.tools.files import unzip


class CondaEnv:
    """
    Creates a local conda environment in a recipe using ``micromamba``, and exposes
    the resulting prefix to the Conan build. Requires ``micromamba`` on ``PATH``.
    """

    def __init__(self, conanfile, channels=None):
        """:param channels: Conda channels in priority order. Defaults to ``["conda-forge"]``."""
        self._conanfile = conanfile
        self._channels = list(channels) if channels else ["conda-forge"]

        self._env_dir = os.path.join(conanfile.generators_folder, "condaenv")

        self._micromamba = None

    @property
    def env_dir(self):
        """Absolute path to the conda environment prefix."""
        return self._env_dir.replace("\\", "/")

    def _resolve_micromamba(self):
        if self._micromamba is not None:
            return self._micromamba
        conf_path = self._conanfile.conf.get("tools.system.condaenv:micromamba_path")
        if conf_path:
            if not os.path.isfile(conf_path):
                raise ConanException(
                    f"CondaEnv: 'tools.system.condaenv:micromamba_path' points to "
                    f"'{conf_path}' which does not exist")
            self._micromamba = conf_path
        elif shutil.which("micromamba"):
            self._micromamba = "micromamba"
        else:
            raise ConanException(
                "CondaEnv: 'micromamba' not found. Install it system-wide or point to "
                "an existing installation via 'tools.system.condaenv:micromamba_path'.")
        return self._micromamba

    def _run_micromamba(self, subcommand, packages):
        micromamba = self._resolve_micromamba()
        channel_args = []
        for ch in self._channels:
            channel_args.extend(["-c", ch])
        cmd = [
            f'"{micromamba}"', subcommand,
            "-p", f'"{self._env_dir}"',
            "--yes", "--no-rc", "--no-env",
            "--strict-channel-priority",
        ] + channel_args + [f'"{p}"' for p in packages]
        self._conanfile.run(" ".join(cmd))

    def install(self, *packages):
        """Install conda packages into the local environment. May be called repeatedly."""
        if not packages:
            return
        subcommand = "create" if not os.path.isdir(self._env_dir) else "install"
        self._run_micromamba(subcommand, packages)

    def _ensure_conda_pack(self):
        """Bootstrap conda-pack into a shared tools env under the Conan home."""
        tool_env = os.path.join(get_conan_user_home(), "condaenv", "tools", "conda-pack")
        if not os.path.isdir(os.path.join(tool_env, "conda-meta")):
            micromamba = self._resolve_micromamba()
            self._conanfile.run(
                f'"{micromamba}" create -p "{tool_env}" --yes --no-rc --no-env '
                f'--strict-channel-priority -c conda-forge "conda-pack"')
        return tool_env

    _ARCHIVE_NAME = "condaenv.tar.gz"

    def pack(self):
        """
        Produce a relocatable tarball at ``{package_folder}/condaenv.tar.gz`` via
        ``conda-pack``. Bootstraps ``conda-pack`` on first use. Call from ``package()``.
        """
        if not os.path.isdir(self._env_dir):
            raise ConanException(
                f"CondaEnv.pack(): environment prefix {self._env_dir} does not exist. "
                f"Call install() first.")

        dest = os.path.join(self._conanfile.package_folder, self._ARCHIVE_NAME)
        tool_env = self._ensure_conda_pack()
        micromamba = self._resolve_micromamba()
        self._conanfile.run(
            f'"{micromamba}" run -p "{tool_env}" conda-pack '
            f'--prefix "{self._env_dir}" --output "{dest}" '
            f'--format tar.gz --force')
        return dest

    def unpack(self):
        """
        Extract the tarball from ``{immutable_package_folder}/condaenv.tar.gz`` into
        ``{package_folder}`` and run ``conda-unpack``. Call from ``finalize()``.
        """
        archive = os.path.join(self._conanfile.folders.immutable_package_folder,
                               self._ARCHIVE_NAME)
        if not os.path.isfile(archive):
            raise ConanException(f"CondaEnv.unpack(): archive '{archive}' "
                                 f"does not exist")
        prefix = self._conanfile.package_folder
        os.makedirs(prefix, exist_ok=True)

        unzip(self._conanfile, archive, destination=prefix)

        is_windows = os.name == "nt"
        unpack = (os.path.join(prefix, "Scripts", "conda-unpack.exe") if is_windows
                  else os.path.join(prefix, "bin", "conda-unpack"))
        if not os.path.isfile(unpack):
            raise ConanException(
                f"CondaEnv.unpack(): conda-unpack not found at {unpack}. "
                f"Was the archive produced by conda-pack?")
        if not is_windows:
            st = os.stat(unpack)
            os.chmod(unpack, st.st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
        self._conanfile.run(f'"{unpack}"')
        return prefix

    def environment(self):
        """:class:`Environment` with PATH, CMAKE_PREFIX_PATH and runtime libs for the conda prefix."""
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
        return env

    def generate(self):
        """Save ``conancondaenv`` script and compose the env into ``VirtualBuildEnv``."""
        env = self.environment()
        env.vars(self._conanfile).save_script("conancondaenv")

        vbe = VirtualBuildEnv(self._conanfile)
        build_env = vbe.environment()
        build_env.compose_env(env)
        vbe.generate()
