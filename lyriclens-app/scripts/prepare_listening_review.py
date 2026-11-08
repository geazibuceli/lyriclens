"""Build a local listening worksheet from existing paired runs; never certify review."""
import argparse
import hashlib
import html
import json
import os
from pathlib import Path


LABELS = (('configured', 'direct', 'Small / original'),
          ('configured', 'vocals', 'Small / isolated'),
          ('large-v3', 'direct', 'Large-v3 / original'),
          ('large-v3', 'vocals', 'Large-v3 / isolated'))


def escape(value):
    return html.escape(str(value), quote=True)


def prepare(datasets, output):
    if output.exists():
        raise ValueError('Review directory exists; choose a new version')
    songs = []
    for manifest, runs in datasets:
        rows = [json.loads(line) for line in manifest.read_text(encoding='utf-8').splitlines() if line.strip()]
        for row in rows:
            audio = (manifest.parent / row['path']).resolve()
            if hashlib.sha256(audio.read_bytes()).hexdigest() != row['sha256']:
                raise ValueError('Source recording changed')
            stem = hashlib.sha256(row['id'].encode()).hexdigest()[:16]
            isolated = runs / ('separation-' + stem) / 'vocals-16k.wav'
            if not isolated.is_file():
                raise ValueError('Isolated audio is missing')
            transcripts = []
            for profile, pipeline, label in LABELS:
                path = runs / f'{stem}-{profile}-{pipeline}.json'
                raw = json.loads(path.read_text(encoding='utf-8'))
                transcripts.append((label, raw['segments']))
            songs.append((row, audio, isolated, transcripts))
    output.mkdir(parents=True)

    def relative(path):
        return escape(Path(os.path.relpath(path, output)).as_posix())

    sections = []
    passages = 0
    for row, audio, isolated, transcripts in songs:
        windows = []
        for start in range(0, int(row['duration']) + 1, 15):
            end = min(start + 15, row['duration'])
            if end <= start:
                continue
            cells = []
            for label, segments in transcripts:
                selected = [s for s in segments if s['start'] < end and s['end'] > start]
                cells.append('<td>' + '<br>'.join(
                    f'<small>{s["start"]:.2f}–{s["end"]:.2f}s</small> {escape(s["text"])}'
                    for s in selected) + '</td>')
            windows.append(f'<tr><th><button data-start="{start}" data-end="{end}">Listen {start // 60:02}:{start % 60:02}–{int(end) // 60:02}:{int(end) % 60:02}</button></th>' +
                           ''.join(cells) + '<td><textarea class="passage-note" aria-label="Passage correction or pronunciation note"></textarea></td></tr>')
            passages += 1
        sections.append(f'''<section data-id="{escape(row['id'])}"><h2>{escape(row.get('title', row['id']))}</h2>
<p>{escape(row.get('singer', 'Josh Woodward'))} · {row['duration']:.2f}s · reference and accent review pending</p>
<p>{escape(row['permissions'])}</p>
<label>Audio route <select class="route"><option value="{relative(audio)}">Original recording</option><option value="{relative(isolated)}">Isolated vocals</option></select></label>
<label>Speed <select class="speed"><option>1</option><option>0.75</option><option>0.5</option></select></label>
<audio controls preload="metadata" src="{relative(audio)}"></audio><p class="error" role="alert"></p>
<details><summary>Publisher lyrics — edit only after listening</summary><p>Confirm repetitions and the performed version. Changing this draft does not verify the benchmark.</p>
<textarea class="reference" aria-label="Reference draft">{escape(row['reference'])}</textarea></details>
<p>Rows use 15-second listening windows. ASR passages crossing a boundary appear in both rows; displayed text is not word-aligned.</p>
<div class="table"><table><thead><tr><th>Listen</th>{''.join('<th>' + label + '</th>' for _, _, label in LABELS)}<th>Words sung / pronunciation notes</th></tr></thead>
<tbody>{''.join(windows)}</tbody></table></div></section>''')
    document = '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>LyricLens listening review</title><style>
body{font:16px system-ui;background:#f5f7f4;color:#223324;margin:24px}section{background:white;padding:20px;margin:24px 0;border-radius:12px}audio{display:block;width:min(100%,700px);margin:14px 0}button,select{font:inherit;padding:8px}label{margin-right:12px}.table{overflow:auto}table{border-collapse:collapse;width:100%;min-width:1100px}td,th{padding:10px;border:1px solid #ccd5ca;vertical-align:top;text-align:left}td{min-width:180px}small{display:block;color:#52634d}textarea{box-sizing:border-box;width:100%;min-height:100px;font:inherit}.reference{min-height:320px}summary{cursor:pointer}.error{color:#a22}
</style><h1>LyricLens listening review</h1>
<p>Local draft worksheet. No reference, word, or accent has been certified as human-reviewed. Listen, correct the words and record uncertainty. Keep the published source and ASR guesses separate.</p>
<p>Edits stay in this page until you download them. Download before reloading or closing.</p>
<button id="download">Download review draft</button>''' + ''.join(sections) + '''
<script>
for(const section of document.querySelectorAll('section')){
 const audio=section.querySelector('audio'),error=section.querySelector('.error');let stopAt=null;
 audio.addEventListener('error',()=>{error.textContent='Audio could not load. Keep this report beside its local recordings and open it in a desktop browser.'});
 audio.addEventListener('loadedmetadata',()=>error.textContent='');
 audio.addEventListener('play',()=>{for(const other of document.querySelectorAll('audio'))if(other!==audio)other.pause()});
 audio.addEventListener('timeupdate',()=>{if(stopAt!==null&&audio.currentTime>=stopAt){audio.pause();stopAt=null}});
 section.querySelector('.speed').onchange=e=>audio.playbackRate=Number(e.target.value);
 section.querySelector('.route').onchange=e=>{audio.pause();stopAt=null;audio.src=e.target.value;audio.load()};
 for(const button of section.querySelectorAll('[data-start]'))button.onclick=async()=>{
  try{stopAt=Number(button.dataset.end);audio.currentTime=Number(button.dataset.start);await audio.play();error.textContent=''}
  catch(e){error.textContent='Playback could not start. Load the audio using the player and retry.'}
 };
}
document.querySelector('#download').onclick=()=>{
 const recordings=[...document.querySelectorAll('section')].map(section=>({id:section.dataset.id,reference:section.querySelector('.reference').value,
  notes:[...section.querySelectorAll('tr')].slice(1).map(row=>({start:Number(row.querySelector('button').dataset.start),end:Number(row.querySelector('button').dataset.end),note:row.querySelector('textarea').value})).filter(row=>row.note.trim())}));
 const data={version:1,status:'draft',human_review_verified:false,recordings};
 const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='listening-review-draft.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),60000);
};
</script></html>'''
    (output / 'review.html').write_text(document, encoding='utf-8')
    summary = dict(recordings=len(songs), listening_windows=passages, human_review_verified=False,
                   reference_changes_applied=False, accuracy_scored=False)
    (output / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--dataset', nargs=2, action='append', required=True, metavar=('MANIFEST', 'RUNS'))
    args = parser.parse_args()
    print(json.dumps(prepare([(Path(a), Path(b)) for a, b in args.dataset], args.output), indent=2))
