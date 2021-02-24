import gzip
import os
import platform
import sys
import tarfile
from fnmatch import fnmatch
from os.path import abspath, join as joinpath, realpath

import six

from conans.errors import ConanException
from conans.util.fallbacks import default_output
from conans.util.log import logger

UNIT_SIZE = 1000.0


def untargz(filename, destination=".", pattern=None, strip_root=False):
    import tarfile
    with tarfile.TarFile.open(filename, 'r:*') as tarredgzippedFile:
        if not pattern and not strip_root:
            tarredgzippedFile.extractall(destination)
        else:
            members = tarredgzippedFile.getmembers()

            if strip_root:
                names = [n.replace("\\", "/") for n in tarredgzippedFile.getnames()]
                common_folder = os.path.commonprefix(names).split("/", 1)[0]
                if not common_folder and len(names) > 1:
                    raise ConanException("The tgz file contains more than 1 folder in the root")
                if len(names) == 1 and len(names[0].split("/", 1)) == 1:
                    raise ConanException("The tgz file contains a file in the root")
                # Remove the directory entry if present
                members = [m for m in members if m.name != common_folder]
                for member in members:
                    name = member.name.replace("\\", "/")
                    member.name = name.split("/", 1)[1]
                    member.path = member.name
            if pattern:
                members = list(filter(lambda m: fnmatch(m.name, pattern),
                                      tarredgzippedFile.getmembers()))
            tarredgzippedFile.extractall(destination, members=members)


def unzip(filename, destination=".", keep_permissions=False, pattern=None, output=None,
          strip_root=False):
    """
    Unzip a zipped file
    :param filename: Path to the zip file
    :param destination: Destination folder (or file for .gz files)
    :param keep_permissions: Keep the zip permissions. WARNING: Can be
    dangerous if the zip was not created in a NIX system, the bits could
    produce undefined permission schema. Use this option only if you are sure
    that the zip was created correctly.
    :param pattern: Extract only paths matching the pattern. This should be a
    Unix shell-style wildcard, see fnmatch documentation for more details.
    :param output: output
    :param flat: If all the contents are in a single dir, flat that directory.
    :return:
    """
    output = default_output(output, 'conans.client.tools.files.unzip')

    if (filename.endswith(".tar.gz") or filename.endswith(".tgz") or
        filename.endswith(".tbz2") or filename.endswith(".tar.bz2") or
        filename.endswith(".tar")):
        return untargz(filename, destination, pattern, strip_root)
    if filename.endswith(".gz"):
        with gzip.open(filename, 'rb') as f:
            file_content = f.read()
        target_name = filename[:-3] if destination == "." else destination
        save(target_name, file_content)
        return
    if filename.endswith(".tar.xz") or filename.endswith(".txz"):
        if six.PY2:
            raise ConanException("XZ format not supported in Python 2. Use Python 3 instead")
        return untargz(filename, destination, pattern, strip_root)

    import zipfile
    full_path = os.path.normpath(os.path.join(get_cwd(), destination))

    if hasattr(sys.stdout, "isatty") and sys.stdout.isatty():
        def print_progress(the_size, uncomp_size):
            the_size = (the_size * 100.0 / uncomp_size) if uncomp_size != 0 else 0
            txt_msg = "Unzipping %d %%"
            if the_size > print_progress.last_size + 1:
                output.rewrite_line(txt_msg % the_size)
                print_progress.last_size = the_size
                if int(the_size) == 99:
                    output.rewrite_line(txt_msg % 100)
    else:
        def print_progress(_, __):
            pass

    with zipfile.ZipFile(filename, "r") as z:
        zip_info = z.infolist()
        if pattern:
            zip_info = [zi for zi in zip_info if fnmatch(zi.filename, pattern)]
        if strip_root:
            names = [n.replace("\\", "/") for n in z.namelist()]
            common_folder = os.path.commonprefix(names).split("/", 1)[0]
            if not common_folder and len(names) > 1:
                raise ConanException("The zip file contains more than 1 folder in the root")
            if len(names) == 1 and len(names[0].split("/", 1)) == 1:
                raise ConanException("The zip file contains a file in the root")
            # Remove the directory entry if present
            # Note: The "zip" format contains the "/" at the end if it is a directory
            zip_info = [m for m in zip_info if m.filename != (common_folder + "/")]
            for member in zip_info:
                name = member.filename.replace("\\", "/")
                member.filename = name.split("/", 1)[1]

        uncompress_size = sum((file_.file_size for file_ in zip_info))
        if uncompress_size > 100000:
            output.info("Unzipping %s, this can take a while" % human_size(uncompress_size))
        else:
            output.info("Unzipping %s" % human_size(uncompress_size))
        extracted_size = 0

        print_progress.last_size = -1
        if platform.system() == "Windows":
            for file_ in zip_info:
                extracted_size += file_.file_size
                print_progress(extracted_size, uncompress_size)
                try:
                    z.extract(file_, full_path)
                except Exception as e:
                    output.error("Error extract %s\n%s" % (file_.filename, str(e)))
        else:  # duplicated for, to avoid a platform check for each zipped file
            for file_ in zip_info:
                extracted_size += file_.file_size
                print_progress(extracted_size, uncompress_size)
                try:
                    z.extract(file_, full_path)
                    if keep_permissions:
                        # Could be dangerous if the ZIP has been created in a non nix system
                        # https://bugs.python.org/issue15795
                        perm = file_.external_attr >> 16 & 0xFFF
                        os.chmod(os.path.join(full_path, file_.filename), perm)
                except Exception as e:
                    output.error("Error extract %s\n%s" % (file_.filename, str(e)))
        output.writeln("")


