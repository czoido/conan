import os
import sys
import time

from tqdm import tqdm

from conans import __version__ as client_version
from conans.cli.output import ConanOutput
from conans.client.cache.cache import ClientCache
from conans.client.migrations import ClientMigrator
from conans.client.tools.env import environment_append
from conans.client.userio import UserIO
from conans.errors import NoRemoteAvailable, ConanException
from conans.model.version import Version
from conans.paths import get_conan_user_home
from conans.util.conan_v2_mode import CONAN_V2_MODE_ENVVAR
from conans.util.env_reader import get_env
from conans.util.files import exception_message_safe


def api_method(f):
    def wrapper(api, *args, **kwargs):
        try:  # getcwd can fail if Conan runs on an unexisting folder
            old_curdir = os.getcwd()
        except EnvironmentError:
            old_curdir = None
        try:
            # TODO: Removing ConanApp creation, should we make it different for 2.0?
            # Also removing the logger call, maybe conan_command can handle it
            cache = ClientCache(api.cache_folder, api.out)
            with environment_append(cache.config.env_vars):
                return f(api, *args, **kwargs)
        except Exception as exc:
            msg = exception_message_safe(exc)
            try:
                api.out.error("{} ({})".format(str(exc.__class__.__name__), msg))
            except BaseException:
                pass
            raise
        finally:
            if old_curdir:
                os.chdir(old_curdir)

    return wrapper


class ConanAPIV2(object):
    def __init__(self, cache_folder=None, output=None, user_io=None, http_requester=None,
                 runner=None):
        self.out = output or ConanOutput()
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

    @api_method
    def user_list(self, remote_name=None):
        self.out.scope = "MyScope"
        self.out.debug("debug message")
        self.out.info("info message")
        self.out.warning("warning message")
        self.out.scope = ""
        self.out.error("error message")
        self.out.critical("critical message")
        for _ in tqdm(range(10)):
            time.sleep(.08)
            self.out.info("doing something")

        if not remote_name or "*" in remote_name:
            info = {"remote1": {"user": "someuser1"},
                    "remote2": {"user": "someuser2"},
                    "remote3": {"user": "someuser3"},
                    "remote4": {"user": "someuser4"}}
        else:
            info = {"{}".format(remote_name): {"user": "someuser1"}}
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

    @api_method
    def search_recipes(self, query, remote_patterns=None, local_cache=False):
        remote = None
        if remote_patterns is not None and len(remote_patterns) > 0:
            remote = remote_patterns[0].replace("*", "remote")

        if remote and "bad" in remote:
            raise NoRemoteAvailable("Remote '%s' not found in remotes" % remote)

        search_results = [{"remote": remote,
                           "items": [{"recipe": {"id": "app/1.0"}},
                                     {"recipe": {"id": "liba/1.0"}}]}]

        return search_results

    @api_method
    def create(self, path, name, version, user, channel):
        name = name or "pkg"
        version = version or "1.0"
        create_results = {"full_reference": "{}/{}@{}/{}#cfeb566fb51ca21a2f549c969c907b53:"
                                            "587de5488b43bc9cebd0703c6c0f8c74#"
                                            "cfeb566fb51ca21a2f549c969c907b53".format(name, version,
                                                                                      user, channel),
                          "name":  name,
                          "version":  version,
                          "user":  user,
                          "channel":  channel,
                          "package_id":  "587de5488b43bc9cebd0703c6c0f8c74",
                          "recipe_revision":  "cfeb566fb51ca21a2f549c969c907b53",
                          "package_revision":  "cfeb566fb51ca21a2f549c969c907b53"}
        return create_results

    @api_method
    def upload(self, pattern_or_reference, remote, query, all):
        rev = "587de5488b43bc9cebd0703c6c0f8c74:cfeb566fb51ca21a2f549c969c907b53#" \
              "cfeb566fb51ca21a2f549c969c907b53"
        if "*" in pattern_or_reference:
            upload_results = {"uploaded_references": ["pkg/1.0@user/channel#{}".format(rev),
                                                      "pkg/2.0@user/channel#{}".format(rev),
                                                      "pkg/3.0@user/channel#{}".format(rev),
                                                      "pkg/4.0@user/channel#{}".format(rev)]}
        else:
            upload_results = {"uploaded_references": [pattern_or_reference]}

        return upload_results


Conan = ConanAPIV2
