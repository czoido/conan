import os
import sys
from io import StringIO

import conans
from conans import __version__ as client_version
from conans.client.cache.cache import ClientCache
from conans.client.graph.graph_binaries import GraphBinariesAnalyzer
from conans.client.graph.graph_manager import GraphManager
from conans.client.graph.proxy import ConanProxy
from conans.client.graph.python_requires import ConanPythonRequire, PyRequireLoader
from conans.client.graph.range_resolver import RangeResolver
from conans.client.hook_manager import HookManager
from conans.client.loader import ConanFileLoader
from conans.client.migrations import ClientMigrator
from conans.client.output import ConanOutput, colorama_initialize
from conans.client.remote_manager import RemoteManager
from conans.client.rest.auth_manager import ConanApiAuthManager
from conans.client.rest.conan_requester import ConanRequester
from conans.client.rest.rest_client import RestApiClientFactory
from conans.client.runner import ConanRunner
from conans.client.store.localdb import LocalDB
from conans.client.tools.env import environment_append
from conans.client.userio import UserIO
from conans.model.version import Version
from conans.paths import get_conan_user_home
from conans.tools import set_global_instances
from conans.util.conan_v2_mode import CONAN_V2_MODE_ENVVAR
from conans.util.env_reader import get_env
from conans.util.files import exception_message_safe
from conans.util.log import configure_logger
from conans.cli.conan_logging import log_command, log_exception


def api_method(f):
    def wrapper(api, *args, **kwargs):
        quiet = kwargs.pop("quiet", False)
        try:  # getcwd can fail if Conan runs on an unexisting folder
            old_curdir = os.getcwd()
        except EnvironmentError:
            old_curdir = None
        old_output = api.user_io.out
        quiet_output = ConanOutput(StringIO(), color=api.color) if quiet else None
        try:
            api.create_app(quiet_output=quiet_output)
            log_command(f.__name__, kwargs)
            with environment_append(api.app.cache.config.env_vars):
                return f(api, *args, **kwargs)
        except Exception as exc:
            if quiet_output:
                old_output.write(quiet_output._stream.getvalue())
                old_output.flush()
            msg = exception_message_safe(exc)
            try:
                log_exception(exc, msg)
            except BaseException:
                pass
            raise
        finally:
            if old_curdir:
                os.chdir(old_curdir)

    return wrapper


class ConanApp(object):
    def __init__(self, cache_folder, user_io, http_requester=None, runner=None, quiet_output=None):
        # User IO, interaction and logging
        self.user_io = user_io
        self.out = self.user_io.out
        if quiet_output:
            self.user_io.out = quiet_output
            self.out = quiet_output

        self.cache_folder = cache_folder
        self.cache = ClientCache(self.cache_folder, self.out)
        self.config = self.cache.config
        if self.config.non_interactive or quiet_output:
            self.user_io.disable_input()

        # Adjust CONAN_LOGGING_LEVEL with the env readed
        conans.util.log.logger = configure_logger(self.config.logging_level,
                                                  self.config.logging_file)
        conans.util.log.logger.debug("INIT: Using config '%s'" % self.cache.conan_conf_path)

        self.hook_manager = HookManager(self.cache.hooks_path, self.config.hooks, self.out)
        # Wraps an http_requester to inject proxies, certs, etc
        self.requester = ConanRequester(self.config, http_requester)
        # To handle remote connections
        artifacts_properties = self.cache.read_artifacts_properties()
        rest_client_factory = RestApiClientFactory(self.out, self.requester, self.config,
                                                   artifacts_properties=artifacts_properties)
        # To store user and token
        localdb = LocalDB.create(self.cache.localdb)
        # Wraps RestApiClient to add authentication support (same interface)
        auth_manager = ConanApiAuthManager(rest_client_factory, self.user_io, localdb)
        # Handle remote connections
        self.remote_manager = RemoteManager(self.cache, auth_manager, self.out, self.hook_manager)

        # Adjust global tool variables
        set_global_instances(self.out, self.requester, self.config)

        self.runner = runner or ConanRunner(self.config.print_commands_to_output,
                                            self.config.generate_run_log_file,
                                            self.config.log_run_to_output,
                                            self.out)

        self.proxy = ConanProxy(self.cache, self.out, self.remote_manager)
        self.range_resolver = RangeResolver(self.cache, self.remote_manager)
        self.python_requires = ConanPythonRequire(self.proxy, self.range_resolver)
        self.pyreq_loader = PyRequireLoader(self.proxy, self.range_resolver)
        self.loader = ConanFileLoader(self.runner, self.out, self.python_requires, self.pyreq_loader)

        self.binaries_analyzer = GraphBinariesAnalyzer(self.cache, self.out, self.remote_manager)
        self.graph_manager = GraphManager(self.out, self.cache, self.remote_manager, self.loader,
                                          self.proxy, self.range_resolver, self.binaries_analyzer)


class ConanAPIV2(object):
    def __init__(self, cache_folder=None, output=None, user_io=None, http_requester=None,
                 runner=None):
        self.color = colorama_initialize()
        self.out = output or ConanOutput(sys.stdout, sys.stderr, self.color)
        self.user_io = user_io or UserIO(out=self.out)
        self.cache_folder = cache_folder or os.path.join(get_conan_user_home(), ".conan")
        self.http_requester = http_requester
        self.runner = runner
        self.app = None  # Api calls will create a new one every call
        # Migration system
        migrator = ClientMigrator(self.cache_folder, Version(client_version), self.out)
        migrator.migrate()
        if not get_env(CONAN_V2_MODE_ENVVAR, False):
            # FIXME Remove in Conan 2.0
            sys.path.append(os.path.join(self.cache_folder, "python"))

    def create_app(self, quiet_output=None):
        self.app = ConanApp(self.cache_folder, self.user_io, self.http_requester,
                            self.runner, quiet_output=quiet_output)

    @api_method
    def user_list(self, remote_name=None):
        if not remote_name or "*" in remote_name:
            info = {"results": {"remote1": {"user": "someuser1"},
                                "remote2": {"user": "someuser2"},
                                "remote3": {"user": "someuser3"},
                                "remote4": {"user": "someuser4"}}}
        else:
            info = {"results": {"{}".format(remote_name): {"user": "someuser1"}}}
        return info

    @api_method
    def user_add(self, remote_name, user_name, user_password, force_add=False):
        return {}

    @api_method
    def user_remove(self, remote_name):
        return {}

    @api_method
    def user_update(self, user_name, user_pasword):
        return {}


Conan = ConanAPIV2
