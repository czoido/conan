import logging
import os
import platform
import stat
import subprocess
import sys
from contextlib import contextmanager
from fnmatch import fnmatch

from patch_ng import fromfile, fromstring

from conans.client.output import ConanOutput
from conans.errors import ConanException
from conans.unicode import get_cwd
from conans.util.fallbacks import default_output
from conans.util.hash import check_with_algorithm_sum, check_sha1, check_md5, check_sha256
from conans.util.compress import unzip, human_size, untargz
from conan.tools.files import load, save, mkdir


# Library extensions supported by collect_libs
VALID_LIB_EXTENSIONS = (".so", ".lib", ".a", ".dylib", ".bc")


@contextmanager
def chdir(newdir):
    old_path = get_cwd()
    os.chdir(newdir)
    try:
        yield
    finally:
        os.chdir(old_path)


def patch(base_path=None, patch_file=None, patch_string=None, strip=0, output=None, fuzz=False):
    """ Applies a diff from file (patch_file)  or string (patch_string)
        in base_path directory or current dir if None
    :param base_path: Base path where the patch should be applied.
    :param patch_file: Patch file that should be applied.
    :param patch_string: Patch string that should be applied.
    :param strip: Number of folders to be stripped from the path.
    :param output: Stream object.
    :param fuzz: Should accept fuzzy patches.
    """

    class PatchLogHandler(logging.Handler):
        def __init__(self):
            logging.Handler.__init__(self, logging.DEBUG)
            self.output = output or ConanOutput(sys.stdout, sys.stderr, color=True)
            self.patchname = patch_file if patch_file else "patch_ng"

        def emit(self, record):
            logstr = self.format(record)
            if record.levelno == logging.WARN:
                self.output.warn("%s: %s" % (self.patchname, logstr))
            else:
                self.output.info("%s: %s" % (self.patchname, logstr))

    patchlog = logging.getLogger("patch_ng")
    if patchlog:
        patchlog.handlers = []
        patchlog.addHandler(PatchLogHandler())

    if not patch_file and not patch_string:
        return
    if patch_file:
        patchset = fromfile(patch_file)
    else:
        patchset = fromstring(patch_string.encode())

    if not patchset:
        raise ConanException("Failed to parse patch: %s" % (patch_file if patch_file else "string"))

    if not patchset.apply(root=base_path, strip=strip, fuzz=fuzz):
        raise ConanException("Failed to apply patch: %s" % patch_file)


def _manage_text_not_found(search, file_path, strict, function_name, output):
    message = "%s didn't find pattern '%s' in '%s' file." % (function_name, search, file_path)
    if strict:
        raise ConanException(message)
    else:
        output.warn(message)
        return False


@contextmanager
def _add_write_permissions(file_path):
    # Assumes the file already exist in disk
    write = stat.S_IWRITE
    saved_permissions = os.stat(file_path).st_mode
    if saved_permissions & write == write:
        yield
        return
    try:
        os.chmod(file_path, saved_permissions | write)
        yield
    finally:
        os.chmod(file_path, saved_permissions)


def replace_in_file(file_path, search, replace, strict=True, output=None, encoding=None):
    output = default_output(output, 'conans.client.tools.files.replace_in_file')

    encoding_in = encoding or "auto"
    encoding_out = encoding or "utf-8"
    content = load(file_path, encoding=encoding_in)
    if -1 == content.find(search):
        _manage_text_not_found(search, file_path, strict, "replace_in_file", output=output)
    content = content.replace(search, replace)
    content = content.encode(encoding_out)
    with _add_write_permissions(file_path):
        save(file_path, content, only_if_modified=False, encoding=encoding_out)


def replace_path_in_file(file_path, search, replace, strict=True, windows_paths=None, output=None,
                         encoding=None):
    output = default_output(output, 'conans.client.tools.files.replace_path_in_file')

    if windows_paths is False or (windows_paths is None and platform.system() != "Windows"):
        return replace_in_file(file_path, search, replace, strict=strict, output=output,
                               encoding=encoding)

    def normalized_text(text):
        return text.replace("\\", "/").lower()

    encoding_in = encoding or "auto"
    encoding_out = encoding or "utf-8"
    content = load(file_path, encoding=encoding_in)
    normalized_content = normalized_text(content)
    normalized_search = normalized_text(search)
    index = normalized_content.find(normalized_search)
    if index == -1:
        return _manage_text_not_found(search, file_path, strict, "replace_path_in_file",
                                      output=output)

    while index != -1:
        content = content[:index] + replace + content[index + len(search):]
        normalized_content = normalized_text(content)
        index = normalized_content.find(normalized_search)

    content = content.encode(encoding_out)
    with _add_write_permissions(file_path):
        save(file_path, content, only_if_modified=False, encoding=encoding_out)

    return True


def replace_prefix_in_pc_file(pc_file, new_prefix):
    content = load(pc_file)
    lines = []
    for line in content.splitlines():
        if line.startswith("prefix="):
            lines.append('prefix=%s' % new_prefix)
        else:
            lines.append(line)
    with _add_write_permissions(pc_file):
        save(pc_file, "\n".join(lines))


def _path_equals(path1, path2):
    path1 = os.path.normpath(path1)
    path2 = os.path.normpath(path2)
    if platform.system() == "Windows":
        path1 = path1.lower().replace("sysnative", "system32")
        path2 = path2.lower().replace("sysnative", "system32")
    return path1 == path2


