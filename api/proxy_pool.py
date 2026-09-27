"""Webshare backbone proxies, selected once per Vinted session."""
from itertools import cycle
from urllib.parse import quote


class WebshareProxyPool:
    def __init__(self, config):
        self._proxies = None
        if not config.get('proxy_enabled', False):
            return
        username = config.get('proxy_username')
        password = config.get('proxy_password')
        if not isinstance(username, str) or not username or not isinstance(password, str) or not password:
            raise ValueError('Webshare requires proxy_username and proxy_password')
        count = config.get('proxy_count', 10)
        if type(count) is not int or not 1 <= count <= 1000:
            raise ValueError('proxy_count must be an integer between 1 and 1000')
        # Use the base username from Direct Connection. Backbone selects an
        # individual proxy with a numbered suffix; do not use "-rotate" here.
        self._proxies = cycle(
            'http://{}:{}@p.webshare.io:80'.format(
                quote(f'{username}-{index}', safe=''), quote(password, safe=''),
            )
            for index in range(1, count + 1)
        )

    def next_proxy(self):
        return next(self._proxies) if self._proxies is not None else None
