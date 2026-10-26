"""Start isolated local services and run owned-silence workflows without model downloads."""
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path


def main():
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backend-port',type=int,default=8011)
    parser.add_argument('--frontend-port',type=int,default=5181)
    choices = ('onboarding_browser_smoke.py', 'editor_browser_smoke.py', 'reliability_browser_smoke.py', 'review_browser_smoke.py',
               'studio_browser_smoke.py', 'recognition_settings_browser_smoke.py')
    parser.add_argument('--scripts', nargs='+', choices=choices, default=list(choices))
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[2]
    output=root/'lyriclens-app/artifacts/browser-ci'
    output.mkdir(parents=True,exist_ok=True)
    for port in (args.backend_port,args.frontend_port):
        with socket.socket() as probe:
            if probe.connect_ex(('127.0.0.1',port))==0:
                raise RuntimeError(f'Port {port} already occupied; no existing process was stopped')
    processes=[]
    with tempfile.TemporaryDirectory() as data, (output/'backend.log').open('w') as backend_log, (output/'frontend.log').open('w') as frontend_log:
        env={**os.environ,'LYRICLENS_DATA':data,'LYRICLENS_DEVICE':'cpu','LYRICLENS_COMPUTE':'int8',
             'LYRICLENS_API_URL':f'http://127.0.0.1:{args.backend_port}',
             'LYRICLENS_BROWSER_URL':f'http://127.0.0.1:{args.frontend_port}',
             'LYRICLENS_STUDIO_MEDIA_DIR':str(output/'studio-media')}
        try:
            processes.append(subprocess.Popen([sys.executable,'-m','uvicorn','lyriclens.api:app','--host','127.0.0.1','--port',str(args.backend_port)],cwd=root,env=env,stdout=backend_log,stderr=subprocess.STDOUT))
            processes.append(subprocess.Popen(['node',str(root/'lyriclens-app/frontend/node_modules/vite/bin/vite.js'),'--host','127.0.0.1','--port',str(args.frontend_port),'--strictPort'],cwd=root/'lyriclens-app/frontend',env=env,stdout=frontend_log,stderr=subprocess.STDOUT))
            deadline=time.monotonic()+45
            while True:
                try:
                    with urllib.request.urlopen(env['LYRICLENS_BROWSER_URL']+'/api/health',timeout=2) as response:
                        if response.status==200: break
                except OSError:
                    pass
                if any(p.poll() is not None for p in processes) or time.monotonic()>deadline:
                    raise RuntimeError('Local CI services failed; inspect browser-ci logs')
                time.sleep(.25)
            for script in args.scripts:
                subprocess.run([sys.executable,str(root/'lyriclens-app/scripts'/script)],cwd=root,env=env,check=True)
        finally:
            for process in reversed(processes):
                if os.name=='nt' and process.poll() is None:
                    subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=False)
                    process.wait(timeout=10)
                    continue
                process.terminate()
                try: process.wait(timeout=10)
                except subprocess.TimeoutExpired: process.kill();process.wait()


if __name__=='__main__':
    main()