def collect_libs(conanfile, folder=None):
    if not conanfile.package_folder:
        return []
    if folder:
        lib_folders = [os.path.join(conanfile.package_folder, folder)]
    else:
        lib_folders = [os.path.join(conanfile.package_folder, folder)
                       for folder in conanfile.cpp_info.libdirs]
    result = []
    for lib_folder in lib_folders:
        if not os.path.exists(lib_folder):
            conanfile.output.warn("Lib folder doesn't exist, can't collect libraries: "
                                  "{0}".format(lib_folder))
            continue
        files = os.listdir(lib_folder)
        for f in files:
            name, ext = os.path.splitext(f)
            if ext in VALID_LIB_EXTENSIONS:
                if ext != ".lib" and name.startswith("lib"):
                    name = name[3:]
                if name in result:
                    conanfile.output.warn("Library '%s' was either already found in a previous "
                                          "'conanfile.cpp_info.libdirs' folder or appears several "
                                          "times with a different file extension" % name)
                else:
                    result.append(name)
    result.sort()
    return result


def which(filename):
    """ same affect as posix which command or shutil.which from python3 """
    # FIXME: Replace with shutil.which in Conan 2.0
    def verify(file_abspath):
        return os.path.isfile(file_abspath) and os.access(file_abspath, os.X_OK)

    def _get_possible_filenames(fname):
        if platform.system() != "Windows":
            extensions = [".sh", ""]
        else:
            if "." in filename:  # File comes with extension already
                extensions = [""]
            else:
                pathext = os.getenv("PATHEXT", ".COM;.EXE;.BAT;.CMD").split(";")
                extensions = [extension.lower() for extension in pathext]
                extensions.insert(1, "")  # No extension
        return ["%s%s" % (fname, extension) for extension in extensions]

    possible_names = _get_possible_filenames(filename)
    for path in os.environ["PATH"].split(os.pathsep):
        for name in possible_names:
            filepath = os.path.abspath(os.path.join(path, name))
            if verify(filepath):
                return filepath
            if platform.system() == "Windows":
                filepath = filepath.lower()
                if "system32" in filepath:
                    # python return False for os.path.exists of exes in System32 but with SysNative
                    trick_path = filepath.replace("system32", "sysnative")
                    if verify(trick_path):
                        return trick_path

    return None


def _replace_with_separator(filepath, sep):
    tmp = load(filepath)
    ret = sep.join(tmp.splitlines())
    if tmp.endswith("\n"):
        ret += sep
    save(filepath, ret)


def unix2dos(filepath):
    _replace_with_separator(filepath, "\r\n")


def dos2unix(filepath):
    _replace_with_separator(filepath, "\n")


def rename(src, dst):
    """
    rename a file or folder to avoid "Access is denied" error on Windows
    :param src: Source file or folder
    :param dst: Destination file or folder
    """
    if os.path.exists(dst):
        raise ConanException("rename {} to {} failed, dst exists.".format(src, dst))

    if platform.system() == "Windows" and which("robocopy") and os.path.isdir(src):
        # /move Moves files and directories, and deletes them from the source after they are copied.
        # /e Copies subdirectories. Note that this option includes empty directories.
        # /ndl Specifies that directory names are not to be logged.
        # /nfl Specifies that file names are not to be logged.
        process = subprocess.Popen(["robocopy", "/move", "/e", "/ndl", "/nfl", src, dst],
                                   stdout=subprocess.PIPE)
        process.communicate()
        if process.returncode != 1:
            raise ConanException("rename {} to {} failed.".format(src, dst))
    else:
        try:
            os.rename(src, dst)
        except Exception as err:
            raise ConanException("rename {} to {} failed: {}".format(src, dst, err))


def remove_files_by_mask(directory, pattern):
    removed_names = []
    for root, _, filenames in os.walk(directory):
        for filename in filenames:
            if fnmatch(filename, pattern):
                fullname = os.path.join(root, filename)
                os.unlink(fullname)
                removed_names.append(os.path.relpath(fullname, directory))
    return removed_names


def fix_symlinks(conanfile, raise_if_error=False):
    """ Fix the symlinks in the conanfile.package_folder: make symlinks relative and remove
        those links to files outside the package (it will print an error, or raise
        if 'raise_if_error' evaluates to true).
    """
    offending_files = []

    def work_on_element(dirpath, element, token):
        fullpath = os.path.join(dirpath, element)
        if not os.path.islink(fullpath):
            return

        link_target = os.readlink(fullpath)
        if link_target in ['/dev/null', ]:
            return

        link_abs_target = os.path.join(dirpath, link_target)
        link_rel_target = os.path.relpath(link_abs_target, conanfile.package_folder)
        if link_rel_target.startswith('..') or os.path.isabs(link_rel_target):
            offending_file = os.path.relpath(fullpath, conanfile.package_folder)
            offending_files.append(offending_file)
            conanfile.output.error("{token} '{item}' links to a {token} outside the package, "
                                   "it's been removed.".format(item=offending_file, token=token))
            os.unlink(fullpath)
        elif not os.path.exists(link_abs_target):
            # This is a broken symlink. Failure is controlled by config variable
            #  'general.skip_broken_symlinks_check'. Do not fail here.
            offending_file = os.path.relpath(fullpath, conanfile.package_folder)
            offending_files.append(offending_file)
            conanfile.output.error("{token} '{item}' links to a path that doesn't exist, it's"
                                   " been removed.".format(item=offending_file, token=token))
            os.unlink(fullpath)
        elif link_target != link_rel_target:
            os.unlink(fullpath)
            os.symlink(link_rel_target, fullpath)

    for (dirpath, dirnames, filenames) in os.walk(conanfile.package_folder):
        for filename in filenames:
            work_on_element(dirpath, filename, token="file")

        for dirname in dirnames:
            work_on_element(dirpath, dirname, token="directory")

    if offending_files and raise_if_error:
        raise ConanException("There are invalid symlinks in the package!")
