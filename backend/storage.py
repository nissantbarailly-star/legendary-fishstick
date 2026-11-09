class StorageNotConfigured(RuntimeError):
    """Raised until an approved organization storage adapter is installed."""


class StorageProvider:
    """Storage adapter contract; implement this using the company's approved provider.

    Implementations must resolve opaque source keys server-side, ensure the caller is
    permitted to create a copy in an approved destination, and return the new copy's
    URL and provider ID. Never return or expose the canonical source URL to the client.
    """

    def create_copy(self, *, source_key: str, copy_name: str, requested_by: str) -> dict:
        raise NotImplementedError


class DisabledStorageProvider(StorageProvider):
    def create_copy(self, *, source_key: str, copy_name: str, requested_by: str) -> dict:
        raise StorageNotConfigured


def get_storage_provider() -> StorageProvider:
    # Intentionally fail closed. Add a provider-specific implementation only after
    # choosing the company storage system and configuring least-privilege credentials.
    return DisabledStorageProvider()
