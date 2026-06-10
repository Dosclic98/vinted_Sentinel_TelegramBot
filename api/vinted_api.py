import requests
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

class VintedAPI:
    def __init__(self, country_code=".de"):
        self.country_code = country_code
        self.session = requests.Session()
        self.token: Optional[str] = None
        self.base_url = f"https://www.vinted{country_code}"  # URL dinamico in base al paese
        self._fetch_cookies()
        
    def _fetch_cookies(self):
        try:
            self.session.get(self.base_url, headers=self._get_headers())
        except Exception as e:
            logger.error(f"Failed to fetch cookies for {self.base_url}: {str(e)}")
    
    def _get_headers(self, with_auth: bool = False) -> Dict:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'en-US,en;q=0.9',
        }
        
        if with_auth and self.token:
            headers['authorization'] = f'Bearer {self.token}'
            
        return headers
    
    async def search_products(self, search_text: str) -> List[Dict]:
        import asyncio
        import random
        
        max_retries = 3
        base_delay = 2.0
        
        for attempt in range(max_retries):
            try:
                params = {
                    'page': '1',
                    'per_page': '10',
                    'search_text': search_text,
                    'order': 'newest_first',
                }
                
                response = self.session.get(
                    f'{self.base_url}/api/v2/catalog/items',
                    params=params,
                    headers=self._get_headers(with_auth=True)
                )
                response.raise_for_status()
                data = response.json()
                
                # Estrazione dell'URL dell'immagine, se disponibile
                items = []
                for item in data.get('items', []):
                    image_url = item.get('photos', [{}])[0].get('url', None)
                    item['image_url'] = image_url  # Aggiungi l'URL dell'immagine all'item
                    items.append(item)
                
                return items
            except Exception as e:
                logger.error(f"Failed to search products (attempt {attempt + 1}/{max_retries}): {str(e)}")
                if attempt < max_retries - 1:
                    sleep_time = (base_delay ** attempt) + random.uniform(0.1, 1.0)
                    logger.info(f"Retrying in {sleep_time:.2f} seconds...")
                    await asyncio.sleep(sleep_time)
                else:
                    return []
