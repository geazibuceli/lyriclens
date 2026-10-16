"""Run matched Small/Large-v3 development comparisons, keeping raw research results private."""
import argparse
import json
import subprocess
import sys
from pathlib import Path


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest',type=Path,default=Path(__file__).resolve().parents[2]/'.runtime'/'singing-research'/'manifest.jsonl')
    parser.add_argument('--device',choices=['cpu','cuda'],default='cuda')
    parser.add_argument('--compute',default='float16')
    args=parser.parse_args()
    directory=args.manifest.parent
    reports={}
    for profile in ['configured','large-v3']:
        output=directory/f'{profile}-results.json'
        command=[sys.executable,'-m','lyriclens.evaluate',str(args.manifest),'--split','development',
                 '--manual-language','--model-profile',profile,'--device',args.device,'--compute',args.compute,'--output',str(output)]
        subprocess.run(command,check=True,timeout=3600)
        reports[profile]=json.loads(output.read_text(encoding='utf-8'))
    # Public summary contains metrics and provenance, never corpus lyrics or recognized text.
    per_clip=[]
    for baseline in reports['configured']['per_clip']:
        candidate=next(r for r in reports['large-v3']['per_clip'] if r['id']==baseline['id'] and r['pipeline']==baseline['pipeline'])
        if candidate['sha256']!=baseline['sha256'] or candidate['reference']!=baseline['reference']:
            raise ValueError('Comparison inputs or references differ')
        item={'id':baseline['id'],'language':baseline['language'],'pipeline':baseline['pipeline'],'sha256':baseline['sha256'],
              'reference_source':baseline['reference_source'],'permissions':baseline['permissions'],
              'duration':baseline['duration'],'conditions':baseline['conditions']}
        for label,run in [('small',baseline),('large_v3',candidate)]:
            item[label]={'state':run['state'],'model':run['model'],'revision':run['revision'],'seconds':run['seconds'],
                         'real_time_factor':run['real_time_factor'],'peak_memory_bytes':run['peak_memory_bytes'],
                         'inference_device':run['inference_device'],'compute_type':run['compute_type'],'settings':run['settings'],
                         'separator_settings':run['separator_settings'],'error':run.get('error'),
                         'metrics':{k:v for k,v in run.get('metrics',{}).items() if not k.startswith('normalized_')}}
        per_clip.append(item)
    summary={'purpose':'Small development singing diagnostic; not representative seven-language validation',
             'comparison_scope':'Configured Small decoding versus explicit Large-v3 profile with native word alignment; not an isolated model-size ablation',
             'selection':'Fixed before model execution; no final evaluation clips used for model/settings selection',
             'model_change':'Explicit optional choice; configured default is unchanged',
             'environment':reports['large-v3']['per_clip'][0]['environment'] if per_clip else {},
             'per_clip':per_clip,'per_language':{key:report['per_language'] for key,report in reports.items()},
             'missing_languages':sorted(set(['ko','ja','zh','en','es','pt','fr'])-{r['language'] for r in per_clip}),
             'raw_research_reports':'Stored locally alongside the manifest; not redistributed'}
    target=Path(__file__).resolve().parents[1]/'evaluation'/'singing-model-comparison.json'
    target.write_text(json.dumps(summary,indent=2),encoding='utf-8')
    print(f'Wrote text-free singing comparison to {target}',flush=True)


if __name__=='__main__':
    main()
