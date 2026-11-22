from fastapi import FastAPI
from fastapi.responses import Response
from fastapi.testclient import TestClient
from starlette.middleware.gzip import GZipMiddleware

from app.main import SPAStaticFiles, add_cache_headers, app


def test_production_registers_compression():
    assert any(m.cls is GZipMiddleware for m in app.user_middleware)


def test_frozen_archive_map_cache_survives_api_no_store_policy():
    site = FastAPI()
    site.middleware('http')(add_cache_headers)
    @site.get('/api/v1/campaign/archives/1/map.svg')
    def frozen_map():
        return Response('<svg/>', media_type='image/svg+xml', headers={'Cache-Control': 'public, max-age=31536000, immutable'})
    @site.get('/api/v1/private')
    def private():
        return {'private': True}
    client = TestClient(site)
    assert 'immutable' in client.get('/api/v1/campaign/archives/1/map.svg').headers['cache-control']
    assert 'no-store' in client.get('/api/v1/private').headers['cache-control']


def test_static_delivery_compresses_and_caches_hashes_without_hiding_missing_modules(tmp_path):
    assets = tmp_path / 'assets'
    assets.mkdir()
    (tmp_path / 'index.html').write_text('<html><body>SPA</body></html>')
    (assets / 'bundle-AbCd1234.js').write_text('const repeated = "abcdefgh";\n' * 10000)
    site = FastAPI()
    site.middleware('http')(add_cache_headers)
    site.mount('/', SPAStaticFiles(directory=str(tmp_path), html=True))
    site.add_middleware(GZipMiddleware, minimum_size=1024, compresslevel=5)
    client = TestClient(site)
    response = client.get('/assets/bundle-AbCd1234.js', headers={'Accept-Encoding': 'gzip'})
    assert response.headers['content-encoding'] == 'gzip'
    with client.stream('GET', '/assets/bundle-AbCd1234.js', headers={'Accept-Encoding': 'gzip'}) as streamed:
        assert len(b''.join(streamed.iter_raw())) < 3000
    assert 'immutable' in response.headers.get('cache-control', '')
    assert client.get('/assets/missing.js').status_code == 404
    assert client.get('/map.svg').status_code == 404
    assert client.get('/seasons/1').status_code == 200
    assert 'no-cache' in client.get('/seasons/1').headers.get('cache-control', '')
