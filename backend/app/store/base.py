import threading


class Store:
    """Generic document store. One interface, two backends (SQLite, Supabase).

    kinds: brand, brand_version, product, product_version, suggestion, submission, asset
    """

    lock = threading.RLock()

    def list(self, kind: str) -> list: ...
    def get(self, kind: str, id: str) -> dict | None: ...
    def put(self, kind: str, id: str, data: dict) -> None: ...
    def delete(self, kind: str, id: str) -> None: ...
