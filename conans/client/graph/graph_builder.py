import fnmatch
from collections import deque

from conans.client.conanfile.configure import run_configure_method
from conans.client.graph.graph import DepsGraph, Node, RECIPE_EDITABLE, CONTEXT_HOST, \
    CONTEXT_BUILD, RECIPE_CONSUMER, TransitiveRequirement
from conans.client.graph.graph_error import GraphError
from conans.client.graph.provides import check_graph_provides
from conans.client.graph.range_resolver import range_satisfies
from conans.errors import ConanException
from conans.model.ref import ConanFileReference
from conans.model.requires import Requirement


class DepsGraphBuilder(object):

    def __init__(self, proxy, loader, resolver):
        self._proxy = proxy
        self._loader = loader
        self._resolver = resolver

    def load_graph(self, root_node, check_updates, update, remotes, profile_host, profile_build,
                   graph_lock=None):
        assert profile_host is not None
        assert profile_build is not None
        # print("Loading graph")
        check_updates = check_updates or update
        initial = graph_lock.initial_counter if graph_lock else None
        dep_graph = DepsGraph(initial_node_id=initial)

        # TODO: Why assign here the settings_build and settings_target?
        root_node.conanfile.settings_build = profile_build.processed_settings.copy()
        root_node.conanfile.settings_target = None

        self._prepare_node(root_node, profile_host, profile_build, graph_lock, None, None)
        self._initialize_requires(root_node, dep_graph, check_updates, update, remotes)
        dep_graph.add_node(root_node)

        open_requires = deque((r, root_node) for r in root_node.conanfile.requires.values())
        try:
            while open_requires:
                # Fetch the first waiting to be expanded (depth-first)
                (require, node) = open_requires.popleft()
                if require.override:
                    continue
                new_node = self._expand_require(require, node, dep_graph, check_updates, update,
                                                remotes, profile_host, profile_build, graph_lock)
                if new_node:
                    self._initialize_requires(new_node, dep_graph, check_updates, update, remotes)
                    open_requires.extendleft((r, new_node)
                                             for r in reversed(new_node.conanfile.requires.values()))
            self._remove_overrides(dep_graph)
            check_graph_provides(dep_graph)
        except GraphError as e:
            dep_graph.error = e
        return dep_graph

    def _expand_require(self, require, node, graph, check_updates, update, remotes, profile_host,
                        profile_build, graph_lock, populate_settings_target=True):
        # Handle a requirement of a node. There are 2 possibilities
        #    node -(require)-> new_node (creates a new node in the graph)
        #    node -(require)-> previous (creates a diamond with a previously existing node)

        # TODO: allow bootstrapping, use references instead of names
        # print("  Expanding require ", node, "->", require)
        previous = node.check_downstream_exists(require)
        prev_node = None
        if previous is not None:
            prev_require, prev_node, base_previous = previous
            # print("  Existing previous requirements from ", base_previous, "=>", prev_require)

            if prev_require is None:
                raise GraphError.loop(node, require, prev_node)

            prev_ref = prev_node.ref if prev_node else prev_require.ref
            if prev_require.force or prev_require.override:  # override
                require.ref = prev_ref
            else:
                self._conflicting_version(require, node, prev_require, prev_node,
                                          prev_ref, base_previous)
                # FIXME: THis will fail if prev_node is None
                self._conflicting_options(require, node, prev_node, prev_require, base_previous)

        if prev_node is None:
            # new node, must be added and expanded (node -> new_node)
            new_node = self._create_new_node(node, require, graph, profile_host, profile_build,
                                             graph_lock, update, check_updates, remotes,
                                             populate_settings_target)
            return new_node
        else:
            # print("Closing a loop from ", node, "=>", prev_node)
            require.process_package_type(prev_node)
            graph.add_edge(node, prev_node, require)
            node.propagate_closing_loop(require, prev_node)

    @staticmethod
    def _conflicting_version(require, node,
                             prev_require, prev_node, prev_ref, base_previous):
        version_range = require.version_range
        prev_version_range = prev_require.version_range if prev_node is None else None
        if version_range:
            # TODO: Check user/channel conflicts first
            if prev_version_range is not None:
                pass  # Do nothing, evaluate current as it were a fixed one
            else:
                if range_satisfies(version_range, prev_ref.version):
                    require.ref = prev_ref
                else:
                    raise GraphError.conflict(node, require, prev_node, prev_require, base_previous)

        elif prev_version_range is not None:
            # TODO: CHeck user/channel conflicts first
            if not range_satisfies(prev_version_range, require.ref.version):
                raise GraphError.conflict(node, require, prev_node, prev_require, base_previous)
        else:
            def _conflicting_refs(ref1, ref2):
                if ref1.copy_clear_rev() != ref2.copy_clear_rev():
                    return True
                # Computed node, if is Editable, has revision=None
                # If new_ref.revision is None we cannot assume any conflict, user hasn't specified
                # a revision, so it's ok any previous_ref
                if ref1.revision and ref2.revision and ref1.revision != ref2.revision:
                    return True

            # As we are closing a diamond, there can be conflicts. This will raise if so
            conflict = _conflicting_refs(prev_ref, require.ref)
            if conflict:  # It is possible to get conflict from alias, try to resolve it
                raise GraphError.conflict(node, require, prev_node, prev_require, base_previous)

    @staticmethod
    def _conflicting_options(require, node, prev_node, prev_require, base_previous):
        # Even if the version matches, there still can be a configuration conflict
        upstream_options = node.conanfile.options[require.ref.name]
        for k, v in upstream_options.items():
            prev_option = prev_node.conanfile.options.get_safe(k)
            if prev_option is not None:
                if prev_option != v:
                    raise GraphError.conflict_config(node, require, prev_node, prev_require,
                                                     base_previous, k, prev_option, v)

    @staticmethod
    def _prepare_node(node, profile_host, profile_build, graph_lock, down_ref, down_options):
        if graph_lock:
            graph_lock.pre_lock_node(node)

        # basic node configuration: calling configure() and requirements()
        conanfile, ref = node.conanfile, node.ref

        run_configure_method(conanfile, down_options, down_ref, ref)

        # Apply build_requires from profile, overrriding the declared ones
        profile = profile_host if node.context == CONTEXT_HOST else profile_build
        build_requires = profile.build_requires
        str_ref = str(node.ref)
        for pattern, build_requires in build_requires.items():
            if ((node.recipe == RECIPE_CONSUMER and pattern == "&") or
                (node.recipe != RECIPE_CONSUMER and pattern == "&!") or
                    fnmatch.fnmatch(str_ref, pattern)):
                for build_require in build_requires:  # Do the override
                    if str(build_require) == str(node.ref):  # FIXME: Ugly str comparison
                        continue  # avoid self-loop of build-requires in build context
                    # FIXME: converting back to string?
                    node.conanfile.requires.build_require(str(build_require),
                                                          raise_if_duplicated=False)
        if graph_lock:  # No need to evaluate, they are hardcoded in lockfile
            graph_lock.lock_node(node, node.conanfile.requires.values())

    def _initialize_requires(self, node, graph, check_updates, update, remotes):
        # Introduce the current requires to define overrides
        # This is the first pass over one recip requires
        for require in node.conanfile.requires.values():
            self._resolve_alias(node, require, graph, check_updates, update, remotes)
            node.transitive_deps[require] = TransitiveRequirement(require, None)

    def _resolve_alias(self, node, require, graph, check_updates, update, remotes):
        alias = require.alias
        if alias is None:
            return

        # First try cached
        cached = graph.aliased.get(alias)
        if cached is not None:
            while True:
                new_cached = graph.aliased.get(cached)
                if new_cached is None:
                    break
                else:
                    cached = new_cached
            require.ref = cached
            return

        while alias is not None:
            # if not cached, then resolve
            try:
                result = self._proxy.get_recipe(alias, check_updates, update, remotes)
                conanfile_path, recipe_status, remote, new_ref = result
            except ConanException as e:
                raise GraphError.missing(node, require, str(e))

            dep_conanfile = self._loader.load_basic(conanfile_path)
            try:
                pointed_ref = ConanFileReference.loads(dep_conanfile.alias)
            except Exception as e:
                raise ConanException(f"Alias definition error in {alias}: {str(e)}")

            # UPDATE THE REQUIREMENT!
            require.ref = pointed_ref
            graph.aliased[alias] = pointed_ref  # Caching the alias
            new_req = Requirement(pointed_ref)  # FIXME: Ugly temp creation just for alias check
            alias = new_req.alias

    def _resolve_recipe(self, ref, check_updates,
                        update, remotes, profile, graph_lock):
        result = self._proxy.get_recipe(ref, check_updates, update, remotes)
        conanfile_path, recipe_status, remote, new_ref = result

        # TODO locked_id = requirement.locked_id
        locked_id = None
        lock_py_requires = graph_lock.python_requires(locked_id) if locked_id is not None else None
        dep_conanfile = self._loader.load_conanfile(conanfile_path, profile, ref=ref,
                                                    lock_python_requires=lock_py_requires)
        if recipe_status == RECIPE_EDITABLE:
            dep_conanfile.in_local_cache = False
            dep_conanfile.develop = True

        return new_ref, dep_conanfile, recipe_status, remote, locked_id

    def _create_new_node(self, node, require, graph, profile_host, profile_build, graph_lock,
                         update, check_updates, remotes, populate_settings_target):

        if require.build:
            profile = profile_build
            context = CONTEXT_BUILD
        else:
            profile = profile_host if node.context == CONTEXT_HOST else profile_build
            context = node.context

        try:
            # TODO: If it is locked not resolve range
            #  if not require.locked_id:  # if it is locked, nothing to resolved
            # TODO: This range-resolve might resolve in a given remote or cache
            # Make sure next _resolve_recipe use it
            resolved_ref = self._resolver.resolve(require, str(node.ref), update, remotes)

            # This accounts for alias too
            resolved = self._resolve_recipe(resolved_ref, check_updates, update,
                                            remotes, profile, graph_lock)
        except ConanException as e:
            raise GraphError.missing(node, require, str(e))

        new_ref, dep_conanfile, recipe_status, remote, locked_id = resolved

        # TODO: This should be out of here
        # If there is a context_switch, it is because it is a BR-build
        # Assign the profiles depending on the context
        dep_conanfile.settings_build = profile_build.processed_settings.copy()
        context_switch = (node.context == CONTEXT_HOST and require.build)
        if not context_switch:
            if populate_settings_target:
                dep_conanfile.settings_target = node.conanfile.settings_target
            else:
                dep_conanfile.settings_target = None
        else:
            if node.context == CONTEXT_HOST:
                dep_conanfile.settings_target = profile_host.processed_settings.copy()
            else:
                dep_conanfile.settings_target = profile_build.processed_settings.copy()

        new_node = Node(new_ref, dep_conanfile, context=context)
        new_node.recipe = recipe_status
        new_node.remote = remote

        if locked_id is not None:
            new_node.id = locked_id

        down_options = node.conanfile.options.deps_package_values
        self._prepare_node(new_node, profile_host, profile_build, graph_lock,
                           node.ref, down_options)

        require.process_package_type(new_node)
        graph.add_node(new_node)
        graph.add_edge(node, new_node, require)
        if node.propagate_downstream(require, new_node):
            raise GraphError.runtime(node, new_node)

        return new_node

    @staticmethod
    def _remove_overrides(dep_graph):
        for node in dep_graph.nodes:
            to_remove = [r for r in node.transitive_deps if r.override]
            for r in to_remove:
                node.transitive_deps.pop(r)
