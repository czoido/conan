import os
from contextlib import contextmanager

from conan.cache.conan_reference import ConanReference
from conans.errors import ConanException
from conans.model.manifest import FileTreeManifest
from conans.paths import BUILD_FOLDER, PACKAGES_FOLDER, SYSTEM_REQS_FOLDER, SYSTEM_REQS, DATA_YML, \
    rm_conandir, EXPORT_SRC_FOLDER, SRC_FOLDER
from conans.paths import CONANFILE, SCM_SRC_FOLDER
from conans.util.files import rmdir
from conans.util.files import set_dirty, clean_dirty, is_dirty


class LayoutBase:
    def __init__(self, ref, base_folder):
        self._ref = ref
        self._base_folder = base_folder

    @property
    def base_folder(self):
        return self._base_folder

    def remove(self):
        try:
            rmdir(self.base_folder)
        except OSError as e:
            raise ConanException(f"Couldn't remove folder {self.base_folder}: {str(e)}")


class RecipeLayout(LayoutBase):
    # TODO: cache2.0 fix this in the future when we only have to deal
    #  with ConanReference and not ConanFileReference and PackageReference
    @property
    def reference(self):
        return self._ref.as_conanfile_reference()

    @reference.setter
    def reference(self, ref: ConanReference):
        self._ref = ref

    def export(self):
        return os.path.join(self.base_folder, 'export')

    def export_sources(self):
        return os.path.join(self.base_folder, 'export_sources')

    def download_export(self):
        return os.path.join(self.base_folder, "dl", "export")

    def source(self):
        return os.path.join(self.base_folder, SRC_FOLDER)

    def conanfile(self):
        return os.path.join(self.export(), CONANFILE)

    def scm_sources(self):
        return os.path.join(self.base_folder, SCM_SRC_FOLDER)

    def conandata(self):
        return os.path.join(self.export(), DATA_YML)

    def recipe_manifest(self):
        return FileTreeManifest.load(self.export())

    def sources_remove(self):
        src_folder = self.source()
        try:
            rm_conandir(src_folder)  # This will remove the shortened path too if exists
        except OSError as e:
            raise ConanException("%s\n\nFolder: %s\n"
                                 "Couldn't remove folder, might be busy or open\n"
                                 "Close any app using it, and retry" % (src_folder, str(e)))
        scm_folder = self.scm_sources()
        try:
            rm_conandir(scm_folder)  # This will remove the shortened path too if exists
        except OSError as e:
            raise ConanException("%s\n\nFolder: %s\n"
                                 "Couldn't remove folder, might be busy or open\n"
                                 "Close any app using it, and retry" % (scm_folder, str(e)))

    def export_remove(self):
        export_folder = self.export()
        rmdir(export_folder)
        export_src_folder = os.path.join(self.base_folder, EXPORT_SRC_FOLDER)
        rm_conandir(export_src_folder)
        download_export = self.download_export()
        rmdir(download_export)
        scm_folder = os.path.join(self.base_folder, SCM_SRC_FOLDER)
        rm_conandir(scm_folder)


class PackageLayout(LayoutBase):
    @property
    def reference(self):
        return self._ref.as_package_reference()

    # TODO: cache2.0 fix this in the future
    @reference.setter
    def reference(self, ref: ConanReference):
        self._ref = ref

    def build(self):
        return os.path.join(self.base_folder, BUILD_FOLDER)

    def package(self):
        return os.path.join(self.base_folder, PACKAGES_FOLDER)

    def download_package(self):
        return os.path.join(self.base_folder, "dl", "pkg")

    # TODO: cache2.0 fix this
    def system_reqs(self):
        return os.path.join(self.base_folder, SYSTEM_REQS_FOLDER, SYSTEM_REQS)

    # TODO: cache2.0 fix this
    def system_reqs_package(self):
        return os.path.join(self.base_folder, SYSTEM_REQS_FOLDER,
                            self._ref.pkgid, SYSTEM_REQS)

    def package_manifests(self):
        package_folder = self.package()
        readed_manifest = FileTreeManifest.load(package_folder)
        expected_manifest = FileTreeManifest.create(package_folder)
        return readed_manifest, expected_manifest

    @contextmanager
    def set_dirty_context_manager(self):
        set_dirty(self.package())
        yield
        clean_dirty(self.package())

    # TODO: cache2.0 check this
    def package_is_dirty(self):
        return is_dirty(self.package())

    def build_remove(self):
        try:
            rmdir(self.build())
        except OSError as e:
            raise ConanException(f"Couldn't remove folder {self.build()}: {str(e)}")

    # TODO: cache2.0 locks
    def package_remove(self):
        # Here we could validate and check we own a write lock over this package
        tgz_folder = self.download_package()
        rmdir(tgz_folder)
        try:
            rmdir(self.package())
        except OSError as e:
            raise ConanException("%s\n\nFolder: %s\n"
                                 "Couldn't remove folder, might be busy or open\n"
                                 "Close any app using it, and retry" % (self.package(), str(e)))
        if is_dirty(self.package()):
            clean_dirty(self.package())


class ReferenceLayout:
    def __new__(cls, ref, base_folder):
        if ref.pkgid:
            return PackageLayout(ref, base_folder)
        else:
            return RecipeLayout(ref, base_folder)
