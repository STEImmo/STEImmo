"""Recover private PDF and signature files after a failed archive transaction."""

import logging

from django.core.files.storage import default_storage
from django.db import DatabaseError

from .models import HandoverArchiveCleanup, Protokoll, ProtokollUnterschrift

logger = logging.getLogger(__name__)


def save_archive_file(storage, name, content, stored_paths):
    # Track an unused candidate before writing: storage can write and then fail
    # without returning a name. A backend may also return a different name.
    name = storage.get_available_name(name)
    stored_paths.append(name)
    saved_name = storage.save(name, content)
    if saved_name != name:
        stored_paths.append(saved_name)
    return saved_name


def cleanup_archive_file(cleanup):
    try:
        if (
            Protokoll.objects.filter(dokument_pfad=cleanup.storage_name).exists()
            or ProtokollUnterschrift.objects.filter(datei=cleanup.storage_name).exists()
        ):
            raise ValueError("Archive file is still referenced.")
        default_storage.delete(cleanup.storage_name)
        cleanup.delete()
        return True
    except Exception as error:
        logger.error("Could not clean up an archive file (%s).", type(error).__name__)
        return False


def cleanup_archive_files(paths):
    # Call only after the archive transaction has rolled back. Persist before
    # deletion so storage outages and interruptions leave a retryable job.
    for name in dict.fromkeys(paths):
        try:
            cleanup, _created = HandoverArchiveCleanup.objects.get_or_create(storage_name=name)
        except DatabaseError as error:
            logger.error("Could not queue archive cleanup (%s).", type(error).__name__)
            continue
        cleanup_archive_file(cleanup)
