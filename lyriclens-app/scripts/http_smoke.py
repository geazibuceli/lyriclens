"""Opt-in HTTP smoke test for a running native or Docker Direct service."""
import argparse
import json
import time
from pathlib import Path
import httpx


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url',default='http://127.0.0.1:8012')
    parser.add_argument('--pipeline',choices=['direct','both'],default='direct')
    parser.add_argument('--output',type=Path,default=Path(__file__).resolve().parents[1]/'evaluation'/'docker-smoke.json')
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    with httpx.Client(base_url=args.url,timeout=30) as client:
        assert client.get('/api/health').json()['status']=='ok'
        readiness=client.get('/api/models').json()
        assert readiness['prepared'] and readiness['ffmpeg_available'],readiness
        with (root/'evaluation'/'audio'/'singing'/'mary.wav').open('rb') as audio:
            response=client.post('/api/jobs',files={'file':('mary.wav',audio,'audio/wav')},data={'language':'en','pipeline':args.pipeline})
        response.raise_for_status()
        identifier=response.json()['id']
        for _ in range(180):
            job=client.get('/api/jobs/'+identifier).json()
            if job['state'] not in {'queued','processing'}:
                break
            time.sleep(1)
        assert job['state']=='completed',job
        assert job['results']['direct']['original'],job
        if args.pipeline=='both':
            assert job['results']['vocals']['state']=='completed',job
            assert job['results']['vocals']['original'],job
        assert client.get('/api/jobs/'+identifier+'/export?format=srt').status_code==200
        args.output.write_text(json.dumps(job,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'state':job['state'],'job_id':identifier,'seconds':job['total_seconds'],'platform':job['environment']['platform']},indent=2))


if __name__=='__main__':
    main()
