"""Read-only environment diagnostics and strictly scoped generated-cache cleanup."""
import importlib.util
import os
import shutil
import stat
from pathlib import Path
from .profiles import available_profiles

CACHE_NAMES = ('decoded.wav','vocals-16k.wav','region-16k.wav','passage-direct.wav','passage-vocals.wav','stems')


def linked(path):
    return path.is_symlink() or bool(getattr(path.lstat(), 'st_file_attributes', 0) & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0))


def files(path):
    if not path.exists():
        return []
    if linked(path):
        raise ValueError('Linked files/directories are excluded from storage operations')
    if path.is_file():
        return [path]
    result = []
    for folder, directories, names in os.walk(path, followlinks=False):
        for name in directories + names:
            if linked(Path(folder)/name):
                raise ValueError('Linked files/directories are excluded from storage operations')
        result.extend(Path(folder)/name for name in names)
    return result


def size(path):
    return sum(item.stat().st_size for item in files(path))


def folder_for(settings, identifier):
    root = settings.root/'jobs'
    folder = root/identifier
    if folder.resolve().parent != root.resolve() or (root.exists() and linked(root)) or (folder.exists() and linked(folder)):
        raise ValueError('Job directory is outside managed storage')
    return folder


def storage(settings, jobs):
    entries = []
    for job in jobs:
        try:
            folder = folder_for(settings, job['id'])
            total = size(folder)
            cache = sum(size(folder/name) for name in CACHE_NAMES)
            entries.append(dict(id=job['id'], filename=job['filename'], bytes=total, cache_bytes=cache,
                                active=job['state'] in {'queued','processing'} or any(t['state'] in {'queued','processing'} for t in job.get('translations',{}).values())))
        except (OSError, ValueError):
            entries.append(dict(id=job['id'], filename=job['filename'], bytes=None, cache_bytes=None,
                                error='Storage unavailable or linked files excluded'))
    models = {}
    for name in ('models','separation-models','translation-models'):
        try:
            models[name] = size(settings.root/name)
        except (OSError, ValueError):
            models[name] = None
    return dict(jobs=entries, models=models, free_bytes=shutil.disk_usage(settings.root).free,
                note='Managed data only; Python/Node dependencies, external evaluation audio and logs are excluded. Models are read-only here.')


def cleanup(settings, identifier):
    folder = folder_for(settings, identifier)
    targets = [folder/name for name in CACHE_NAMES if (folder/name).exists()]
    # Validate every target before removing anything. Originals/raw/SQLite are never selected.
    selected = []
    for target in targets:
        if target.resolve().parent != folder.resolve():
            raise ValueError('Cache target is outside its job directory')
        selected.extend(files(target))
    removed = 0
    for item in selected:
        amount = item.stat().st_size
        item.unlink()
        removed += amount
    for target in targets:
        if target.is_dir():
            for root, directories, _ in os.walk(target, topdown=False):
                for directory in directories:
                    (Path(root)/directory).rmdir()
            target.rmdir()
    return dict(removed_bytes=removed)


def diagnostics(settings):
    checks = [dict(name='FFmpeg', ok=shutil.which(settings.ffmpeg) is not None,
                   detail='Audio decoder found' if shutil.which(settings.ffmpeg) else 'Install FFmpeg or configure LYRICLENS_FFMPEG and restart')]
    for module, name in [('faster_whisper','Recognition dependencies'), ('demucs','Optional vocal separation dependencies')]:
        ready = importlib.util.find_spec(module) is not None
        checks.append(dict(name=name, ok=ready, detail='Installed' if ready else 'Install the corresponding optional dependencies in the setup guide'))
    for profile in available_profiles(settings):
        checks.append(dict(name=profile['label'], ok=profile['prepared'],
                           detail='Local checkpoint prepared' if profile['prepared'] else 'Prepare this model explicitly using the setup guide'))
    checks.append(dict(name='Vocal separation checkpoint', ok=(settings.root/'separation-models'/'955717e8-8726e21a.th').exists(),
                       detail='Optional; needed only for isolated vocals'))
    from .translation import prepared
    translation_dependencies = all(importlib.util.find_spec(module) is not None for module in ('ctranslate2','transformers','sentencepiece'))
    checks.append(dict(name='Optional translation',ok=translation_dependencies and prepared(settings),
                       detail='Local dependencies and checkpoint ready' if translation_dependencies and prepared(settings) else 'Install optional translation dependencies and explicitly prepare the translation checkpoint'))
    try:
        from .adapters import prepare_cuda_libraries
        if settings.device == 'cuda':
            prepare_cuda_libraries()
        import ctranslate2
        supported = sorted(ctranslate2.get_supported_compute_types(settings.device))
        ok = settings.compute_type in supported or settings.compute_type in {'default','auto'}
        checks.append(dict(name='Recognition device', ok=ok,
                           detail=f'{settings.device}/{settings.compute_type}; supported compute types: {", ".join(supported)}. This does not load a model or prove GPU memory capacity.'))
    except Exception:
        checks.append(dict(name='Recognition device', ok=False,
                           detail=f'Cannot initialize {settings.device}/{settings.compute_type}. Check installed runtime, GPU drivers and compute settings, then restart. No automatic device fallback.'))
    return dict(checks=checks, device=settings.device, compute_type=settings.compute_type,
                note='Read-only checks; no model inference, installation or download. Optional features can be unavailable while direct recognition works.')
