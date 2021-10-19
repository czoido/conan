import pytest
from conans.test.assets.genconanfile import GenConanfile
from conans.test.utils.tools import TestClient


@pytest.fixture(scope="module")
def build_all():
    """ Build a simple graph to test --build option
        foobar <- bar <- foo
               <--------|
        All packages are built from sources to keep a cache.
    :return: TestClient instance
    """
    client = TestClient()
    client.save({"conanfile.py": GenConanfile().with_setting("build_type")})
    client.run("export . foo/1.0@user/testing")
    client.save({"conanfile.py": GenConanfile().with_require("foo/1.0@user/testing")
                .with_setting("build_type")})
    client.run("export . bar/1.0@user/testing")
    client.save({"conanfile.py": GenConanfile().with_require("foo/1.0@user/testing")
                .with_require("bar/1.0@user/testing")
                .with_setting("build_type")})
    client.run("export . foobar/1.0@user/testing")
    client.run("install foobar/1.0@user/testing --build")

    return client


foo_id = "e53d55fd33066c49eb97a4ede6cb50cd8036fe8b"
bar_id = "1eb1d823cd7f59878ddfa73183c6f29ecf42ebfe"
foobar_id = "b2e76a33737572a9e07c173b8ea3572520c3c2cb"


def check_if_build_from_sources(refs_modes, output):
    for ref, mode in refs_modes.items():
        if mode == "Build":
            assert "{}/1.0@user/testing: Forced build from source".format(ref) in output
        else:
            assert "{}/1.0@user/testing: Forced build from source".format(ref) not in output


def test_install_build_single(build_all):
    """ When only --build=<ref> is passed, only <ref> must be built
    """
    build_all.run("install foobar/1.0@user/testing --build=foo")

    assert f"bar/1.0@user/testing:{bar_id} - Cache" in build_all.out
    assert f"foo/1.0@user/testing:{foo_id} - Build" in build_all.out
    assert f"foobar/1.0@user/testing:{foobar_id} - Cache" in build_all.out
    assert "foo/1.0@user/testing: Forced build from source" in build_all.out
    assert "bar/1.0@user/testing: Forced build from source" not in build_all.out
    assert "foobar/1.0@user/testing: Forced build from source" not in build_all.out
    assert "No package matching" not in build_all.out


def test_install_build_double(build_all):
    """ When both --build=<ref1> and --build=<ref2> are passed, only both should be built
    """
    build_all.run("install foobar/1.0@user/testing --build=foo --build=bar")

    assert f"bar/1.0@user/testing:{bar_id} - Build" in build_all.out
    assert f"foo/1.0@user/testing:{foo_id} - Build" in build_all.out
    assert f"foobar/1.0@user/testing:{foobar_id} - Cache" in build_all.out
    assert "foo/1.0@user/testing: Forced build from source" in build_all.out
    assert "bar/1.0@user/testing: Forced build from source" in build_all.out
    assert "foobar/1.0@user/testing: Forced build from source" not in build_all.out
    assert "No package matching" not in build_all.out


@pytest.mark.parametrize("build_arg,mode", [("--build", "Build"),
                                            ("--build=", "Cache"),
                                            ("--build=*", "Build")])
def test_install_build_only(build_arg, mode, build_all):
    """ When only --build is passed, all packages must be built from sources
        When only --build= is passed, it's considered an error
        When only --build=* is passed, all packages must be built from sources
    """
    build_all.run("install foobar/1.0@user/testing {}".format(build_arg))

    assert f"bar/1.0@user/testing:{bar_id} - {mode}" in build_all.out
    assert f"foo/1.0@user/testing:{foo_id} - {mode}" in build_all.out
    assert f"foobar/1.0@user/testing:{foobar_id} - {mode}" in build_all.out

    if "Build" == mode:
        assert "foo/1.0@user/testing: Forced build from source" in build_all.out
        assert "bar/1.0@user/testing: Forced build from source" in build_all.out
        assert "foobar/1.0@user/testing: Forced build from source" in build_all.out
        # FIXME assert "No package matching" not in build_all.out
    else:
        assert "foo/1.0@user/testing: Forced build from source" not in build_all.out
        assert "bar/1.0@user/testing: Forced build from source" not in build_all.out
        assert "foobar/1.0@user/testing: Forced build from source" not in build_all.out
        # FIXME assert "No package matching" in build_all.out


