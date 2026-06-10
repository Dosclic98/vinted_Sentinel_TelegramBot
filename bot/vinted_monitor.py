import asyncio
import html
import random
from datetime import datetime
from api.vinted_api import VintedAPI
from bot.telegram_bot import TelegramBot
from db.product_database import ProductDatabase
import logging

logger = logging.getLogger(__name__)

class VintedMonitor:
    def __init__(self, config):
        self.config = config
        self.db = ProductDatabase()
        self.bot = TelegramBot(config['token'], config['channel_id'])

    async def start_monitoring(self):
        while True:
            try:
                is_first_request = True
                shuffle_countries = self.config['countries'][:]
                random.shuffle(shuffle_countries)
                for country_code in shuffle_countries:
                    # Iniziamo una nuova sessione API per ciascun paese
                    self.api = VintedAPI(country_code)
                    
                    shuffle_search_terms = self.config['search_terms'][:]
                    random.shuffle(shuffle_search_terms)
                    for search_term in shuffle_search_terms:
                        if not is_first_request:
                            # Stochastic delay between requests (e.g., 2 to 6 seconds)
                            delay = random.uniform(2.0, 6.0)
                            logger.debug(f"Waiting {delay:.2f} seconds before next request...")
                            await asyncio.sleep(delay)
                        is_first_request = False
                        
                        logger.debug(f"Searching for term: {search_term} in {country_code}")
                        items = await self.api.search_products(search_term)
                        
                        for item in items:
                            try:
                                item_id = str(item.get('id'))
                                if not item_id or self.db.is_product_seen(item_id):
                                    continue
                                
                                self.db.add_product(item)
                                
                                # Creazione del messaggio da inviare a Telegram
                                message_text = self.create_message(item, country_code)
                                
                                # Invia il messaggio con immagine e link
                                self.bot.send_message(
                                    message_text,
                                    image_url=item.get('image_url'),  # Passa l'URL dell'immagine (solo la prima)
                                    product_url=item.get('url')           # Passa il link al prodotto
                                )
                                logger.info(f"New product found and posted: {item.get('title')}")
                            except Exception as e:
                                logger.error(f"Error processing item: {str(e)}")
                                continue

                # Add uncertainty to the refresh delay (±20% variation)
                base_delay = self.config['refresh_delay']
                stochastic_refresh = random.uniform(base_delay * 0.8, base_delay * 1.2)
                logger.debug(f"Waiting {stochastic_refresh:.2f} seconds before next full check loop...")
                await asyncio.sleep(stochastic_refresh)
                
            except Exception as e:
                logger.error(f"Error in monitoring loop: {str(e)}")
                await asyncio.sleep(30)
    
    def create_message(self, item, country_code):
        country_name = self.get_country_name_from_code(country_code)
        
        # Dettagli del prodotto
        title = item.get('title', 'No Title')
        
        # Escape html characters in title
        safe_title = html.escape(title)

        price_data = item.get('price', {})
        if isinstance(price_data, dict):
            amount = price_data.get('amount', 'N/A')
            currency = price_data.get('currency_code', 'EUR')
            # Mappa i codici valuta ai simboli
            currency_symbols = {'EUR': '€', 'GBP': '£', 'USD': '$', 'PLN': 'zł'}
            currency_symbol = currency_symbols.get(currency, currency)
            price_str = f"{amount} {currency_symbol}"
        else:
            price_str = f"{price_data} €" if price_data else "N/A"
        
        # Creazione del messaggio più compatto con HTML
        added_time = datetime.now().strftime("%d/%m/%Y - %H:%M")
        message_text = f"<b>{safe_title}</b>\n\n💸 <b>Price:</b> {price_str}\n📍 <b>Country:</b> {country_name}\n🕒 <b>Added:</b> {added_time}"
        
        return message_text

    def get_country_name_from_code(self, country_code):
        country_map = {
            ".de": "Germany",
            ".it": "Italy",
            ".fr": "France",
            ".es": "Spain",
            ".uk": "United Kingdom"
        }
        return country_map.get(country_code, "Unknown Country")
