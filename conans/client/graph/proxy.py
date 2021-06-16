import os

from requests.exceptions import RequestException

from conan.cache.conan_reference import ConanReference
from conans.client.graph.graph import (RECIPE_DOWNLOADED, RECIPE_INCACHE, RECIPE_NEWER,
                                       RECIPE_NOT_IN_REMOTE, RECIPE_NO_REMOTE, RECIPE_UPDATEABLE,
                                       RECIPE_UPDATED, RECIPE_EDITABLE)
from conans.client.output import ScopedOutput
from conans.client.recorder.action_recorder import INSTALL_ERROR_MISSING, INSTALL_ERROR_NETWORK
from conans.client.remover import DiskRemover
from conans.errors import ConanException, NotFoundException, RecipeNotFoundException
from conans.model.ref import ConanFileReference
from conans.paths.package_layouts.package_editable_layout import PackageEditableLayout
from conans.util.tracer import log_recipe_got_from_local_cache


class ConanProxy(object):
    def __init__(self, cache, output, remote_manager):
        # collaborators
        self._cache = cache
        self._out = output
        self._remote_manager = remote_manager

    def get_recipe(self, ref, check_updates, update, remotes):

        # TODO: cache2.0 check editables
        # if isinstance(layout, PackageEditableLayout):
        #     conanfile_path = layout.conanfile()
        #     status = RECIPE_EDITABLE
        #     # TODO: log_recipe_got_from_editable(reference)
        #     # TODO: recorder.recipe_fetched_as_editable(reference)
        #     return conanfile_path, status, None, ref

        # TODO: cache2.0 Check with new locks
        # with layout.conanfile_write_lock(self._out):
        result = self._get_recipe(ref, check_updates, update, remotes)
        conanfile_path, status, remote, new_ref = result

        if status not in (RECIPE_DOWNLOADED, RECIPE_UPDATED):
            log_recipe_got_from_local_cache(new_ref)

        return conanfile_path, status, remote, new_ref

    def _get_recipe(self, reference, check_updates, update, remotes):
        output = ScopedOutput(str(reference), self._out)

        # check if it there's any revision of this recipe in the local cache
        ref = self._cache.get_latest_rrev(reference)

        # NOT in disk, must be retrieved from remotes
        if not ref:
            remote, new_ref = self._download_recipe(reference, output, remotes, remotes.selected)
            recipe_layout = self._cache.ref_layout(new_ref)
            status = RECIPE_DOWNLOADED
            conanfile_path = recipe_layout.conanfile()
            return conanfile_path, status, remote, new_ref

        # TODO: cache2.0: store the remote in the db? In 1.X we took the remote from the metadata
        # TODO: cache2.0: check with new --update flows
        recipe_layout = self._cache.ref_layout(ref)
        conanfile_path = recipe_layout.conanfile()
        # TODO: cache2.0: check if we want to get the remote through the layout
        cur_remote = self._cache.get_remote(recipe_layout.reference)
        cur_remote = remotes[cur_remote] if cur_remote else None
        selected_remote = remotes.selected or cur_remote

        check_updates = check_updates or update

        # TODO: cache2.0 check this for new update flows
        # requested_different_revision = (ref.revision is not None) and cur_revision != ref.revision
        # if requested_different_revision:
        #     if check_updates:
        #         remote, new_ref = self._download_recipe(layout, ref, output, remotes,
        #                                                 selected_remote)
        #         status = RECIPE_DOWNLOADED
        #         return conanfile_path, status, remote, new_ref
        #     else:
        #         raise NotFoundException("The '%s' revision recipe in the local cache doesn't "
        #                                 "match the requested '%s'."
        #                                 " Use '--update' to check in the remote."
        #                                 % (cur_revision, repr(ref)))

        if not check_updates:
            status = RECIPE_INCACHE
            return conanfile_path, status, cur_remote, ref

        # Checking updates in the server
        if not selected_remote:
            status = RECIPE_NO_REMOTE
            return conanfile_path, status, None, ref

        try:  # get_recipe_manifest can fail, not in server
            upstream_manifest, ref = self._remote_manager.get_recipe_manifest(ref, selected_remote)
        except NotFoundException:
            status = RECIPE_NOT_IN_REMOTE
            return conanfile_path, status, selected_remote, ref

        read_manifest = recipe_layout.recipe_manifest()
        # TODO: cache2.0 check this for 2.0
        if upstream_manifest != read_manifest:
            if upstream_manifest.time > read_manifest.time:
                if update:
                    DiskRemover().remove_recipe(recipe_layout, output=output)
                    output.info("Retrieving from remote '%s'..." % selected_remote.name)
                    self._download_recipe(recipe_layout, ref, output, remotes, selected_remote)
                    status = RECIPE_UPDATED
                    return conanfile_path, status, selected_remote, ref
                else:
                    status = RECIPE_UPDATEABLE
            else:
                status = RECIPE_NEWER
        else:
            status = RECIPE_INCACHE

        return conanfile_path, status, selected_remote, ref

    def _download_recipe(self, ref, output, remotes, remote):

        def _retrieve_from_remote(the_remote):
            output.info("Trying with '%s'..." % the_remote.name)
            # If incomplete, resolve the latest in server
            _ref = self._remote_manager.get_recipe(ref, the_remote)
            output.info("Downloaded recipe revision %s" % _ref.revision)
            return _ref

        if remote:
            output.info("Retrieving from server '%s' " % remote.name)
        else:
            latest_rrev = self._cache.get_latest_rrev(ref)
            if latest_rrev:
                remote_name = self._cache.get_remote(latest_rrev)
                if remote_name:
                    remote = remotes[remote_name]
                    output.info("Retrieving from predefined remote '%s'" % remote.name)

        if remote:
            try:
                new_ref = _retrieve_from_remote(remote)
                return remote, new_ref
            except NotFoundException:
                msg = "%s was not found in remote '%s'" % (str(ref), remote.name)
                raise NotFoundException(msg)
            except RequestException as exc:
                raise exc

        output.info("Not found in local cache, looking in remotes...")
        remotes = remotes.values()
        if not remotes:
            raise ConanException("No remote defined")
        for remote in remotes:
            try:
                new_ref = _retrieve_from_remote(remote)
                return remote, new_ref
            # If not found continue with the next, else raise
            except NotFoundException:
                pass
        else:
            msg = "Unable to find '%s' in remotes" % ref.full_str()
            raise NotFoundException(msg)
