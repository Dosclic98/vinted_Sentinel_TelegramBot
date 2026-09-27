import json
import logging
import os
import stat
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict

logger = logging.getLogger(__name__)


class ProductDatabase:
    def __init__(self, file_path: str = "products.json"):
        self.file_path = Path(file_path)
        self.seen_products: Dict[str, Dict] = self._load_database()

    def _load_database(self) -> Dict[str, Dict]:
        try:
            with self.file_path.open('r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            return {}

    def _write_atomic(self, data: Dict[str, Dict]):
        temp_path = None
        try:
            # Same directory ensures os.replace stays on the same filesystem.
            with tempfile.NamedTemporaryFile(
                mode='w', encoding='utf-8', dir=self.file_path.parent,
                prefix=f'{self.file_path.name}.', suffix='.tmp', delete=False,
            ) as temp:
                temp_path = Path(temp.name)
                if self.file_path.exists():
                    os.fchmod(temp.fileno(), stat.S_IMODE(self.file_path.stat().st_mode))
                json.dump(data, temp, indent=2)
                temp.flush()
                os.fsync(temp.fileno())
            os.replace(temp_path, self.file_path)
            # Persist the rename as well as the contents on the Linux host.
            directory_fd = os.open(self.file_path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            if temp_path is not None and temp_path.exists():
                temp_path.unlink()

    def save_database(self):
        try:
            self._write_atomic(self.seen_products)
        except Exception as e:
            logger.error(f"Error saving database: {str(e)}")

    def is_product_seen(self, product_id: str) -> bool:
        return product_id in self.seen_products

    def add_product(self, product):
        try:
            self.seen_products[str(product["id"])] = {
                "data": product,
                "timestamp": datetime.now().isoformat()
            }
            self.save_database()
        except Exception as e:
            logger.error(f"Error adding product to database: {str(e)}")
