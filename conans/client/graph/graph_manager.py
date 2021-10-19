
import os

from conans.cli.output import ConanOutput
from conans.client.conanfile.configure import run_configure_method
from conans.client.graph.graph import Node, CONTEXT_HOST
from conans.client.graph.graph_binaries import RECIPE_CONSUMER, RECIPE_VIRTUAL
from conans.client.graph.graph_builder import DepsGraphBuilder
from conans.client.profile_loader import profile_from_args
from conans.model.ref import ConanFileReference


class GraphManager(object):
    def __init__(self, cache, loader, proxy, resolver, binary_analyzer):
        self._proxy = proxy
        self._output = ConanOutput()
        self._resolver = resolver
        self._cache = cache
        self._loader = loader
        self._binary_analyzer = binary_analyzer

    def load_consumer_conanfile(self, conanfile_path):
        """loads a conanfile for local flow: source
        """
        # This is very dirty, should be removed for Conan 2.0 (source() method only)
        # FIXME: Make "conan source" build the whole graph. Do it in another PR
        profile_host = profile_from_args(None, None, None, None, None, os.getcwd(), self._cache)
        profile_host.process_settings(self._cache)

        name, version, user, channel = None, None, None, None
        if conanfile_path.endswith(".py"):
            lock_python_requires = None
            # The global.conf is necessary for download_cache definition
            profile_host.conf.rebase_conf_definition(self._cache.new_config)
            conanfile = self._loader.load_consumer(conanfile_path,
                                                   profile_host=profile_host,
                                                   name=name, version=version,
                                                   user=user, channel=channel,
                                                   lock_python_requires=lock_python_requires)

            run_configure_method(conanfile, down_options=None, down_ref=None, ref=None)
        else:
            conanfile = self._loader.load_conanfile_txt(conanfile_path, profile_host=profile_host)

        return conanfile

    def load_graph(self, reference, create_reference, profile_host, profile_build, graph_lock,
                   root_ref, build_mode, check_updates, update,
                   remotes, apply_build_requires=True, lockfile_node_id=None,
                   is_build_require=False, require_overrides=None):
        """ main entry point to compute a full dependency graph
        """
        assert profile_host is not None
        assert profile_build is not None

        root_node = self._load_root_node(reference, create_reference, profile_host, graph_lock,
                                         root_ref, lockfile_node_id, is_build_require,
                                         require_overrides)
        profile_host_build_requires = profile_host.build_requires
        builder = DepsGraphBuilder(self._proxy, self._loader, self._resolver)
        deps_graph = builder.load_graph(root_node, check_updates, update, remotes, profile_host,
                                        profile_build, graph_lock)
        version_ranges_output = self._resolver.output
        if version_ranges_output:
            self._output.success("Version ranges solved")
            for msg in version_ranges_output:
                self._output.info("    %s" % msg)
            self._output.writeln("")
            self._resolver.clear_output()

        # TODO: Move binary_analyzer elsewhere
        if not deps_graph.error:
            self._binary_analyzer.evaluate_graph(deps_graph, build_mode, update, remotes)

        return deps_graph

    def _load_root_node(self, reference, create_reference, profile_host, graph_lock, root_ref,
                        lockfile_node_id, is_build_require, require_overrides):
        """ creates the first, root node of the graph, loading or creating a conanfile
        and initializing it (settings, options) as necessary. Also locking with lockfile
        information
        """
        profile_host.dev_reference = create_reference  # Make sure the created one has develop=True

        # create (without test_package), install|info|graph|export-pkg <ref>
        if isinstance(reference, ConanFileReference):
            return self._load_root_direct_reference(reference, graph_lock, profile_host,
                                                    lockfile_node_id, is_build_require,
                                                    require_overrides)

        path = reference  # The reference must be pointing to a user space conanfile
        if create_reference:  # Test_package -> tested reference
            return self._load_root_test_package(path, create_reference, graph_lock, profile_host,
                                                require_overrides)

        # It is a path to conanfile.py or conanfile.txt
        root_node = self._load_root_consumer(path, graph_lock, profile_host, root_ref,
                                             require_overrides)
        return root_node

    def _load_root_consumer(self, path, graph_lock, profile, ref, require_overrides):
        """ load a CONSUMER node from a user space conanfile.py or conanfile.txt
        install|info|create|graph <path>
        :path full path to a conanfile
        :graph_lock: might be None, information of lockfiles
        :profile: data to inject to the consumer node: settings, options
        :ref: previous reference of a previous command. Can be used for finding itself in
              the lockfile, or to initialize
        """
        if path.endswith(".py"):
            lock_python_requires = None
            if graph_lock:
                if ref.name is None:
                    # If the graph_info information is not there, better get what we can from
                    # the conanfile
                    # Using load_named() to run set_name() set_version() and get them
                    # so it can be found by name in the lockfile
                    conanfile = self._loader.load_named(path, None, None, None, None)
                    ref = ConanFileReference(ref.name or conanfile.name,
                                             ref.version or conanfile.version,
                                             ref.user, ref.channel, validate=False)
                node_id = graph_lock.get_consumer(ref)
                lock_python_requires = graph_lock.python_requires(node_id)

            conanfile = self._loader.load_consumer(path, profile,
                                                   name=ref.name,
                                                   version=ref.version,
                                                   user=ref.user,
                                                   channel=ref.channel,
                                                   lock_python_requires=lock_python_requires,
                                                   require_overrides=require_overrides)

            ref = ConanFileReference(conanfile.name, conanfile.version,
                                     ref.user, ref.channel, validate=False)
            root_node = Node(ref, conanfile, context=CONTEXT_HOST, recipe=RECIPE_CONSUMER, path=path)
        else:
            conanfile = self._loader.load_conanfile_txt(path, profile, ref=ref)
            root_node = Node(None, conanfile, context=CONTEXT_HOST, recipe=RECIPE_CONSUMER,
                             path=path)

        if graph_lock:  # Find the Node ID in the lock of current root
            node_id = graph_lock.get_consumer(root_node.ref)
            root_node.id = node_id

        return root_node

    def _load_root_direct_reference(self, reference, graph_lock, profile, lockfile_node_id,
                                    is_build_require, require_overrides):
        """ When a full reference is provided:
        install|info|graph <ref> or export-pkg .
        :return a VIRTUAL root_node with a conanfile that requires the reference
        """
        conanfile = self._loader.load_virtual([reference], profile,
                                              is_build_require=is_build_require,
                                              require_overrides=require_overrides)
        root_node = Node(ref=None, conanfile=conanfile, context=CONTEXT_HOST, recipe=RECIPE_VIRTUAL)
        # Build_requires cannot be found as early as this, because there is no require yet
        if graph_lock and not is_build_require:  # Find the Node ID in the lock of current root
            graph_lock.find_require_and_lock(reference, conanfile, lockfile_node_id)
        return root_node

    def _load_root_test_package(self, path, create_reference, graph_lock, profile,
                                require_overrides):
        """ when a test_package/conanfile.py is provided, together with the reference that is
        being created and need to be tested
        :return a CONSUMER root_node with a conanfile.py with an injected requires to the
        created reference
        """
        test = str(create_reference)
        # do not try apply lock_python_requires for test_package/conanfile.py consumer
        conanfile = self._loader.load_consumer(path, profile, user=create_reference.user,
                                               channel=create_reference.channel,
                                               require_overrides=require_overrides
                                               )
        conanfile.display_name = "%s (test package)" % str(test)
        conanfile.output.scope = conanfile.display_name

        # Injection of the tested reference
        test_type = getattr(conanfile, "test_type", ("requires", ))
        if not isinstance(test_type, (list, tuple)):
            test_type = (test_type, )
        if "build_requires" in test_type:
            conanfile.requires.build_require(str(create_reference))
        if "requires" in test_type:
            require = False # conanfile.requires.get(create_reference.name)
            if require:
                require.ref = require.range_ref = create_reference
            else:
                conanfile.requires(repr(create_reference))

        ref = ConanFileReference(conanfile.name, conanfile.version,
                                 create_reference.user, create_reference.channel, validate=False)
        root_node = Node(ref, conanfile, recipe=RECIPE_CONSUMER, context=CONTEXT_HOST, path=path)
        if graph_lock:
            graph_lock.find_require_and_lock(create_reference, conanfile)
        return root_node
