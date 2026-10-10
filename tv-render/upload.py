"""Publish one fully rendered six-segment batch using GitHub Actions OIDC."""
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from urllib.parse import quote
from urllib.request import Request, urlopen
from urllib.error import HTTPError

SITE = 'https://lcn-market-television-hls.sturdyrain.chatgpt.site'
AUDIENCE = 'lcn-market-television-publisher'


def request(url, method='GET', data=None, headers=None):
    try:
        with urlopen(Request(url, data=data, method=method, headers=headers or {}), timeout=30) as response:
            return response.read()
    except HTTPError as error:
        body = error.read(512).decode('utf-8', errors='replace')
        raise RuntimeError(f'{method} {url.split("?")[0]} returned HTTP {error.code}: {body}') from None


def main():
    feed_path = Path(sys.argv[1])
    hls = Path(sys.argv[2])
    feed_bytes = feed_path.read_bytes()
    feed = json.loads(feed_bytes)
    if feed.get('mode') not in ('TEST', 'MARKET') or len(feed.get('snapshots', [])) != 6:
        raise ValueError('Only six-snapshot TEST or MARKET batches can be published')
    oidc_url = os.environ['ACTIONS_ID_TOKEN_REQUEST_URL']
    oidc_request_token = os.environ['ACTIONS_ID_TOKEN_REQUEST_TOKEN']
    separator = '&' if '?' in oidc_url else '?'
    token_response = request(oidc_url + separator + 'audience=' + quote(AUDIENCE),
                             headers={'Authorization': f'Bearer {oidc_request_token}'})
    publisher_token = json.loads(token_response)['value']
    source_hash = hashlib.sha256(feed_bytes).hexdigest()
    batch_id = f'{int(time.time() * 1000):013d}-{source_hash[:8]}'
    auth = {'Authorization': f'Bearer {publisher_token}'}
    for i in range(6):
        data = (hls / f'segment-{i:03d}.ts').read_bytes()
        if len(data) < 188 or len(data) % 188:
            raise ValueError(f'Segment {i} is not valid MPEG-TS packet data')
        request(f'{SITE}/api/market-batches/{batch_id}/{i}.ts', 'PUT', data,
                {**auth, 'Content-Type': 'video/mp2t'})
    payload = json.dumps({'mode': feed['mode'], 'sha256': source_hash}).encode()
    result = request(f'{SITE}/api/market-batches/{batch_id}/commit', 'POST', payload,
                     {**auth, 'Content-Type': 'application/json'})
    print(f'Published batch {batch_id}: {result.decode()}')
    print(f'PMMS URL: {SITE}/hls/lcn-market-test.m3u8')


if __name__ == '__main__':
    main()
