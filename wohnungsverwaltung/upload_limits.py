"""Early request and streaming file limits for proof and apartment photo uploads."""

from django.conf import settings
from django.core.files.uploadhandler import FileUploadHandler, StopUpload
from django.http import HttpRequest, HttpResponse


def _is_main_application_submission(request: HttpRequest) -> bool:
    path_parts = request.path_info.strip("/").split("/")
    return (
        request.method == "POST"
        and len(path_parts) == 4
        and path_parts[0:2] == ["uebergaben", "bewerbung"]
        and path_parts[3] == "main"
    )


def upload_too_large_response(message: str) -> HttpResponse:
    response = HttpResponse(message, status=413, content_type="text/plain; charset=utf-8")
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "private, no-store"
    return response


def _mib(value: int) -> str:
    return f"{value / (1024 * 1024):g} MiB"


class MainApplicationProofUploadHandler(FileUploadHandler):
    """Stop an oversized proof while Django is still parsing the request body."""

    def __init__(self, request: HttpRequest):
        super().__init__(request)
        self.total_file_size = 0
        self.current_file_size = 0

    def new_file(
        self,
        field_name: str,
        file_name: str,
        content_type: str,
        content_length: int | None,
        charset: str | None,
        content_type_extra: dict | None = None,
    ) -> None:
        super().new_file(
            field_name,
            file_name,
            content_type,
            content_length,
            charset,
            content_type_extra,
        )
        self.current_file_size = 0

    def receive_data_chunk(self, raw_data: bytes, start: int) -> bytes:
        chunk_size = len(raw_data)
        self.current_file_size += chunk_size
        self.total_file_size += chunk_size

        if self.current_file_size > settings.MAIN_APPLICATION_PROOF_MAX_SIZE:
            self.request._main_application_upload_error = (
                "Eine Datei überschreitet das Limit von "
                f"{_mib(settings.MAIN_APPLICATION_PROOF_MAX_SIZE)}."
            )
            raise StopUpload(connection_reset=False)

        if self.total_file_size > settings.MAIN_APPLICATION_MAX_REQUEST_SIZE:
            self.request._main_application_upload_error = (
                "Die Dateigröße überschreitet das Gesamtlimit von "
                f"{_mib(settings.MAIN_APPLICATION_MAX_REQUEST_SIZE)}."
            )
            raise StopUpload(connection_reset=False)

        return raw_data

    def file_complete(self, file_size: int):
        return None


class MainApplicationUploadLimitMiddleware:
    """Reject declared oversized requests before CSRF or form parsing starts."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        path_parts = request.path_info.strip("/").split("/")
        if (
            request.method == "POST"
            and len(path_parts) == 4
            and path_parts[:2] == ["verwaltung", "wohnungen"]
            and path_parts[3] == "fotos"
        ):
            # Allow bounded multipart headers and caption data around one photo.
            maximum = settings.APARTMENT_PHOTO_MAX_SIZE + 64 * 1024
            try:
                content_length = int(request.META.get("CONTENT_LENGTH") or 0)
            except (TypeError, ValueError):
                content_length = 0
            if content_length > maximum:
                return upload_too_large_response("Der Wohnungsfoto-Upload ist zu groß.")
            request.upload_handlers.insert(0, ApartmentPhotoUploadHandler(request))
            response = self.get_response(request)
            error = getattr(request, "_apartment_photo_upload_error", None)
            return upload_too_large_response(error) if error else response

        if not _is_main_application_submission(request):
            return self.get_response(request)

        try:
            content_length = int(request.META.get("CONTENT_LENGTH") or 0)
        except (TypeError, ValueError):
            content_length = 0

        if content_length > settings.MAIN_APPLICATION_MAX_REQUEST_SIZE:
            return upload_too_large_response(
                "Die Gesamtgröße des Uploads überschreitet das Limit von "
                f"{_mib(settings.MAIN_APPLICATION_MAX_REQUEST_SIZE)}."
            )

        request.upload_handlers.insert(0, MainApplicationProofUploadHandler(request))
        response = self.get_response(request)
        upload_error = getattr(request, "_main_application_upload_error", None)
        if upload_error:
            return upload_too_large_response(upload_error)
        return response


class ApartmentPhotoUploadHandler(FileUploadHandler):
    """Bound photo bytes before Django's memory and temporary-file handlers."""

    def __init__(self, request: HttpRequest):
        super().__init__(request)
        self.total_file_size = 0

    def receive_data_chunk(self, raw_data: bytes, start: int) -> bytes:
        self.total_file_size += len(raw_data)
        if self.total_file_size > settings.APARTMENT_PHOTO_MAX_SIZE:
            self.request._apartment_photo_upload_error = (
                "Die Datei ist zu groß. Erlaubt sind höchstens "
                f"{_mib(settings.APARTMENT_PHOTO_MAX_SIZE)}."
            )
            raise StopUpload(connection_reset=False)
        return raw_data

    def file_complete(self, file_size: int):
        return None
