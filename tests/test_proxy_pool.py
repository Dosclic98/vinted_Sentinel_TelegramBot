import unittest
from urllib.parse import unquote, urlsplit

from api.proxy_pool import WebshareProxyPool


class ProxyPoolTest(unittest.TestCase):
    def test_disabled_by_default_even_with_saved_credentials(self):
        pool = WebshareProxyPool({'proxy_username': 'user', 'proxy_password': 'password'})
        self.assertIsNone(pool.next_proxy())

    def test_cycles_over_all_ten_proxies(self):
        pool = WebshareProxyPool({
            'proxy_enabled': True, 'proxy_username': 'user', 'proxy_password': 'password',
        })
        urls = [pool.next_proxy() for _ in range(11)]
        self.assertEqual(len(set(urls[:10])), 10)
        self.assertEqual(urls[0], urls[10])
        for index, url in enumerate(urls[:10], 1):
            parsed = urlsplit(url)
            self.assertEqual(parsed.hostname, 'p.webshare.io')
            self.assertEqual(parsed.port, 80)
            self.assertEqual(parsed.username, f'user-{index}')

    def test_credentials_are_url_encoded(self):
        pool = WebshareProxyPool({
            'proxy_enabled': True, 'proxy_username': 'user@example',
            'proxy_password': 'p@ss:/?#%', 'proxy_count': 1,
        })
        parsed = urlsplit(pool.next_proxy())
        self.assertEqual(unquote(parsed.username), 'user@example-1')
        self.assertEqual(unquote(parsed.password), 'p@ss:/?#%')
        self.assertEqual(parsed.hostname, 'p.webshare.io')

    def test_invalid_configuration_does_not_fall_back_to_direct(self):
        configs = [
            {}, {'proxy_username': 'user'},
            {'proxy_username': 'user', 'proxy_password': 'password', 'proxy_count': 0},
            {'proxy_username': 'user', 'proxy_password': 'password', 'proxy_count': '10'},
        ]
        for config in configs:
            with self.subTest(config_keys=list(config)):
                with self.assertRaises(ValueError):
                    WebshareProxyPool({**config, 'proxy_enabled': True})
