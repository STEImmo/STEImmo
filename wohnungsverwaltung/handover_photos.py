"""Recover photo files from failed uploads and committed photo removals."""

import logging
from contextlib import contextmanager

from django.core.files.storage import Storage
from django.db import DatabaseError, transaction

from .models import HandoverPhotoCleanup, RaumMerkmalFoto, calculate_photo_checksum

logger = logging.getLogger(__name__)
PHOTO_SAVE_ERROR = (
    "Die Fotos konnten nicht sicher gespeichert werden. Bitte wählen Sie die Fotos "
    "erneut aus und versuchen Sie es noch einmal."
)
PHOTO_READ_ERROR = (
    "Ein vorhandenes Foto konnte nicht gelesen werden. Die neuen Fotos wurden nicht "
    "gespeichert. Bitte versuchen Sie es später erneut."
)


class HandoverPhotoStorageError(Exception):
    pass


class HandoverPhotoReadError(Exception):
    pass


def existing_photo_checksums(photos) -> set[str]:
    checksums = set()
    for photo in photos:
        if photo.inhalt_hash_sha256:
            checksums.add(photo.inhalt_hash_sha256)
            continue
        try:
            with photo.datei.open("rb") as photo_file:
                checksums.add(calculate_photo_checksum(photo_file))
        except (OSError, ValueError) as error:
            raise HandoverPhotoReadError from error
    return checksums


def _cleanup_removed_photo_file(storage: Storage, name: str, cleanup_id) -> None:
    try:
        if RaumMerkmalFoto.objects.filter(datei=name).exists():
            raise ValueError("Photo is still referenced.")
        storage.delete(name)
        HandoverPhotoCleanup.objects.filter(pk=cleanup_id).delete()
    except Exception as error:
        # The committed job survives a storage failure or process interruption.
        logger.error("Could not clean up a removed photo file (%s).", type(error).__name__)


def delete_handover_photo(photo: RaumMerkmalFoto) -> None:
    with transaction.atomic():
        storage = photo.datei.storage
        name = photo.datei.name
        cleanup = None
        if name:
            cleanup, _created = HandoverPhotoCleanup.objects.get_or_create(storage_name=name)
        photo.delete()
        if cleanup is not None:
            transaction.on_commit(lambda: _cleanup_removed_photo_file(storage, name, cleanup.pk))


def save_handover_photo(photo: RaumMerkmalFoto, stored_files: list[tuple[Storage, str]]) -> None:
    field = photo._meta.get_field("datei")
    storage = field.storage
    upload = photo.datei.file
    try:
        name = field.generate_filename(photo, upload.name)
        while storage.exists(name):
            name = field.generate_filename(photo, upload.name)
        # A backend can fail after writing without returning a name. The opaque
        # new candidate must also be tracked, before the first write.
        stored_files.append((storage, name))
        saved_name = storage.save(name, upload, max_length=field.max_length)
    except Exception as error:
        raise HandoverPhotoStorageError from error
    if saved_name != name:
        stored_files.append((storage, saved_name))
    photo.datei = saved_name
    photo.save()


def _cleanup_new_photo_files(stored_files: list[tuple[Storage, str]]) -> None:
    seen = set()
    for storage, name in reversed(stored_files):
        if name in seen:
            continue
        seen.add(name)
        cleanup = None
        try:
            cleanup, _created = HandoverPhotoCleanup.objects.get_or_create(storage_name=name)
        except DatabaseError as error:
            logger.error("Could not queue photo cleanup (%s).", type(error).__name__)
        try:
            storage.delete(name)
            if cleanup is not None:
                cleanup.delete()
        except Exception as error:
            logger.error("Could not clean up a new photo file (%s).", type(error).__name__)


@contextmanager
def handover_photo_upload():
    stored_files = []
    try:
        with transaction.atomic():
            yield stored_files
    except Exception:
        # The savepoint has rolled back before cleanup jobs are persisted.
        _cleanup_new_photo_files(stored_files)
        raise
