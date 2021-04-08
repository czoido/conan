import unittest

from conans.client.tools import environment_append
from conans.test.utils.tools import TestClient


class CliUserTest(unittest.TestCase):

    def run(self, *args, **kwargs):
        with environment_append({"CONAN_V2_CLI": "1"}):
            super(CliUserTest, self).run(*args, **kwargs)

    def test_user_command(self):
        client = TestClient()

        client.run("user list")
        self.assertIn("remote: remote1 user: someuser1", client.out)
        self.assertIn("remote: remote2 user: someuser2", client.out)
        self.assertIn("remote: remote3 user: someuser3", client.out)
        self.assertIn("remote: remote4 user: someuser4", client.out)
