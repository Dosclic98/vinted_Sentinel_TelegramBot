import asyncio
import logging
import random
from typing import Dict, List
from urllib.parse import urljoin

import requests

logger = logging.getLogger(__name__)


class VintedAPI:
    REQUEST_TIMEOUT = (5, 20)
    CATALOG_PATH = '/web/gateway/svc-catalogue/items'

    def __init__(self, country_code=".de"):
        self.country_code = country_code
        domain = '.co.uk' if country_code == '.uk' else country_code
        self.locale = {
            '.de': 'de-DE', '.it': 'it-IT', '.fr': 'fr-FR',
            '.es': 'es-ES', '.uk': 'en-GB', '.co.uk': 'en-GB',
        }.get(country_code, 'en-US')
        self.session = requests.Session()
        self.base_url = f"https://www.vinted{domain}"
        self._session_ready = self._fetch_cookies()

    def _fetch_cookies(self) -> bool:
        # Discard expired authentication before requesting a new anonymous session.
        self._session_ready = False
        self.session.cookies.clear()
        headers = self._get_headers()
        headers['Accept'] = 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
        try:
            response = self.session.get(
                f'{self.base_url}/catalog',
                headers=headers,
                timeout=self.REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            self._session_ready = True
            return True
        except requests.RequestException as exc:
            logger.error("Failed to fetch cookies for %s: %s", self.base_url, exc)
            return False

    def _get_headers(self) -> Dict:
        # requests.Session sends the authentication cookies with their correct scope.
        return {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': f'{self.base_url}/catalog',
            'Platform': 'web',
            'Locale': self.locale,
            'X-Next-App': 'marketplace-web',
        }

    async def search_products(self, search_text: str) -> List[Dict]:
        max_retries = 3
        base_delay = 2.0
        params = {
            'page': '1',
            'per_page': '10',
            'search_text': search_text,
            'order': 'newest_first',
        }

        for attempt in range(max_retries):
            try:
                if not self._session_ready and not self._fetch_cookies():
                    raise requests.RequestException('Could not initialize Vinted session')

                response = self.session.get(
                    f'{self.base_url}{self.CATALOG_PATH}',
                    params=params,
                    headers=self._get_headers(),
                    timeout=self.REQUEST_TIMEOUT,
                )
                if response.status_code == 401:
                    self._session_ready = False
                    logger.warning("Vinted rejected the session for %s; cookies will be renewed", self.base_url)
                elif response.status_code == 403:
                    logger.error("Vinted denied catalog access for %s (403); stopping this search", self.base_url)
                    return []
                response.raise_for_status()
                data = response.json()

                items = []
                for item in data.get('items', []):
                    # Catalog responses can contain a single photo or a photos list.
                    photo = item.get('photo') or next(iter(item.get('photos') or []), {})
                    item['image_url'] = photo.get('url')
                    if item.get('url'):
                        item['url'] = urljoin(self.base_url, item['url'])
                    items.append(item)
                return items
            except (requests.RequestException, ValueError) as exc:
                logger.error("Failed to search products (attempt %s/%s): %s", attempt + 1, max_retries, exc)
                if attempt < max_retries - 1:
                    sleep_time = (base_delay ** attempt) + random.uniform(0.1, 1.0)
                    logger.info("Retrying in %.2f seconds...", sleep_time)
                    await asyncio.sleep(sleep_time)
        return []
