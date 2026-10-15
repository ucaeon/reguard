import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from pipelines.collectors.recall_images import discover_images, official_image_url


class ImageTests(unittest.TestCase):
    def setUp(self):
        self.row = dict(recallUid='123', certNum='CB123', recallModelName='허니', recallCmpnyName='리틀아이')

    def client(self, html, image=b'\x89PNG\r\n\x1a\nexample'):
        self.calls = []
        def respond(request):
            self.calls.append(request)
            if request.url.host == 'www.safetykorea.kr':
                return httpx.Response(200, text=html)
            self.assertEqual(request.headers['Range'], 'bytes=0-31')
            return httpx.Response(206, content=image)
        return httpx.Client(transport=httpx.MockTransport(respond))

    def test_verified_url_without_files(self):
        html = 'CB123 허니 리틀아이<img alt="전체사진" src="http://office.safetykorea.kr/fileData/사진.png">'
        with self.client(html) as client, patch.object(Path, 'write_bytes', side_effect=AssertionError('no files')):
            result = discover_images(self.row, client)
        self.assertEqual(result['status'], 'success')
        self.assertTrue(result['images'][0]['imageUrl'].startswith('https://office.safetykorea.kr/'))
        self.assertNotIn('archiveFile', result['images'][0])
        self.assertEqual(len(self.calls), 2)

    def test_wrong_identity_never_requests_image(self):
        with self.client('CB999 허니 리틀아이') as client:
            result = discover_images(self.row, client)
        self.assertEqual(result['status'], 'identity_unconfirmed')
        self.assertEqual(len(self.calls), 1)

    def test_untrusted_hosts_rejected(self):
        for url in ['http://localhost/fileData/x.png', 'https://office.safetykorea.kr.evil.com/fileData/x',
                    'https://x@office.safetykorea.kr/fileData/x', 'https://office.safetykorea.kr:8888/fileData/x']:
            self.assertIsNone(official_image_url(url))

    def test_non_image_rejected(self):
        with self.client('CB123 허니 리틀아이<img alt="전체사진" src="https://office.safetykorea.kr/fileData/x">', b'<html>error</html>') as client:
            self.assertEqual(discover_images(self.row, client)['status'], 'not_found')

    def test_server_error_retries_but_missing_notice_is_not_found(self):
        for code, status in [(503, 'retry'), (429, 'retry'), (404, 'not_found')]:
            with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(code))) as client:
                self.assertEqual(discover_images(self.row, client)['status'], status)

    def test_redirect_is_not_followed(self):
        calls = []
        def respond(request):
            calls.append(request)
            return httpx.Response(302, headers={'location': 'http://localhost/secret'})
        with httpx.Client(transport=httpx.MockTransport(respond)) as client:
            self.assertEqual(discover_images(self.row, client)['status'], 'retry')
        self.assertEqual(len(calls), 1)

    def test_timeout_is_retryable(self):
        def respond(request):
            raise httpx.ReadTimeout('timeout', request=request)
        with httpx.Client(transport=httpx.MockTransport(respond)) as client:
            self.assertEqual(discover_images(self.row, client)['status'], 'retry')