def human_size(size_bytes):
    """
    format a size in bytes into a 'human' file size, e.g. B, KB, MB, GB, TB, PB
    Note that bytes will be reported in whole numbers but KB and above will have
    greater precision.  e.g. 43 B, 443 KB, 4.3 MB, 4.43 GB, etc
    """

    suffixes_table = [('B', 0), ('KB', 1), ('MB', 1), ('GB', 2), ('TB', 2), ('PB', 2)]

    num = float(size_bytes)
    for suffix, precision in suffixes_table:
        if num < UNIT_SIZE:
            break
        num /= UNIT_SIZE

    if precision == 0:
        formatted_size = "%d" % num
    else:
        formatted_size = str(round(num, ndigits=precision))

    return "%s%s" % (formatted_size, suffix)


def gzopen_without_timestamps(name, mode="r", fileobj=None, **kwargs):
    """ !! Method overrided by laso to pass mtime=0 (!=None) to avoid time.time() was
        setted in Gzip file causing md5 to change. Not possible using the
        previous tarfile open because arguments are not passed to GzipFile constructor
    """
    compresslevel = int(os.getenv("CONAN_COMPRESSION_LEVEL", 9))

    if mode not in ("r", "w"):
        raise ValueError("mode must be 'r' or 'w'")

    try:
        fileobj = gzip.GzipFile(name, mode, compresslevel, fileobj, mtime=0)
    except OSError:
        if fileobj is not None and mode == 'r':
            raise tarfile.ReadError("not a gzip file")
        raise

    try:
        # Format is forced because in Python3.8, it changed and it generates different tarfiles
        # with different checksums, which break hashes of tgzs
        t = tarfile.TarFile.taropen(name, mode, fileobj, format=tarfile.GNU_FORMAT, **kwargs)
    except IOError:
        fileobj.close()
        if mode == 'r':
            raise tarfile.ReadError("not a gzip file")
        raise
    except Exception:
        fileobj.close()
        raise
    t._extfileobj = False
    return t


def tar_extract(fileobj, destination_dir):
    """Extract tar file controlling not absolute paths and fixing the routes
    if the tar was zipped in windows"""

    def badpath(path, base):
        # joinpath will ignore base if path is absolute
        return not realpath(abspath(joinpath(base, path))).startswith(base)

    def safemembers(members):
        base = realpath(abspath(destination_dir))

        for finfo in members:
            if badpath(finfo.name, base) or finfo.islnk():
                logger.warning("file:%s is skipped since it's not safe." % str(finfo.name))
                continue
            else:
                # Fixes unzip a windows zipped file in linux
                finfo.name = finfo.name.replace("\\", "/")
                yield finfo

    the_tar = tarfile.open(fileobj=fileobj)
    # NOTE: The errorlevel=2 has been removed because it was failing in Win10, it didn't allow to
    # "could not change modification time", with time=0
    # the_tar.errorlevel = 2  # raise exception if any error
    the_tar.extractall(path=destination_dir, members=safemembers(the_tar))
    the_tar.close()
