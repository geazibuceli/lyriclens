"""Opt-in real local translation diagnostics; original non-lyrical sentences, no quality score."""
import importlib.metadata
import json
import platform
import time
from pathlib import Path
from lyriclens.config import Settings, LANGUAGES
from lyriclens.translation import LocalTranslator, MODEL, REVISION, model_dir

SAMPLES = {
    'en':'The sun is shining today.',
    'pt':'O sol brilha hoje.',
    'es':'El sol brilla hoy.',
    'fr':"Le soleil brille aujourd'hui.",
    'ko':'오늘은 해가 빛납니다.',
    'ja':'今日は太陽が輝いています。',
    'zh':'今天阳光灿烂。',
}


def main():
    settings = Settings()
    translator = LocalTranslator(settings)
    reports = []
    for source,text in SAMPLES.items():
        for target in LANGUAGES:
            if source==target:
                continue
            started = time.perf_counter()
            result = dict(source_language=source,target_language=target,source_text=text)
            try:
                output = translator.translate(text,source,target)
                assert output.strip(), 'Empty output'
                result.update(state='completed',translation=output)
            except Exception as exc:
                result.update(state='failed',error=str(exc))
            result['seconds'] = time.perf_counter()-started
            reports.append(result)
            print(f'{source} -> {target}: {result["state"]}',flush=True)
    report = dict(purpose='Execution diagnostics on original short non-lyrical sentences; no translation quality score or lyric validation',
                  model=MODEL,revision=REVISION,license='MIT',device='cpu',compute_type='int8',
                  model_bytes=(model_dir(settings)/'model.bin').stat().st_size,
                  environment=dict(python=platform.python_version(),platform=platform.platform(),
                                   packages={name:importlib.metadata.version(name) for name in ['ctranslate2','transformers','sentencepiece']}),
                  settings=dict(beam_size=4,max_input_tokens=512,max_output_tokens=512),per_pair=reports)
    target = Path(__file__).resolve().parents[1]/'evaluation/translation-smoke.json'
    target.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    assert all(r['state']=='completed' for r in reports), 'Some pairs failed; inspect the report'
    print(f'Passed {len(reports)}/42 actual local translation executions; wrote {target}',flush=True)


if __name__=='__main__':
    main()
