import json
import logging
import asyncio
from pathlib import Path
from bot.vinted_monitor import VintedMonitor

logging.basicConfig(level=logging.DEBUG)

def main():
    try:
        config_path = Path(__file__).resolve().parent / 'config' / 'config.prod.json'
        with config_path.open(encoding='utf-8') as f:
            config = json.load(f)
        
        monitor = VintedMonitor(config)
        logging.info("Starting Vinted Monitor... Press Ctrl+C to stop.")
        asyncio.run(monitor.start_monitoring())
        
    except KeyboardInterrupt:
        logging.info("Received exit signal (Ctrl+C). Shutting down gracefully...")
    except Exception as e:
        logging.error(f"Error starting the bot: {str(e)}")

if __name__ == "__main__":
    main()
