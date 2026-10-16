"""Offline development-only decoding experiments; never use references as ASR input.

Raw corpus text stays in ignored .runtime. Public reports contain metrics only.
No experiment changes the application's runtime settings automatically.
"""
import argparse
import hashlib
import json
import subprocess
import time
from dataclasses import replace
from pathlib import Path

from lyriclens.adapters import FFmpegDecoder, WhisperTranscriber, DemucsSeparator
from lyriclens.config import Settings, LANGUAGES
from lyriclens.domain import validate_segments, text_of
from lyriclens.evaluate import load_manifest, metrics
from lyriclens.profiles import profile_settings


VARIANTS = {
    'baseline': {},
    'wide-search': {'beam_size': 10, 'patience': 2.0},
    'context': {'beam_size': 10, 'condition_on_previous_text': True},
    'shorter': {'beam_size': 10, 'length_penalty': 0.8},
    'tempo-115': {'audio_tempo': 1.15},
    'tempo-130': {'audio_tempo': 1.30},
}


class ExperimentSettings:
    def __init__(self, base, options):
        self.base, self.options = base, options

    def __getattr__(self, name):
        return getattr(self.base, name)

    def inference(self):
        return {**self.base.inference(), **{k:v for k,v in self.options.items() if k!='audio_tempo'}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    repo = Path(__file__).resolve().parents[2]
    parser.add_argument('--manifest', type=Path, default=repo/'.runtime/singing-research/manifest.jsonl')
    parser.add_argument('--variants', nargs='+', choices=list(VARIANTS), default=['baseline','wide-search','context','shorter'])
    parser.add_argument('--reuse-derived', action='store_true', help='Verify cached audio against prior baseline hashes before reuse')
    parser.add_argument('--report-name', default='singing-decoding-experiments')
    args = parser.parse_args()
    root = args.manifest.parent/'decoding-experiments'
    root.mkdir(exist_ok=True)
    rows = [r for r in load_manifest(args.manifest) if r['split']=='development']
    settings = replace(profile_settings(Settings(), 'large-v3'), device='cuda', compute_type='float16')
    decoder, separator = FFmpegDecoder(settings), DemucsSeparator(settings)
    inputs = []
    previous = json.loads((root/'raw-results.json').read_text(encoding='utf-8')) if args.reuse_derived else []
    try:
        for row in rows:
            folder = root/row['id']
            folder.mkdir(exist_ok=True)
            direct = folder/'decoded.wav'
            vocals = folder/'vocals.wav'
            if args.reuse_derived:
                for pipeline,audio in [('direct',direct),('vocals',vocals)]:
                    old = next(r for r in previous if r['id']==row['id'] and r['pipeline']==pipeline and r['variant']=='baseline')
                    if old['sha256']!=row['sha256'] or old['derived_sha256']!=hashlib.sha256(audio.read_bytes()).hexdigest():
                        raise ValueError('Cached evaluation audio provenance mismatch')
                import soundfile
                info = {'duration':soundfile.info(direct).duration}
            else:
                print(f'Preparing {row["id"]}',flush=True)
                info = decoder.decode(row['resolved_path'], direct)
                decoder.decode(separator.separate(direct, folder/'stems'), vocals)
            inputs.extend((row, pipeline, audio, info['duration']) for pipeline,audio in [('direct',direct),('vocals',vocals)])
    finally:
        separator.close()
    model = WhisperTranscriber(settings)
    reports = []
    for variant in args.variants:
        options = VARIANTS[variant]
        model.settings = ExperimentSettings(settings, options)
        for row,pipeline,audio,duration in inputs:
            tempo = options.get('audio_tempo',1.0)
            if tempo!=1:
                transformed = audio.with_name(f'{audio.stem}-{variant}.wav')
                subprocess.run([settings.ffmpeg,'-nostdin','-v','error','-y','-i',str(audio),
                                '-af',f'atempo={tempo}','-c:a','pcm_s16le',str(transformed)],check=True,capture_output=True,timeout=60)
                audio = transformed
            print(f'{variant}: {row["id"]}/{pipeline}', flush=True)
            result = dict(variant=variant, id=row['id'], language=row['language'], pipeline=pipeline,
                          sha256=row['sha256'], derived_sha256=hashlib.sha256(audio.read_bytes()).hexdigest(),
                          reference_source=row['reference_source'], permissions=row['permissions'],
                          model=settings.model_id, revision=settings.revision, settings=model.settings.inference(),
                          audio_tempo=tempo,timestamp_mapping='model time multiplied by tempo, then strict original-duration validation')
            started = time.perf_counter()
            try:
                raw = model.transcribe(audio, row['language'])
                result['raw'] = raw
                segments = [{**s,'start':s['start']*tempo,'end':s['end']*tempo} for s in raw['segments']]
                validate_segments(segments, duration)
                result.update(state='completed', metrics=metrics(row['reference'], text_of(raw['segments']), row['language']))
            except Exception as exc:
                result.update(state='failed', error=str(exc))
            result['asr_seconds'] = time.perf_counter()-started
            reports.append(result)
            private_name = 'raw-results.json' if args.report_name=='singing-decoding-experiments' else args.report_name+'-raw.json'
            (root/private_name).write_text(json.dumps(reports,ensure_ascii=False,indent=2),encoding='utf-8')
    summaries = []
    for variant in args.variants:
        for language in LANGUAGES:
            for pipeline in ['direct','vocals']:
                group = [r for r in reports if r['variant']==variant and r['language']==language and r['pipeline']==pipeline]
                completed = [r for r in group if r['state']=='completed']
                denominator = sum(r['metrics']['reference_characters'] for r in completed)
                summaries.append(dict(variant=variant,language=language,pipeline=pipeline,clips=len(group),
                                      failures=len(group)-len(completed),
                                      cer=sum(r['metrics']['character_errors'] for r in completed)/denominator if denominator else None))
    public = []
    for run in reports:
        item = {k:v for k,v in run.items() if k not in {'raw','metrics'}}
        item['metrics'] = {k:v for k,v in run.get('metrics',{}).items() if not k.startswith('normalized_')}
        public.append(item)
    target = repo/'lyriclens-app/evaluation'/f'{args.report_name}.json'
    target.write_text(json.dumps(dict(purpose='Development-only decoding search; not final evaluation',
                                     selection='Fixed variants before inference; no references supplied to ASR',
                                     audio='Same hashed original clips; derived input hashes and tempo recorded per run; ASR-only timing excludes transformations',
                                     runtime_changed=False, per_clip=public, summaries=summaries),indent=2),encoding='utf-8')
    print(f'Wrote {target}',flush=True)


if __name__ == '__main__':
    main()
