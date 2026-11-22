"""Изолированный ASGI и пустой worker для короткого окна выпуска.

Этот модуль копируется в отдельный технический релиз. Не импортирует приложение,
конфигурацию или драйвер БД; ни один запрос не может выполнить игровую операцию.
"""
import json
import re
from threading import Event


HTML = '''<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow"><title>BFME ClanWars</title>
<link rel="stylesheet" href="/maintenance.css"></head><body><main>
<p class="brand">BFME ClanWars</p><h1>Техническое обновление</h1>
<p>Сохраняем итоги первого сезона и обновляем сайт.</p>
<p>Аккаунты, матчи и достижения сохраняются. Попробуйте зайти немного позже.</p>
</main></body></html>'''
CSS = '''html{color-scheme:dark;background:#0d100f;color:#eee;font:18px/1.6 Arial,sans-serif}
body{margin:0;min-height:100vh;display:grid;place-items:center}
main{box-sizing:border-box;width:min(100%,800px);padding:40px 28px}
.brand{color:#d5bd7a;font-weight:700}h1{font-family:Georgia,serif;font-size:32px;color:#d5bd7a}
p{max-width:650px}'''


def idle_worker(stop_event=None):
    stop_event = stop_event if stop_event is not None else Event()
    while not stop_event.wait(60):
        pass


def create_app(release):
    if not isinstance(release, str) or re.fullmatch(r'[A-Za-z0-9_.-]{1,120}', release) is None:
        raise ValueError('Некорректный идентификатор технического релиза')

    async def app(scope, receive, send):
        if scope['type'] == 'lifespan':
            while True:
                message = await receive()
                if message['type'] == 'lifespan.startup':
                    await send({'type': 'lifespan.startup.complete'})
                elif message['type'] == 'lifespan.shutdown':
                    await send({'type': 'lifespan.shutdown.complete'})
                    return
        elif scope['type'] == 'websocket':
            await send({'type': 'websocket.close', 'code': 1013})
        elif scope['type'] == 'http':
            method, path = scope['method'], scope.get('path', '/')
            status, media = 503, 'application/json; charset=utf-8'
            body = json.dumps({'maintenance': True, 'detail': 'Техническое обновление сайта'},
                ensure_ascii=False).encode('utf8')
            if method in {'GET', 'HEAD'}:
                if path == '/__cutover__/status':
                    status = 200
                    body = json.dumps({'maintenance': True, 'release': release}).encode('utf8')
                elif path == '/health/live':
                    status, body = 200, b'{"maintenance":true,"alive":true}'
                elif path == '/maintenance.css':
                    status, media, body = 200, 'text/css; charset=utf-8', CSS.encode('utf8')
                elif path == '/':
                    media, body = 'text/html; charset=utf-8', HTML.encode('utf8')
            headers = [(b'content-type', media.encode()), (b'content-length', str(len(body)).encode()),
                (b'cache-control', b'no-store'), (b'retry-after', b'60'),
                (b'x-content-type-options', b'nosniff'), (b'x-robots-tag', b'noindex, nofollow'),
                (b'content-security-policy', b"default-src 'none'; style-src 'self'; frame-ancestors 'none'")]
            await send({'type': 'http.response.start', 'status': status, 'headers': headers})
            await send({'type': 'http.response.body', 'body': b'' if method == 'HEAD' else body})

    return app
