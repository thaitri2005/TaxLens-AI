from taxlens.storage.azure_blob import AzureBlobStorage


def test_azure_storage_routes_normalized_keys_to_normalized_container() -> None:
    storage = object.__new__(AzureBlobStorage)
    raw_container = object()
    normalized_container = object()
    storage._raw_container = raw_container
    storage._normalized_container = normalized_container

    assert storage._container_for_key("raw-documents/example.pdf") is raw_container
    assert storage._container_for_key("normalized-text/example.txt") is normalized_container
    assert storage._blob_name("raw-documents/example.pdf") == "example.pdf"
    assert storage._blob_name("normalized-text/example.txt") == "example.txt"
