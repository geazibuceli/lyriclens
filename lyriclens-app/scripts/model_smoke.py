"""Explicit real-model smoke run with provenance; no model substitutions or downloads."""
import argparse
import json
import tempfile
import time
from pathlib import Path
from lyriclens.adapters import FFmpegDecoder, WhisperTranscriber
from lyriclens.config import Settings
from lyriclens.domain import validate_segments
from lyriclens.memory import PeakMemory
from lyriclens.worker import environment


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('audio',type=Path)
    parser.add_argument('--device',choices=['cpu','cuda'],default='cpu')
    parser.add_argument('--compute',default='int8')
    parser.add_argument('--language',default='en')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    settings=Settings(device=args.device,compute_type=args.compute)
    report={'environment':environment(),'model_id':settings.model_id,'revision':settings.revision,
            'device':args.device,'compute_type':args.compute,'language_instruction':args.language,
            'inference':settings.inference(),'purpose':'Execution smoke test; not a quality benchmark'}
    started=time.perf_counter()
    memory=PeakMemory().start()
    try:
        with tempfile.TemporaryDirectory() as temp:
            audio=Path(temp)/'decoded.wav'
            info=FFmpegDecoder(settings).decode(args.audio,audio)
            raw=WhisperTranscriber(settings).transcribe(audio,args.language)
            validate_segments(raw['segments'],info['duration'])
            report.update(state='completed',duration=info['duration'],raw=raw)
    except Exception as exc:
        report.update(state='failed',error=str(exc))
    report.update(seconds=time.perf_counter()-started,peak_rss_bytes=memory.stop())
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:report[k] for k in ('state','device','compute_type','seconds')},indent=2),flush=True)
    if report['state']=='failed':
        raise SystemExit(1)


if __name__=='__main__':
    main()
