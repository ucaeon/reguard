"""Discover verified official image URLs. Never write image files to disk."""
import hashlib
import json
import re
from html.parser import HTMLParser
from urllib.parse import quote, urlsplit

import httpx


class Notice(HTMLParser):
    def __init__(self):
        super().__init__()
        self.images = []
        self.text = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'img' and attrs.get('alt') in ('전체사진', '부분사진'):
            self.images.append(attrs.get('src', ''))

    def handle_data(self, data):
        self.text.append(data)


def identity(row):
    return [str(row.get('recallUid') or ''), str(row.get('certNum') or ''),
            str(row.get('recallModelName') or ''),
            str(row.get('recallCmpnyName') or row.get('makerName') or '')]


def fingerprint(row):
    return hashlib.sha256(json.dumps(identity(row), ensure_ascii=False).encode()).hexdigest()


def official_image_url(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = urlsplit(value)
        if (parsed.scheme not in ('http', 'https') or parsed.hostname != 'office.safetykorea.kr'
                or parsed.username or parsed.password or parsed.port not in (None, 80, 443)
                or not parsed.path.startswith('/fileData/')):
            return None
        return 'https://office.safetykorea.kr' + quote(parsed.path, safe='/%')
    except ValueError:
        return None


def discover_images(row, client):
    uid, *identifiers = identity(row)
    if not uid.isdigit():
        return {'status': 'identity_unconfirmed', 'images': [], 'error': 'INVALID_RECALL_UID'}
    notice_url = f'https://www.safetykorea.kr/recall/ajax/recallBoard?recallUid={uid}'
    try:
        response = client.get(notice_url, timeout=15, follow_redirects=False)
        response.raise_for_status()
        notice = Notice()
        notice.feed(response.text)
        text = re.sub(r'\s+', '', ''.join(notice.text))
        identifiers = [re.sub(r'\s+', '', value) for value in identifiers if value]
        if len(identifiers) < 2 or not all(value in text for value in identifiers):
            return {'status': 'identity_unconfirmed', 'images': [], 'error': 'IDENTITY_NOT_CONFIRMED'}
        images = []
        for source in notice.images[:2]:
            url = official_image_url(source)
            if not url or any(item['imageUrl'] == url for item in images):
                continue
            # Read only a small signature in memory, even if Range is ignored.
            # Redirects are rejected, so an official URL cannot redirect to an arbitrary host.
            with client.stream('GET', url, headers={'Range': 'bytes=0-31'},
                               timeout=15, follow_redirects=False) as image:
                image.raise_for_status()
                signature = next(image.iter_bytes(chunk_size=32), b'')
            if signature.startswith(b'\x89PNG\r\n\x1a\n'):
                mime = 'image/png'
            elif signature.startswith(b'\xff\xd8\xff'):
                mime = 'image/jpeg'
            elif signature.startswith((b'GIF87a', b'GIF89a')):
                mime = 'image/gif'
            elif signature.startswith(b'RIFF') and signature[8:12] == b'WEBP':
                mime = 'image/webp'
            else:
                continue
            images.append({'imageUrl': url, 'sourceUrl': notice_url, 'contentType': mime})
        return {'status': 'success' if images else 'not_found', 'images': images, 'error': None}
    except httpx.HTTPStatusError as error:
        code = error.response.status_code
        return {'status': 'not_found' if code in (404, 410) else 'retry',
                'images': [], 'error': f'HTTP_{code}'}
    except httpx.RequestError as error:
        return {'status': 'retry', 'images': [], 'error': type(error).__name__}
