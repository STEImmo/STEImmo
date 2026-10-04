"""Bound multipart uploads before CSRF or form validation parses them."""

import re

from django.core.exceptions import RequestDataTooBig
from django.core.files.uploadhandler import FileUploadHandler
from django.http import JsonResponse

SIGNATURE_BYTES = 512 * 1024
REQUEST_BYTES = 2 * 1024 * 1024


class UploadLimitExceeded(Exception):
    pass


class SignatureUploadLimit(FileUploadHandler):
    def __init__(self, request):
        super().__init__(request)
        self.total = 0

    def new_file(self, *args, **kwargs):
        super().new_file(*args, **kwargs)
        self.file_bytes = 0

    def receive_data_chunk(self, raw_data, start):
        self.file_bytes += len(raw_data)
        self.total += len(raw_data)
        if self.file_bytes > SIGNATURE_BYTES or self.total > 2 * SIGNATURE_BYTES:
            raise UploadLimitExceeded
        return raw_data

    def file_complete(self, file_size):
        return None


class LimitedStream:
    def __init__(self, stream):
        self.stream = stream
        self.bytes_read = 0

    def _read(self, method, size):
        remaining = REQUEST_BYTES - self.bytes_read
        amount = min(size, remaining + 1) if size >= 0 else remaining + 1
        data = getattr(self.stream, method)(amount)
        self.bytes_read += len(data)
        if self.bytes_read > REQUEST_BYTES:
            raise UploadLimitExceeded
        return data

    def read(self, size=-1):
        return self._read("read", size)

    def readline(self, size=-1):
        return self._read("readline", size)


class SignatureRequestLimitMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method == "POST" and re.fullmatch(
            r"/uebergaben/[0-9a-fA-F-]{36}/bestaetigen/", request.path_info
        ):
            try:
                length = int(request.META.get("CONTENT_LENGTH") or 0)
                if length > REQUEST_BYTES:
                    raise UploadLimitExceeded
                request._stream = LimitedStream(request._stream)
                request.upload_handlers.insert(0, SignatureUploadLimit(request))
                # Parse here so limit exceptions are handled before CSRF processing.
                request.POST
            except (UploadLimitExceeded, RequestDataTooBig):
                # An interrupted file is not yet in the parser's completed-file list.
                for handler in request.upload_handlers:
                    upload = getattr(handler, "file", None)
                    if upload is not None:
                        upload.close()
                response = JsonResponse(
                    {"error": "Die Übertragung ist zu groß. Maximal 512 KiB je Unterschrift."},
                    status=413,
                )
                response["Cache-Control"] = "private, no-store"
                return response
        return self.get_response(request)