@pytest.mark.parametrize("build_arg,bar,foo,foobar", [("--build", "Cache", "Build", "Cache"),
                                                      ("--build=", "Cache", "Build", "Cache"),
                                                      ("--build=*", "Build", "Build", "Build")])
def test_install_build_all_with_single(build_arg, bar, foo, foobar, build_all):
    """ When --build is passed with another package, only the package must be built from sources.
        When --build= is passed with another package, only the package must be built from sources.
        When --build=* is passed with another package, all packages must be built from sources.
    """
    build_all.run("install foobar/1.0@user/testing --build=foo {}".format(build_arg))

    assert f"bar/1.0@user/testing:{bar_id} - {bar}" in build_all.out
    assert f"foo/1.0@user/testing:{foo_id} - {foo}" in build_all.out
    assert f"foobar/1.0@user/testing:{foobar_id} - {foobar}" in build_all.out
    check_if_build_from_sources({"foo": foo, "bar": bar, "foobar": foobar}, build_all.out)


@pytest.mark.parametrize("build_arg,bar,foo,foobar", [("--build", "Cache", "Cache", "Cache"),
                                                      ("--build=", "Cache", "Cache", "Cache"),
                                                      ("--build=*", "Build", "Cache", "Build")])
def test_install_build_all_with_single_skip(build_arg, bar, foo, foobar, build_all):
    """ When --build is passed with a skipped package, not all packages must be built from sources.
        When --build= is passed with another package, only the package must be built from sources.
        When --build=* is passed with another package, not all packages must be built from sources.
        The arguments order matter, that's why we need to run twice.
    """
    for argument in ["--build=!foo {}".format(build_arg),
                     "{} --build=!foo".format(build_arg)]:
        build_all.run("install foobar/1.0@user/testing {}".format(argument))
        assert f"bar/1.0@user/testing:{bar_id} - {bar}" in build_all.out
        assert f"foo/1.0@user/testing:{foo_id} - {foo}" in build_all.out
        assert f"foobar/1.0@user/testing:{foobar_id} - {foobar}" in build_all.out
        check_if_build_from_sources({"foo": foo, "bar": bar, "foobar": foobar}, build_all.out)


@pytest.mark.parametrize("build_arg,bar,foo,foobar", [("--build", "Cache", "Cache", "Cache"),
                                                      ("--build=", "Cache", "Cache", "Cache"),
                                                      ("--build=*", "Cache", "Cache", "Build")])
def test_install_build_all_with_double_skip(build_arg, bar, foo, foobar, build_all):
    """ When --build is passed with a skipped package, not all packages must be built from sources.
        When --build= is passed with another package, only the package must be built from sources.
        When --build=* is passed with another package, not all packages must be built from sources.
        The arguments order matter, that's why we need to run twice.
    """
    for argument in ["--build=!foo --build=!bar {}".format(build_arg),
                     "{} --build=!foo --build=!bar".format(build_arg)]:
        build_all.run("install foobar/1.0@user/testing {}".format(argument))

        assert f"bar/1.0@user/testing:{bar_id} - {bar}" in build_all.out
        assert f"foo/1.0@user/testing:{foo_id} - {foo}" in build_all.out
        assert f"foobar/1.0@user/testing:{foobar_id} - {foobar}" in build_all.out


def test_report_matches(build_all):
    """ When a wrong reference is passed to be build, an error message should be shown
    """
    build_all.run("install foobar/1.0@user/testing --build=* --build=baz")
    assert f"foobar/1.0@user/testing:{foobar_id} - Build" in build_all.out
    # FIXME assert "No package matching 'baz' pattern found." in build_all.out

    build_all.run("install foobar/1.0@user/testing --build=* --build=!baz")
    # FIXME assert "No package matching 'baz' pattern found." in build_all.out
    assert f"foobar/1.0@user/testing:{foobar_id} - Build" in build_all.out

    build_all.run("install foobar/1.0@user/testing --build=* --build=!baz --build=blah")
    # FIXME assert "No package matching 'blah' pattern found." in build_all.out
    # FIXME assert "No package matching 'baz' pattern found." in build_all.out
    assert f"foobar/1.0@user/testing:{foobar_id} - Build" in build_all.out

    build_all.run("install foobar/1.0@user/testing --build=* --build=!baz --build=!blah")
    # FIXME  assert "No package matching 'blah' pattern found." in build_all.out
    # FIXME assert "No package matching 'baz' pattern found." in build_all.out
    assert f"foobar/1.0@user/testing:{foobar_id} - Build" in build_all.out
