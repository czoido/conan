import errno
import os

import six

from conans.client.downloaders.download import run_downloader
from conans.util.compress import unzip
from conans.errors import ConanException
from conans.util.fallbacks import default_output, default_requester


def _to_file_bytes(content, encoding="utf-8"):
    if six.PY3:
        if not isinstance(content, bytes):
            content = bytes(content, encoding)
    elif isinstance(content, unicode):
        content = content.encode(encoding)
    return content


def _detect_encoding(text):
    import codecs
    encodings = {codecs.BOM_UTF8: "utf_8_sig",
                 codecs.BOM_UTF16_BE: "utf_16_be",
                 codecs.BOM_UTF16_LE: "utf_16_le",
                 codecs.BOM_UTF32_BE: "utf_32_be",
                 codecs.BOM_UTF32_LE: "utf_32_le",
                 b'\x2b\x2f\x76\x38': "utf_7",
                 b'\x2b\x2f\x76\x39': "utf_7",
                 b'\x2b\x2f\x76\x2b': "utf_7",
                 b'\x2b\x2f\x76\x2f': "utf_7",
                 b'\x2b\x2f\x76\x38\x2d': "utf_7"}
    for bom in sorted(encodings, key=len, reverse=True):
        if text.startswith(bom):
            try:
                return encodings[bom], len(bom)
            except UnicodeDecodeError:
                continue
    decoders = ["utf-8", "Windows-1252"]
    for decoder in decoders:
        try:
            text.decode(decoder)
            return decoder, 0
        except UnicodeDecodeError:
            continue


def _decode_text(text, encoding="auto"):
    bom_length = 0
    if encoding == "auto":
        encoding, bom_length = _detect_encoding(text)
        if encoding is None:
            return text.decode("utf-8", "ignore")  # Ignore not compatible characters
    return text[bom_length:].decode(encoding)


def load(path, binary=False, encoding="auto"):
    """ Loads a file content """
    with open(path, 'rb') as handle:
        tmp = handle.read()
        return tmp if binary else _decode_text(tmp, encoding)


def save(path, content, only_if_modified=False, encoding="utf-8"):
    """
    Saves a file with given content
    Params:
        path: path to write file to
        content: contents to save in the file
        only_if_modified: file won't be modified if the content hasn't changed
        encoding: target file text encoding
    """
    dir_path = os.path.dirname(path)
    if not os.path.isdir(dir_path):
        try:
            os.makedirs(dir_path)
        except OSError as error:
            if error.errno not in (errno.EEXIST, errno.ENOENT):
                raise OSError("The folder {} does not exist and could not be created ({})."
                              .format(dir_path, error.strerror))
        except Exception:
            raise

    new_content = _to_file_bytes(content, encoding)

    if only_if_modified and os.path.exists(path):
        old_content = load(path, binary=True, encoding=encoding)
        if old_content == new_content:
            return

    with open(path, "wb") as handle:
        handle.write(new_content)


def mkdir(path):
    """Recursive mkdir, doesnt fail if already existing"""
    if os.path.exists(path):
        return
    os.makedirs(path)


def get(url, md5='', sha1='', sha256='', destination=".", filename="", keep_permissions=False,
        pattern=None, requester=None, output=None, verify=True, retry=None, retry_wait=None,
        overwrite=False, auth=None, headers=None, strip_root=False):
    """ high level downloader + unzipper + (optional hash checker) + delete temporary zip
    """

    if not filename:  # deduce filename from the URL
        url_base = url[0] if isinstance(url, (list, tuple)) else url
        if "?" in url_base or "=" in url_base:
            raise ConanException("Cannot deduce file name from the url: '{}'. Use 'filename' "
                                 "parameter.".format(url_base))
        filename = os.path.basename(url_base)

    download(url, filename, out=output, requester=requester, verify=verify, retry=retry,
             retry_wait=retry_wait, overwrite=overwrite, auth=auth, headers=headers,
             md5=md5, sha1=sha1, sha256=sha256)
    unzip(filename, destination=destination, keep_permissions=keep_permissions, pattern=pattern,
          output=output, strip_root=strip_root)
    os.unlink(filename)


def ftp_download(ip, filename, login='', password=''):
    import ftplib
    try:
        ftp = ftplib.FTP(ip)
        ftp.login(login, password)
        filepath, filename = os.path.split(filename)
        if filepath:
            ftp.cwd(filepath)
        with open(filename, 'wb') as f:
            ftp.retrbinary('RETR ' + filename, f.write)
    except Exception as e:
        try:
            os.unlink(filename)
        except OSError:
            pass
        raise ConanException("Error in FTP download from %s\n%s" % (ip, str(e)))
    finally:
        try:
            ftp.quit()
        except Exception:
            pass


def download(url, filename, verify=True, out=None, retry=None, retry_wait=None, overwrite=False,
             auth=None, headers=None, requester=None, md5='', sha1='', sha256=''):
    """Retrieves a file from a given URL into a file with a given filename.
       It uses certificates from a list of known verifiers for https downloads,
       but this can be optionally disabled.

    :param url: URL to download. It can be a list, which only the first one will be downloaded, and
                the follow URLs will be used as mirror in case of download error.
    :param filename: Name of the file to be created in the local storage
    :param verify: When False, disables https certificate validation
    :param out: An object with a write() method can be passed to get the output. stdout will use if
                not specified
    :param retry: Number of retries in case of failure. Default is overriden by general.retry in the
                  conan.conf file or an env variable CONAN_RETRY
    :param retry_wait: Seconds to wait between download attempts. Default is overriden by
                       general.retry_wait in the conan.conf file or an env variable CONAN_RETRY_WAIT
    :param overwrite: When True, Conan will overwrite the destination file if exists. Otherwise it
                      will raise an exception
    :param auth: A tuple of user and password to use HTTPBasic authentication
    :param headers: A dictionary with additional headers
    :param requester: HTTP requests instance
    :param md5: MD5 hash code to check the downloaded file
    :param sha1: SHA-1 hash code to check the downloaded file
    :param sha256: SHA-256 hash code to check the downloaded file
    :return: None
    """
    out = default_output(out, 'conan.tools.files')
    requester = default_requester(requester, 'conan.tools.files')
    from conans.tools import _global_config as config

    # It might be possible that users provide their own requester
    retry = retry if retry is not None else config.retry
    retry = retry if retry is not None else 1
    retry_wait = retry_wait if retry_wait is not None else config.retry_wait
    retry_wait = retry_wait if retry_wait is not None else 5

    checksum = sha256 or sha1 or md5

    def _download_file(file_url):
        # The download cache is only used if a checksum is provided, otherwise, a normal download
        run_downloader(requester=requester, output=out, verify=verify, config=config,
                       user_download=True, use_cache=bool(config and checksum), url=file_url,
                       file_path=filename, retry=retry, retry_wait=retry_wait, overwrite=overwrite,
                       auth=auth, headers=headers, md5=md5, sha1=sha1, sha256=sha256)
        out.writeln("")

    if not isinstance(url, (list, tuple)):
        _download_file(url)
    else:  # We were provided several URLs to try
        for url_it in url:
            try:
                _download_file(url_it)
                break
            except Exception as error:
                message = "Could not download from the URL {}: {}.".format(url_it, str(error))
                out.warn(message + " Trying another mirror.")
        else:
            raise ConanException("All downloads from ({}) URLs have failed.".format(len(url)))
