"""Check a running Docker frontend/API using owned silence, without model downloads."""
import argparse
import io
import json
import re
import time
import urllib.error
import urllib.request
import uuid
import wave
from pathlib import Path


def request(base, path, *, method='GET', data=None, headers=None):
    req = urllib.request.Request(base + path, data=data, method=method, headers=headers or {})
    with urllib.request.urlopen(req, timeout=10) as response:
        return response.read()


def check(base):
    deadline = time.monotonic() + 90
    while True:
        try:
            health = json.loads(request(base, '/api/health'))
            if health.get('worker_alive'):
                break
        except (OSError, ValueError):
            pass
        if time.monotonic() >= deadline:
            raise RuntimeError('Frontend proxy/API did not become healthy within 90 seconds')
        time.sleep(.5)
    html = request(base, '/').decode('utf-8')
    asset = re.search(r'src="(/assets/[^\"]+\.js)"', html)
    assert asset, 'Production JavaScript bundle is missing'
    bundle = request(base, asset[1])
    assert b'Filter instrumental sections' in bundle, 'Frontend does not include the current recognition controls'
    demo = request(base, '/demo/voice.wav')
    with wave.open(io.BytesIO(demo), 'rb') as audio:
        assert audio.getnframes() > 0
    models = json.loads(request(base, '/api/models'))
    assert models['ffmpeg_available'], 'FFmpeg is unavailable in the backend image'
    assert {p['id'] for p in models['profiles']} >= {'configured', 'aligned', 'large-v3'}
    identifier = None
    try:
        buffer = io.BytesIO()
        with wave.open(buffer, 'wb') as audio:
            audio.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
            audio.writeframes(bytes(32000))
        boundary = 'LyricLens-' + uuid.uuid4().hex
        chunks = []
        for key, value in {'language': 'en', 'pipeline': 'direct', 'model_profile': 'aligned',
                           'reduce_hallucinations': 'true'}.items():
            chunks.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode())
        chunks.append(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="owned-docker-silence.wav"\r\nContent-Type: audio/wav\r\n\r\n'.encode())
        chunks.extend([buffer.getvalue(), f'\r\n--{boundary}--\r\n'.encode()])
        job = json.loads(request(base, '/api/jobs', method='POST', data=b''.join(chunks),
                                 headers={'Content-Type': f'multipart/form-data; boundary={boundary}'}))
        identifier = job['id']
        path = '/api/jobs/' + identifier
        deadline = time.monotonic() + 30
        while job['state'] in {'queued', 'processing'}:
            if time.monotonic() >= deadline:
                raise RuntimeError('Owned silence job exceeded its smoke-test deadline')
            time.sleep(.2)
            job = json.loads(request(base, path))
        assert job['state'] == 'completed', job.get('error')
        assert job['inference']['word_timestamps'] is True
        assert job['inference']['vad_filter'] is True
        assert job['inference']['hallucination_silence_threshold'] == 2.0
        result = job['results']['direct']
        assert result['original'] == [] and result['provenance']['model_executed'] is False
        raw = json.loads(request(base, path + '/raw?pipeline=direct'))
        assert raw['model_executed'] is False
        for format_name in ('json', 'txt', 'srt', 'lrc'):
            request(base, path + '/export?pipeline=direct&format=' + format_name)
        return {'frontend_bundle': True, 'demo_audio': True, 'proxy_worker_alive': True,
                'ffmpeg_available': True, 'guarded_upload': True, 'silence_export_formats': ['json', 'txt', 'srt', 'lrc'],
                'recognition_models_executed': False,
                'note': 'Owned digital-silence integration check; not a singing-accuracy benchmark.'}
    finally:
        if identifier is not None:
            path = '/api/jobs/' + identifier
            job = json.loads(request(base, path))
            if job['state'] in {'queued', 'processing'}:
                request(base, path + '/cancel', method='POST', data=b'')
                deadline = time.monotonic() + 10
                while job['state'] in {'queued', 'processing'} and time.monotonic() < deadline:
                    time.sleep(.2)
                    job = json.loads(request(base, path))
            if job['state'] in {'queued', 'processing'}:
                raise RuntimeError(f'Owned fixture still active; cleanup required for job {identifier}')
            request(base, path, method='DELETE')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://127.0.0.1:5182')
    parser.add_argument('--output', type=Path, default=Path('lyriclens-app/artifacts/docker-smoke/report.json'))
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    try:
        report = {'passed': True, **check(args.url.rstrip('/'))}
    except Exception as error:
        args.output.write_text(json.dumps({'passed': False, 'error': str(error)}, indent=2), encoding='utf-8')
        raise
    args.output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print('Docker smoke passed: production bundle, demo audio, API proxy, guarded silence upload and exports.')


if __name__ == '__main__':
    main()
