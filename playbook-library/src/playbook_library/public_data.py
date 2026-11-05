# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""Downloads of the datarecord stores in the public `manta-public-test-data` bucket."""

from pathlib import Path

try:
    from google.cloud.storage import Client, transfer_manager
except ImportError as err:
    raise ImportError(
        "Downloading public test data needs google-cloud-storage: "
        "install playbook-library[public-data]."
    ) from err

PUBLIC_BUCKET = "manta-public-test-data"


def download_public_store(name: str, store_dir: Path) -> Path:
    """Download the store `name` of the public test data bucket into `store_dir`."""
    prefix = f"{name}/"
    bucket = Client.create_anonymous_client().bucket(PUBLIC_BUCKET)
    names = [blob.name.removeprefix(prefix) for blob in bucket.list_blobs(prefix=prefix)]
    transfer_manager.download_many_to_path(
        bucket,
        names,
        destination_directory=store_dir,
        blob_name_prefix=prefix,
        create_directories=True,
        raise_exception=True,
        worker_type=transfer_manager.THREAD,
    )
    return store_dir
