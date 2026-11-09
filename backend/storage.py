import os
import time
from urllib.parse import quote

import requests


class StorageNotConfigured(RuntimeError):
    """Storage has not been configured or the requested source is not allowed."""


class StorageProvider:
    def create_copy(self, *, source_key: str, copy_name: str, requested_by: str) -> dict:
        raise NotImplementedError


class DisabledStorageProvider(StorageProvider):
    def create_copy(self, *, source_key: str, copy_name: str, requested_by: str) -> dict:
        raise StorageNotConfigured


class MicrosoftGraphStorageProvider(StorageProvider):
    """Microsoft Graph app-only adapter for a single approved SharePoint/OneDrive library.

    Configure a confidential Entra ID app with least-privilege application permissions
    (prefer Sites.Selected with an explicit site grant), tenant admin consent, source
    drive ID, and destination drive/folder IDs. `source_key` is an item ID, not a URL.
    """
    GRAPH = "https://graph.microsoft.com/v1.0"

    def __init__(self):
        self.tenant = os.getenv("MS_TENANT_ID", "")
        self.client_id = os.getenv("MS_CLIENT_ID", "")
        self.client_secret = os.getenv("MS_CLIENT_SECRET", "")
        self.source_drive = os.getenv("MS_SOURCE_DRIVE_ID", "")
        self.destination_drive = os.getenv("MS_DESTINATION_DRIVE_ID", "")
        self.destination_folder = os.getenv("MS_DESTINATION_FOLDER_ID", "")
        if not all((self.tenant, self.client_id, self.client_secret, self.source_drive, self.destination_drive, self.destination_folder)):
            raise StorageNotConfigured
        self.timeout = 20

    def _token(self):
        response = requests.post(
            f"https://login.microsoftonline.com/{quote(self.tenant, safe='')}/oauth2/v2.0/token",
            data={"client_id": self.client_id, "client_secret": self.client_secret,
                  "scope": "https://graph.microsoft.com/.default", "grant_type": "client_credentials"},
            timeout=self.timeout,
        )
        if response.status_code != 200:
            raise RuntimeError("Graph token request failed")
        return response.json()["access_token"]

    def create_copy(self, *, source_key: str, copy_name: str, requested_by: str) -> dict:
        token = self._token()
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        source_url = f"{self.GRAPH}/drives/{quote(self.source_drive, safe='')}/items/{quote(source_key, safe='')}/copy"
        response = requests.post(source_url, headers=headers,
            json={"name": copy_name, "parentReference": {"driveId": self.destination_drive, "id": self.destination_folder}},
            timeout=self.timeout)
        if response.status_code not in (200, 202):
            raise RuntimeError("Graph copy request failed")
        if response.status_code == 200:
            item = response.json()
        else:
            monitor_url = response.headers.get("Location")
            if not monitor_url or not monitor_url.startswith("https://graph.microsoft.com/"):
                raise RuntimeError("Graph returned an invalid copy monitor URL")
            deadline = time.monotonic() + 60
            item = None
            while time.monotonic() < deadline:
                time.sleep(min(int(response.headers.get("Retry-After", "2")), 5))
                response = requests.get(monitor_url, headers={"Authorization": f"Bearer {token}"}, timeout=self.timeout, allow_redirects=False)
                if response.status_code == 303:
                    location = response.headers.get("Location", "")
                    if not location.startswith(self.GRAPH + "/drives/"):
                        raise RuntimeError("Graph returned an invalid copied item location")
                    response = requests.get(location, headers={"Authorization": f"Bearer {token}"}, timeout=self.timeout)
                    if response.status_code != 200:
                        raise RuntimeError("Unable to retrieve copied item")
                    item = response.json()
                    break
                if response.status_code == 200:
                    body = response.json()
                    if body.get("status") == "completed" and body.get("resourceId"):
                        item_id = body["resourceId"]
                        item_url = f"{self.GRAPH}/drives/{quote(self.destination_drive, safe='')}/items/{quote(item_id, safe='')}"
                        response = requests.get(item_url, headers={"Authorization": f"Bearer {token}"}, timeout=self.timeout)
                        if response.status_code == 200:
                            item = response.json()
                            break
                    if body.get("status") in ("failed", "delete"):
                        raise RuntimeError("Graph copy operation failed")
                elif response.status_code not in (202, 204):
                    raise RuntimeError("Graph copy polling failed")
            if item is None:
                raise RuntimeError("Graph copy operation timed out")
        web_url = item.get("webUrl")
        item_id = item.get("id")
        if not web_url or not web_url.startswith("https://") or not item_id:
            raise RuntimeError("Graph returned incomplete copy metadata")
        return {"destination_id": item_id, "url": web_url}


def get_storage_provider() -> StorageProvider:
    backend = os.getenv("STORAGE_BACKEND", "disabled").lower()
    if backend == "microsoft_graph":
        return MicrosoftGraphStorageProvider()
    if backend == "disabled":
        return DisabledStorageProvider()
    raise StorageNotConfigured
