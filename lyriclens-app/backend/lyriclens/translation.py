"""Optional local text translation with a bounded worker and immutable source snapshots."""
import hashlib
import json
import logging
import queue
import threading
import time
from .store import now

MODEL = 'facebook/m2m100_418M'
REVISION = '55c2e61bbf05dfb8d7abccdc3fae6fc8512fd636'
ACTIVE = {'queued', 'processing'}
log = logging.getLogger('lyriclens.translation')


def model_dir(settings):
    return settings.root/'translation-models'/f'm2m100-{REVISION[:12]}-int8'


def prepared(settings):
    try:
        marker = json.loads((model_dir(settings)/'READY.json').read_text(encoding='utf-8'))
        return marker.get('model')==MODEL and marker.get('revision')==REVISION and (model_dir(settings)/'model.bin').exists()
    except (OSError, ValueError):
        return False


def source_segments(job, pipeline):
    result = job.get('results',{}).get(pipeline)
    if not result or result['state']!='completed':
        raise ValueError('No completed transcript for this pipeline')
    return result['edited'] if result.get('edited') is not None else result['original']


def fingerprint(segments):
    return hashlib.sha256(json.dumps(segments,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8')).hexdigest()


def key(pipeline, target):
    return f'{pipeline}:{target}'


def has_active(job):
    return any(t['state'] in ACTIVE for t in job.get('translations',{}).values())


def is_stale(job, translation):
    return fingerprint(source_segments(job,translation['pipeline']))!=translation['source_fingerprint']


class LocalTranslator:
    def __init__(self, settings):
        self.settings = settings
        self.model = self.tokenizer = None

    def translate(self, text, source, target):
        if not text.strip():
            return ''
        if not prepared(self.settings):
            raise ValueError('Translation model is not prepared. Run python -m lyriclens.models translation-download explicitly.')
        if self.model is None:
            import ctranslate2
            from transformers import M2M100Tokenizer
            self.tokenizer = M2M100Tokenizer.from_pretrained(str(model_dir(self.settings)),local_files_only=True)
            self.model = ctranslate2.Translator(str(model_dir(self.settings)),device='cpu',compute_type='int8',inter_threads=1,intra_threads=4)
        self.tokenizer.src_lang = source
        tokens = self.tokenizer.convert_ids_to_tokens(self.tokenizer.encode(text,truncation=False))
        if len(tokens)>512:
            raise ValueError('A transcript segment exceeds 512 translation tokens. Split it into shorter segments and retry; no text was truncated.')
        output = self.model.translate_batch([tokens],target_prefix=[[self.tokenizer.lang_code_to_token[target]]],
                                          beam_size=4,max_input_length=0,max_decoding_length=512,
                                          return_end_token=True)[0].hypotheses[0]
        if not output or output[-1]!='</s>':
            raise ValueError('Translation reached its output limit. Shorten the source segment and retry; incomplete output was not saved.')
        return self.tokenizer.decode(self.tokenizer.convert_tokens_to_ids(output[1:]),skip_special_tokens=True).strip()


class TranslationWorker:
    def __init__(self, settings, store, translator=None):
        self.settings, self.store = settings, store
        self.translator = translator or LocalTranslator(settings)
        self.injected = translator is not None
        self.queue = queue.Queue(settings.queue_size)
        self.stopping = threading.Event()
        self.thread = threading.Thread(target=self.loop,daemon=True)

    def start(self):
        with self.store.lock:
            for job in self.store.list():
                changed = False
                for translation in job.get('translations',{}).values():
                    if translation['state'] in ACTIVE:
                        translation.update(state='interrupted',error='Translation interrupted by service restart')
                        changed = True
                if changed:
                    self.store.put(job)
        self.thread.start()

    def stop(self):
        self.stopping.set()
        self.thread.join(timeout=2)

    def loop(self):
        while not self.stopping.is_set():
            try:
                identifier, name = self.queue.get(timeout=.2)
            except queue.Empty:
                continue
            try:
                self.run(identifier,name)
            except Exception:
                log.exception('Translation worker failed')
            finally:
                self.queue.task_done()

    def update(self, identifier, name, **changes):
        with self.store.lock:
            job = self.store.get(identifier)
            if job is None:
                return
            job['translations'][name].update(changes)
            self.store.put(job)

    def run(self, identifier, name):
        job = self.store.get(identifier)
        if not job or job.get('translations',{}).get(name,{}).get('state')!='queued':
            return
        translation = job['translations'][name]
        self.update(identifier,name,state='processing',started_at=now())
        started = time.perf_counter()
        try:
            segments = list(translation.get('segments', []))
            for segment in translation['source_segments'][len(segments):]:
                latest = self.store.get(identifier)
                if self.stopping.is_set() or latest['translations'][name].get('cancel_requested'):
                    self.update(identifier,name,state='interrupted' if self.stopping.is_set() else 'canceled',completed_at=now())
                    return
                source = segment.get('language') or translation['source_language']
                target = translation['target_language']
                text = segment['text'] if source==target else self.translator.translate(segment['text'],source,target)
                segments.append({**segment,'text':text,'language':target})
                self.update(identifier,name,completed_segments=len(segments),segments=list(segments))
            latest = self.store.get(identifier)
            if self.stopping.is_set() or latest['translations'][name].get('cancel_requested'):
                self.update(identifier,name,state='interrupted' if self.stopping.is_set() else 'canceled',completed_at=now())
                return
            self.update(identifier,name,state='completed',segments=segments,edited=None,completed_at=now(),seconds=time.perf_counter()-started)
        except Exception as exc:
            log.exception('Local translation failed')
            self.update(identifier,name,state='failed',error=str(exc) if isinstance(exc,ValueError) else 'Local translation failed. Check optional dependencies and the local server log.',completed_at=now())


def prepare(settings):
    """Network/conversion permitted only in this explicitly invoked CLI operation."""
    from huggingface_hub import snapshot_download
    from ctranslate2.converters import TransformersConverter
    folder = model_dir(settings)
    if prepared(settings):
        print('Translation model is already prepared.')
        return
    original = settings.root/'translation-models'/f'm2m100-{REVISION[:12]}-source'
    snapshot_download(MODEL,revision=REVISION,local_dir=original,
                      allow_patterns=['config.json','pytorch_model.bin','sentencepiece.bpe.model','vocab.json','tokenizer_config.json','special_tokens_map.json','README.md'])
    class PinnedConverter(TransformersConverter):
        def load_model(self, model_class, model_name_or_path, **kwargs):
            # CT2 4.8 uses the newer dtype name; the pinned Transformers 4.49 uses torch_dtype.
            kwargs['torch_dtype'] = kwargs.pop('dtype',None)
            return model_class.from_pretrained(model_name_or_path,local_files_only=True,**kwargs)
    converter = PinnedConverter(str(original),copy_files=['sentencepiece.bpe.model','vocab.json','tokenizer_config.json','special_tokens_map.json'])
    converter.convert(str(folder),quantization='int8',force=True)
    (folder/'READY.json').write_text(json.dumps(dict(model=MODEL,revision=REVISION,license='MIT',quantization='int8')),encoding='utf-8')
    print(f'Prepared local CPU/int8 translation model: {folder}')
