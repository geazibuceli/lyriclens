import importlib.metadata
import json
import logging
import platform
import queue
import shutil
import threading
import time
from collections import OrderedDict
from dataclasses import replace
from .adapters import FFmpegDecoder, WhisperTranscriber, DemucsSeparator
from .domain import validate_segments, validate_model_segments, text_of
from .store import now

log = logging.getLogger("lyriclens")


class Worker:
    def __init__(self, settings, store, decoder=None, transcriber=None, separator=None):
        self.settings, self.store = settings, store
        self.decoder = decoder or FFmpegDecoder(settings)
        self.transcriber = transcriber or WhisperTranscriber(settings)
        self.injected_transcriber = transcriber is not None
        self.transcribers = OrderedDict()
        self.separator = separator or DemucsSeparator(settings)
        self.queue = queue.Queue(settings.queue_size)
        self.stopping = threading.Event()
        self.thread = threading.Thread(target=self.loop, daemon=True)

    def start(self):
        self.store.recover()
        self.thread.start()

    def transcriber_for(self,job):
        if self.injected_transcriber:
            return self.transcriber
        selected = replace(self.settings,model_id=job["model_id"],revision=job["revision"],
                           device=job["inference"]["device"],compute_type=job["inference"]["compute_type"],
                           word_timestamps=job["inference"].get("word_timestamps",False))
        key = (selected.model_id,selected.revision,selected.device,selected.compute_type,selected.word_timestamps)
        if key not in self.transcribers:
            if len(self.transcribers)>=2:
                self.transcribers.popitem(last=False)
            self.transcribers[key] = WhisperTranscriber(selected)
        self.transcribers.move_to_end(key)
        return self.transcribers[key]

    def stop(self):
        self.stopping.set()
        self.thread.join(timeout=2)
        if hasattr(self.separator,"close"):
            self.separator.close()

    def canceled(self, job_id):
        return self.stopping.is_set() or self.store.get(job_id).get("cancel_requested", False)

    def stage(self, job_id, stage):
        with self.store.lock:
            history = self.store.get(job_id).get("stage_history", [])
            history.append({"stage": stage, "at": now()})
            self.store.update(job_id, stage=stage, stage_history=history)
        log.info(json.dumps({"event": "stage", "job_id": job_id, "stage": stage}))

    def loop(self):
        while not self.stopping.is_set():
            try:
                job_id = self.queue.get(timeout=0.2)
            except queue.Empty:
                continue
            try:
                self.run(job_id)
            finally:
                self.queue.task_done()

    def run(self, job_id):
        job = self.store.get(job_id)
        if not job or job["state"] != "queued":
            return
        folder = self.settings.root / "jobs" / job_id
        started = time.perf_counter()
        final_changes = {}
        try:
            self.store.update(job_id, state="processing", started_at=now())
            if self.canceled(job_id):
                return
            self.stage(job_id, "Decoding audio")
            t = time.perf_counter()
            decoded = folder / "decoded.wav"
            info = self.decoder.decode(folder / "original", decoded)
            self.store.update(job_id, audio=info, decode_seconds=time.perf_counter() - t)
            processed_duration = info["duration"]
            offset = 0.0
            if job.get("region"):
                self.stage(job_id, "Extracting selected region with context")
                region = job["region"]
                cropped = folder / "region-16k.wav"
                processed_duration = self.decoder.crop(decoded, cropped, region["start"], region["end"])
                offset = region["start"]
                decoded = cropped
            self.store.update(job_id, processed_audio={"duration":processed_duration,"original_offset":offset,
                                                     "timeline":"identity plus original_offset"})
            results = {name: value for name, value in job.get('results', {}).items() if value['state'] == 'completed'}
            for pipeline in job["pipelines"]:
                if pipeline in results:
                    continue  # A resumed job keeps completed routes and user edits intact.
                if self.canceled(job_id):
                    return
                t = time.perf_counter()
                try:
                    audio = decoded
                    if pipeline == "vocals":
                        self.stage(job_id, "Separating vocals")
                        vocals = self.separator.separate(decoded, folder / "stems")
                        audio = folder / "vocals-16k.wav"
                        vocal_info = self.decoder.decode(vocals, audio)
                        if abs(vocal_info["duration"] - processed_duration) > 0.1:
                            raise ValueError("Vocal separation changed the timeline; timestamp mapping is unavailable")
                    if self.canceled(job_id):
                        return
                    self.stage(job_id, f"Transcribing {pipeline} audio")
                    raw = self.transcribe_plan(job,audio,folder,pipeline) if job.get('language_plan') else self.transcriber_for(job).transcribe(audio, None if job["requested_language"] == "auto" else job["requested_language"])
                    # Persist raw response before validation; never silently clamp invalid timestamps.
                    (folder / f"{pipeline}-raw.json").write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
                    local_segments, reordered = validate_model_segments(raw["segments"], processed_duration)
                    segments = validate_segments([{**s,"start":s["start"]+offset,"end":s["end"]+offset} for s in local_segments], info["duration"])
                    warnings = ["Singing recognition and segment timing may be inaccurate. Review against the audio."]
                    if reordered or raw.get('timestamp_order_normalized'):
                        warnings.append('Model segments were reordered by start time; timestamps and overlapping passages are unchanged. The raw response preserves the emitted order.')
                    if job.get('language_plan'):
                        warnings.append('Languages follow saved user instructions. Only saved passage intervals are transcribed; gaps are omitted. This is not automatic code-switch detection.')
                    if raw.get("signal_control"):
                        warnings.append(raw["signal_control"])
                    if not segments:
                        warnings.append("No words returned. Select a language, try the other pipeline, upload a clearer excerpt, or edit the transcript.")
                    results[pipeline] = {"state": "completed", "original": segments, "original_text": text_of(segments),
                                         "edited": None, "detected_language": raw.get("language"),
                                         "language_source": raw.get("language_source"), "warnings": warnings,
                                         "seconds": time.perf_counter() - t,
                                         "provenance": {"model_id": job["model_id"], "revision": job["revision"],
                                                        "settings": job["inference"], "region":job.get("region"),
                                                        "timestamp_offset":offset,
                                                        "language_plan":job.get('language_plan'),
                                                        "model_executed":raw.get("model_executed",True),
                                                        "separator_settings":{"device":self.settings.separation_device,"shifts":0} if pipeline == "vocals" else None,
                                                        "separator": "htdemucs/955717e8-8726e21a" if pipeline == "vocals" else None}}
                except Exception as exc:
                    log.exception("Pipeline failed: %s %s", job_id, pipeline)
                    if pipeline == "vocals":
                        (folder / "vocals-16k.wav").unlink(missing_ok=True)
                        shutil.rmtree(folder / "stems", ignore_errors=True)
                    results[pipeline] = {"state": "failed", "error": str(exc) if isinstance(exc, ValueError) else "Processing failed. Check the local server log.", "seconds": time.perf_counter() - t}
                self.store.update(job_id, results=results)
            state = "completed" if any(r["state"] == "completed" for r in results.values()) else "failed"
            final_changes = dict(state=state, stage="Finished", completed_at=now(), total_seconds=time.perf_counter() - started)
        except Exception as exc:
            log.exception("Job failed: %s", job_id)
            final_changes = dict(state="failed", stage="Failed", error=str(exc) if isinstance(exc, ValueError) else "Processing failed. Check the local server log.", completed_at=now())
            for name in ("decoded.wav", "vocals-16k.wav", "region-16k.wav"):
                (folder / name).unlink(missing_ok=True)
            shutil.rmtree(folder / "stems", ignore_errors=True)
        finally:
            with self.store.lock:
                if self.canceled(job_id):
                    final_changes = dict(state="interrupted" if self.stopping.is_set() else "canceled", stage="Stopped", completed_at=now())
                self.store.update(job_id, **final_changes)

    def transcribe_plan(self, job, audio, folder, pipeline):
        output = dict(segments=[],passages=[],language=None,language_source='user-instructed passage languages',model_executed=False)
        path = folder/f'{pipeline}-raw.json'
        for index,passage in enumerate(job['language_plan']):
            if self.canceled(job['id']):
                raise ValueError('Multilingual transcription stopped')
            self.stage(job['id'],f"Transcribing passage {index+1}/{len(job['language_plan'])}: {passage['language']}")
            cropped = folder/f'passage-{pipeline}.wav'
            duration = self.decoder.crop(audio,cropped,passage['start'],passage['end'])
            raw = self.transcriber_for(job).transcribe(cropped,None if passage['language']=='auto' else passage['language'])
            output['passages'].append(dict(region=passage,response=raw))
            output['model_executed'] = output['model_executed'] or raw.get('model_executed',True)
            path.write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8')
            local, reordered = validate_model_segments(raw['segments'],duration)
            output['timestamp_order_normalized'] = output.get('timestamp_order_normalized', False) or reordered
            for segment in local:
                mapped = {**segment,'start':segment['start']+passage['start'],'end':segment['end']+passage['start']}
                if passage['language']!='auto':
                    mapped.update(language=passage['language'],language_source='user instruction')
                output['segments'].append(mapped)
            path.write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8')
            cropped.unlink(missing_ok=True)
        return output


def environment():
    packages = {}
    for name in ("fastapi", "faster-whisper", "ctranslate2", "demucs", "torch"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            pass
    return {"python": platform.python_version(), "platform": platform.platform(), "packages": packages}
