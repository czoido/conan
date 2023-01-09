import os
import re
import time

from conan.api.output import ConanOutput, ConanProgress
from conans.client.rest import response_to_str
from conans.errors import ConanException, NotFoundException, AuthenticationException, \
    ForbiddenException, ConanConnectionError, RequestErrorException
from conans.util.sha import check_with_algorithm_sum
from conans.util.thread import ExceptionThread
from conans.util.tracer import log_download


class FileDownloader:

    def __init__(self, requester):
        self._output = ConanOutput()
        self._requester = requester
        self._progress = ConanProgress()

    def _prepare_download(self, urls, dest_folder, files, overwrite):
        sorted_files = sorted(files, reverse=True)
        for filename in sorted_files:
            abs_path = os.path.join(dest_folder, filename)
            os.makedirs(os.path.dirname(abs_path), exist_ok=True)  # filename in subfolder must exist

            assert abs_path, "Conan 2.0 always download files to disk, not to memory"
            assert os.path.isabs(abs_path), "Target file_path must be absolute"

            if os.path.exists(abs_path):
                if overwrite:
                    self._output.warning("file '%s' already exists, overwriting" % abs_path)
                else:
                    # Should not happen, better to raise, probably we had to remove
                    # the dest folder before
                    raise ConanException("Error, the file to download already exists: '%s'" % abs_path)
        return sorted_files

    def _download_with_retry(self, url, auth, headers, file_path, verify_ssl, retry, retry_wait,
                             md5, sha1, sha256):
        try:
            for counter in range(retry + 1):
                try:
                    self._download_file(url, auth, headers, file_path, verify_ssl)
                    break
                except (NotFoundException, ForbiddenException, AuthenticationException,
                        RequestErrorException):
                    raise
                except ConanException as exc:
                    if counter == retry:
                        raise
                    else:
                        self._output.error(exc)
                        self._output.info(f"Waiting {retry_wait} seconds to retry...")
                        time.sleep(retry_wait)

            self._check_checksum(file_path, md5, sha1, sha256)
        except Exception:
            if os.path.exists(file_path):
                os.remove(file_path)
            raise

    def download(self, urls, dest_folder, files, retry=2, retry_wait=0, verify_ssl=True, auth=None,
                 overwrite=False, headers=None, md5=None, sha1=None, sha256=None, parallel=False):
        """ in order to make the download concurrent, the folder for file_path MUST exist
        """
        sorted_files_download = self._prepare_download(urls, dest_folder, files, overwrite)
        threads = []
        with self._progress.progress:
            for filename in sorted_files_download:
                url = urls[filename]
                file_path = os.path.join(dest_folder, filename)
                if parallel:
                    kwargs = {"url": url, "auth": auth, "headers": headers, "file_path": file_path,
                              "verify_ssl": verify_ssl, "retry": retry, "retry_wait": retry_wait,
                              "md5": md5, "sha1": sha1, "sha256": sha256}
                    thread = ExceptionThread(target=self._download_with_retry, kwargs=kwargs)
                    threads.append(thread)
                    thread.start()
                else:
                    self._download_with_retry(url, auth, headers, file_path, verify_ssl, retry,
                                              retry_wait, md5, sha1, sha256)
            for t in threads:
                t.join()

    @staticmethod
    def _response_chunks(response, size=1024 * 100):
        for chunk in response.iter_content(size):
            yield chunk

    @staticmethod
    def _check_checksum(file_path, md5, sha1, sha256):
        if md5 is not None:
            check_with_algorithm_sum("md5", file_path, md5)
        if sha1 is not None:
            check_with_algorithm_sum("sha1", file_path, sha1)
        if sha256 is not None:
            check_with_algorithm_sum("sha256", file_path, sha256)

    def _download_file(self, url, auth, headers, file_path, verify_ssl, try_resume=False):
        t1 = time.time()
        if try_resume and os.path.exists(file_path):
            range_start = os.path.getsize(file_path)
            headers = headers.copy() if headers else {}
            headers["range"] = "bytes={}-".format(range_start)
        else:
            range_start = 0

        try:
            response = self._requester.get(url, stream=True, verify=verify_ssl, auth=auth,
                                           headers=headers)
        except Exception as exc:
            raise ConanException("Error downloading file %s: '%s'" % (url, exc))

        if not response.ok:
            if response.status_code == 404:
                raise NotFoundException("Not found: %s" % url)
            elif response.status_code == 403:
                if auth is None or (hasattr(auth, "token") and auth.token is None):
                    # TODO: This is a bit weird, why this conversion? Need to investigate
                    raise AuthenticationException(response_to_str(response))
                raise ForbiddenException(response_to_str(response))
            elif response.status_code == 401:
                raise AuthenticationException()
            raise ConanException("Error %d downloading file %s" % (response.status_code, url))

        def get_total_length():
            if range_start:
                content_range = response.headers.get("Content-Range", "")
                match = re.match(r"^bytes (\d+)-(\d+)/(\d+)", content_range)
                if not match or range_start != int(match.group(1)):
                    raise ConanException("Error in resumed download from %s\n"
                                         "Incorrect Content-Range header %s" % (url, content_range))
                return int(match.group(3))
            else:
                total_size = response.headers.get('Content-Length') or len(response.content)
                return int(total_size)

        try:
            total_length = get_total_length()
            action = "Downloading" if range_start == 0 else "Continuing download of"
            description = "{} {}".format(action, os.path.basename(file_path))

            use_progress_bars = True
            if use_progress_bars:
                chunks = self._progress.add_bar(self._response_chunks(response), total_length,
                                                description)
            else:
                chunks = self._response_chunks(response)
                self._output.info(description)

            total_downloaded_size = range_start
            mode = "ab" if range_start else "wb"

            with open(file_path, mode) as file_handler:
                for chunk in chunks:
                    file_handler.write(chunk)
                    total_downloaded_size += len(chunk)

            gzip = (response.headers.get("content-encoding") == "gzip")
            response.close()
            # it seems that if gzip we don't know the size, cannot resume and shouldn't raise
            if total_downloaded_size != total_length and not gzip:
                if (total_length > total_downloaded_size > range_start
                        and response.headers.get("Accept-Ranges") == "bytes"):
                    self._download_file(url, auth, headers, file_path, verify_ssl, try_resume=True)
                else:
                    raise ConanException("Transfer interrupted before complete: %s < %s"
                                         % (total_downloaded_size, total_length))

            duration = time.time() - t1
            log_download(url, duration)

        except Exception as e:
            # If this part failed, it means problems with the connection to server
            raise ConanConnectionError("Download failed, check server, possibly try again\n%s"
                                       % str(e))
