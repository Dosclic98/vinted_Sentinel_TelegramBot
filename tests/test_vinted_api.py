import unittest
from unittest.mock import AsyncMock, Mock, patch

import requests

from api.vinted_api import VintedAPI


def response(status=200, items=None):
    result = Mock(status_code=status)
    result.json.return_value = {'items': items or []}
    if status >= 400:
        result.raise_for_status.side_effect = requests.HTTPError(
            f'HTTP {status}', response=result,
        )
    return result


class VintedAPITest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.session = requests.Session()
        self.session.get = Mock()
        session_patch = patch('api.vinted_api.requests.Session', return_value=self.session)
        session_patch.start()
        self.addCleanup(session_patch.stop)
        sleep_patch = patch('api.vinted_api.asyncio.sleep', new_callable=AsyncMock)
        self.sleep = sleep_patch.start()
        self.addCleanup(sleep_patch.stop)
        self.addCleanup(self.session.close)

    async def test_proxy_is_used_for_bootstrap_and_401_recovery(self):
        proxy = 'http://test-user-1:test-password@p.webshare.io:80'
        calls = []

        def get(url, **kwargs):
            calls.append(url)
            self.assertEqual(self.session.proxies, {'http': proxy, 'https': proxy})
            self.assertFalse(self.session.trust_env)
            if len(calls) == 2:
                return response(401)
            return response()

        self.session.get.side_effect = get
        api = VintedAPI(proxy_url=proxy)
        self.assertEqual(await api.search_products('cpu'), [])
        self.assertEqual(len(calls), 4)

    async def test_proxy_failure_is_redacted_and_never_falls_back(self):
        proxy = 'http://test-user-1:test%40password@p.webshare.io:80'
        self.session.get.side_effect = requests.exceptions.ProxyError(
            f'Cannot connect to {proxy}: test@password test-user-1'
        )
        with self.assertLogs('api.vinted_api', level='ERROR') as logs:
            api = VintedAPI(proxy_url=proxy)
            self.assertEqual(await api.search_products('cpu'), [])
        messages = '\n'.join(logs.output)
        for secret in ('test-user-1', 'test@password', 'test%40password'):
            self.assertNotIn(secret, messages)
        self.assertEqual(self.session.proxies['https'], proxy)
        self.assertFalse(self.session.trust_env)
        self.assertTrue(all(call.args[0].endswith('/catalog') for call in self.session.get.call_args_list))

    async def test_401_renews_cookies_before_retry(self):
        def get(url, **kwargs):
            if url.endswith('/catalog'):
                self.assertEqual(len(self.session.cookies), 0)
                self.session.cookies.set('access_token_web', 'fresh')
                return response()
            if self.session.cookies.get('access_token_web') == 'expired':
                return response(401)
            return response(items=[{'id': 1, 'photo': {'url': 'image.jpg'}, 'url': '/items/1-cpu'}])

        self.session.get.side_effect = get
        api = VintedAPI()
        self.session.cookies.set('access_token_web', 'expired')
        items = await api.search_products('Ryzen 5 5600')
        self.assertEqual(items[0]['image_url'], 'image.jpg')
        self.assertEqual(items[0]['url'], 'https://www.vinted.de/items/1-cpu')
        self.assertEqual(self.session.get.call_args.kwargs['headers']['Platform'], 'web')
        self.assertEqual(self.session.get.call_args.kwargs['headers']['Locale'], 'de-DE')
        self.assertEqual([call.args[0] for call in self.session.get.call_args_list], [
            api.base_url + '/catalog', api.base_url + '/web/gateway/svc-catalogue/items',
            api.base_url + '/catalog', api.base_url + '/web/gateway/svc-catalogue/items',
        ])
        for call in self.session.get.call_args_list:
            self.assertEqual(call.kwargs['timeout'], api.REQUEST_TIMEOUT)
        self.assertEqual(self.session.get.call_args.kwargs['params']['search_text'], 'Ryzen 5 5600')

    async def test_repeated_401_is_bounded(self):
        self.session.get.side_effect = [response(), response(401), response(), response(401), response(), response(401)]
        api = VintedAPI()
        self.assertEqual(await api.search_products('cpu'), [])
        self.assertEqual(self.session.get.call_count, 6)
        self.assertEqual(self.sleep.await_count, 2)
        self.assertFalse(api._session_ready)

    async def test_failed_bootstrap_does_not_query_catalog(self):
        self.session.get.side_effect = requests.Timeout('timeout')
        api = VintedAPI()
        self.assertEqual(await api.search_products('cpu'), [])
        self.assertEqual(self.session.get.call_count, 4)
        self.assertTrue(all(call.args[0].endswith('/catalog') for call in self.session.get.call_args_list))

    async def test_bootstrap_http_error_is_retried(self):
        self.session.get.side_effect = [response(503), response(), response(items=[{'id': 1}])]
        api = VintedAPI('.it')
        self.assertFalse(api._session_ready)
        self.assertEqual(len(await api.search_products('cpu')), 1)
        self.assertTrue(api._session_ready)

    async def test_403_stops_search(self):
        self.session.get.side_effect = [response(), response(403)]
        self.assertEqual(await VintedAPI().search_products('cpu'), [])
        self.assertEqual(self.session.get.call_count, 2)
        self.sleep.assert_not_awaited()

    async def test_photos_and_empty_results(self):
        self.session.get.side_effect = [response(), response(items=[
            {'id': 1, 'photos': [{'url': 'image.jpg'}]},
            {'id': 2, 'photos': []}, {'id': 3, 'photos': None}, {'id': 4},
        ]), response()]
        api = VintedAPI()
        items = await api.search_products('cpu')
        self.assertEqual([item['image_url'] for item in items], ['image.jpg', None, None, None])
        self.assertEqual(await api.search_products('missing'), [])

    async def test_transient_error_keeps_session(self):
        self.session.get.side_effect = [response(), response(503), response()]
        self.assertEqual(await VintedAPI().search_products('cpu'), [])
        self.assertEqual(self.session.get.call_count, 3)
        self.sleep.assert_awaited_once()


if __name__ == '__main__':
    unittest.main()
