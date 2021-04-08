import patch_ng
import pytest

from conan.tools.files import patch, apply_conandata_patches
from conans.errors import ConanException
from conans.test.utils.mocks import ConanFileMock


class MockPatchset:
    filename = None
    string = None
    apply_args = None

    def apply(self, root, strip, fuzz):
        self.apply_args = (root, strip, fuzz)
        return True


@pytest.fixture
def mock_patch_ng(monkeypatch):
    mock = MockPatchset()

    def mock_fromfile(filename):
        mock.filename = filename
        return mock

    def mock_fromstring(string):
        mock.string = string
        return mock

    monkeypatch.setattr(patch_ng, "fromfile", mock_fromfile)
    monkeypatch.setattr(patch_ng, "fromstring", mock_fromstring)
    return mock


def test_single_patch_file(mock_patch_ng):
    conanfile = ConanFileMock()
    conanfile.display_name = 'mocked/ref'
    patch(conanfile, patch_file='patch-file')
    assert mock_patch_ng.filename == 'patch-file'
    assert mock_patch_ng.string is None
    assert mock_patch_ng.apply_args == (None, 0, False)
    assert len(str(conanfile.output)) == 0


def test_single_patch_string(mock_patch_ng):
    conanfile = ConanFileMock()
    conanfile.display_name = 'mocked/ref'
    patch(conanfile, patch_string='patch_string')
    assert mock_patch_ng.string == b'patch_string'
    assert mock_patch_ng.filename is None
    assert mock_patch_ng.apply_args == (None, 0, False)
    assert len(str(conanfile.output)) == 0


def test_single_patch_arguments(mock_patch_ng):
    conanfile = ConanFileMock()
    conanfile.display_name = 'mocked/ref'
    patch(conanfile, patch_file='patch-file', base_path='root', strip=23, fuzz=True)
    assert mock_patch_ng.filename == 'patch-file'
    assert mock_patch_ng.apply_args == ('root', 23, True)
    assert len(str(conanfile.output)) == 0


def test_single_patch_type(mock_patch_ng):
    conanfile = ConanFileMock()
    conanfile.display_name = 'mocked/ref'
    patch(conanfile, patch_file='patch-file', patch_type='patch_type')
    assert 'Apply patch (patch_type)\n' == str(conanfile.output)


def test_single_patch_description(mock_patch_ng):
    conanfile = ConanFileMock()
    conanfile.display_name = 'mocked/ref'
    patch(conanfile, patch_file='patch-file', patch_description='patch_description')
    assert 'Apply patch: patch_description\n' == str(conanfile.output)


def test_single_patch_extra_fields(mock_patch_ng):
    conanfile = ConanFileMock()
    conanfile.display_name = 'mocked/ref'
    patch(conanfile, patch_file='patch-file', patch_type='patch_type',
          patch_description='patch_description')
    assert 'Apply patch (patch_type): patch_description\n' == str(conanfile.output)


def test_single_no_patchset(monkeypatch):
    monkeypatch.setattr(patch_ng, "fromfile", lambda _: None)

    conanfile = ConanFileMock()
    conanfile.display_name = 'mocked/ref'
    with pytest.raises(ConanException) as excinfo:
        patch(conanfile, patch_file='patch-file-failed')
    assert 'Failed to parse patch: patch-file-failed' == str(excinfo.value)


def test_single_apply_fail(monkeypatch):
    class MockedApply:
        def apply(self, *args, **kwargs):
            return False

    monkeypatch.setattr(patch_ng, "fromfile", lambda _: MockedApply())

    conanfile = ConanFileMock()
    conanfile.display_name = 'mocked/ref'
    with pytest.raises(ConanException) as excinfo:
        patch(conanfile, patch_file='patch-file-failed')
    assert 'Failed to apply patch: patch-file-failed' == str(excinfo.value)


def test_multiple_no_version(mock_patch_ng):
    conanfile = ConanFileMock()
    conanfile.display_name = 'mocked/ref'
    conanfile.conan_data = {'patches': [
        {'patch_file': 'patches/0001-buildflatbuffers-cmake.patch',
         'base_path': 'source_subfolder', },
        {'patch_file': 'patches/0002-implicit-copy-constructor.patch',
         'base_path': 'source_subfolder',
         'patch_type': 'backport',
         'patch_source': 'https://github.com/google/flatbuffers/pull/5650',
         'patch_description': 'Needed to build with modern clang compilers.'}
    ]}
    apply_conandata_patches(conanfile)
    assert 'Apply patch (backport): Needed to build with modern clang compilers.\n' \
           == str(conanfile.output)


def test_multiple_with_version(mock_patch_ng):
    conanfile = ConanFileMock()
    conanfile.display_name = 'mocked/ref'
    conanfile.conan_data = {'patches': {
        "1.11.0": [
            {'patch_file': 'patches/0001-buildflatbuffers-cmake.patch',
             'base_path': 'source_subfolder', },
            {'patch_file': 'patches/0002-implicit-copy-constructor.patch',
             'base_path': 'source_subfolder',
             'patch_type': 'backport',
             'patch_source': 'https://github.com/google/flatbuffers/pull/5650',
             'patch_description': 'Needed to build with modern clang compilers.'}
        ],
        "1.12.0": [
            {'patch_file': 'patches/0001-buildflatbuffers-cmake.patch',
             'base_path': 'source_subfolder', },
        ]}}

    with pytest.raises(AssertionError) as excinfo:
        apply_conandata_patches(conanfile)
    assert 'Can only be applied if conanfile.version is already defined' == str(excinfo.value)

    conanfile.version = "1.2.11"
    apply_conandata_patches(conanfile)
    assert len(str(conanfile.output)) == 0

    conanfile.version = "1.11.0"
    apply_conandata_patches(conanfile)
    assert 'Apply patch (backport): Needed to build with modern clang compilers.\n' \
           == str(conanfile.output)
