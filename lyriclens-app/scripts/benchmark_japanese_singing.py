"""Natural Japanese singing execution diagnostic, without inventing a lyric reference.

The official HTS archive supplies phoneme labels, not an orthographic transcript.
These runs intentionally have no CER/WER and do not establish recognition quality.
"""
import hashlib
import argparse
import json
import tarfile
import tempfile
import time
import wave
from dataclasses import replace
from pathlib import Path

from lyriclens.adapters import FFmpegDecoder, WhisperTranscriber, DemucsSeparator
from lyriclens.config import Settings
from lyriclens.domain import validate_model_segments
from lyriclens.profiles import profile_settings, PROFILE_IDS


def main():
    repo = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profiles', nargs='+', choices=PROFILE_IDS, default=['configured', 'large-v3'])
    parser.add_argument('--output', type=Path, default=repo/'lyriclens-app/evaluation/japanese-singing-smoke.json')
    parser.add_argument('--raw-directory', type=Path, default=repo/'.runtime/singing-research')
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Output already exists; choose a new --output to preserve previous evidence')
    root = args.raw_directory
    root.mkdir(parents=True, exist_ok=True)
    if list(root.glob('japanese-*-raw.json')):
        parser.error('Raw outputs already exist; choose a new --raw-directory')
    clips = []
    with tarfile.open(repo / '.runtime' / 'hts-japanese.tar.bz2') as archive:
        for number in ['003', '004']:
            stem = f'HTS-demo_NIT-SONG070-F001/data/raw/nitech_jp_song070_f001_{number}'
            original = archive.extractfile(stem + '.raw').read()
            target = root / f'nit-song070-{number}.wav'
            with wave.open(str(target), 'wb') as output:
                output.setnchannels(1)
                output.setsampwidth(2)
                output.setframerate(48000)
                output.writeframes(original)
            clips.append((number, target, len(original) / 96000))
    reports = []
    for profile in args.profiles:
        settings = replace(profile_settings(Settings(), profile), device='cuda', compute_type='float16')
        decoder, model, separator = FFmpegDecoder(settings), WhisperTranscriber(settings), DemucsSeparator(settings)
        try:
            for number, target, duration in clips:
                for pipeline in ['direct', 'vocals']:
                    print(f'Running Japanese {number}: {profile}/{pipeline}', flush=True)
                    row = dict(id=f'nit-song070-{number}', language='ja', profile=profile,
                               model=settings.model_id, revision=settings.revision, pipeline=pipeline,
                               sha256=hashlib.sha256(target.read_bytes()).hexdigest(), duration=duration,
                               settings=settings.inference(), cer=None, wer=None,
                               source='https://hts.sp.nitech.ac.jp/archives/2.3/HTS-demo_NIT-SONG070-F001.tar.bz2',
                               permissions='CC-BY-3.0; Nagoya Institute of Technology, Department of Computer Science (2004-2015), data/COPYING',
                               audio_transformation='Original mono 48kHz signed little-endian PCM16 wrapped in WAV without resampling before app decode',
                               quality_status='Not scored: source supplies phoneme labels, no independently checked orthographic reference')
                    started = time.perf_counter()
                    try:
                        with tempfile.TemporaryDirectory() as tmp:
                            folder = Path(tmp)
                            decoded = folder / 'decoded.wav'
                            info = decoder.decode(target, decoded)
                            audio = decoded
                            if pipeline == 'vocals':
                                audio = folder / 'vocals.wav'
                                decoder.decode(separator.separate(decoded, folder / 'stems'), audio)
                            raw = model.transcribe(audio, 'ja')
                            (root / f'japanese-{profile}-{number}-{pipeline}-raw.json').write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding='utf-8')
                            segments, reordered = validate_model_segments(raw['segments'], info['duration'])
                            row.update(state='completed', segments=len(segments), timestamp_order_normalized=reordered,
                                       timing_recovery={k:v for k,v in raw.get('timing_recovery', {}).items() if k != 'initial_response'} or None)
                    except Exception as exc:
                        row.update(state='failed', error=str(exc))
                    row['seconds'] = time.perf_counter() - started
                    reports.append(row)
        finally:
            separator.close()
            del model
    args.output.write_text(json.dumps(reports, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
