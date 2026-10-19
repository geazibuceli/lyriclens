"""Conservative project policy for declared training sources, not a legal certification."""
import hashlib
import re
from pathlib import Path

ALLOWED_LICENSES={'CC0-1.0','CC-BY-4.0','OWNED-CONSENT'}
SCOPES=('recording','lyrics','composition','performer','model_training','model_weight_distribution')


def validate_rights(row,manifest):
    if row.get('source_license') not in ALLOWED_LICENSES:
        raise ValueError('Training policy requires CC0-1.0, CC-BY-4.0 or OWNED-CONSENT; restrictive/unknown sources are excluded')
    review=row.get('rights_review',{})
    if (not isinstance(review,dict) or review.get('status')!='verified'
            or not isinstance(review.get('reviewed_by'),str) or not review['reviewed_by'].strip()
            or review.get('additional_terms') is not False):
        raise ValueError('A human rights review and explicit absence of additional source terms are required')
    if any(review.get(scope) is not True for scope in SCOPES):
        raise ValueError('Confirm recording, lyrics, composition, performer, training and weight-distribution rights separately')
    documents=review.get('evidence')
    if not isinstance(documents,list) or not 1<=len(documents)<=10:
        raise ValueError('Attach 1-10 local provenance/authorization evidence records')
    root=Path(manifest).resolve().parent
    for document in documents:
        if not isinstance(document,dict) or not isinstance(document.get('path'),str) or not re.fullmatch('[0-9a-f]{64}',str(document.get('sha256',''))):
            raise ValueError('Evidence records need a local relative path and SHA-256')
        relative=Path(document['path'])
        target=(root/relative).resolve()
        if relative.is_absolute() or not target.is_relative_to(root) or not target.is_file() or target.stat().st_size>10*1024*1024:
            raise ValueError('Rights evidence must be a local file within the manifest directory, at most 10 MiB')
        with target.open('rb') as handle:
            if hashlib.file_digest(handle,'sha256').hexdigest()!=document['sha256']:
                raise ValueError('Rights evidence changed; review it again before training')


def pending_rights():
    return dict(status='pending',reviewed_by='',additional_terms=None,
                **{scope:False for scope in SCOPES},evidence=[])


def prepare_original(audio,reference,output,identifier,language,group):
    import json
    import tempfile
    from .config import Settings,LANGUAGES
    from .adapters import FFmpegDecoder
    if output.exists():
        raise ValueError('Review queue already exists; use a new output name')
    if language not in LANGUAGES or not identifier.strip() or not group.strip():
        raise ValueError('Choose a supported language, clip ID and song/session group')
    text=reference.read_text(encoding='utf-8-sig').strip()
    if not text or len(text)>20000:
        raise ValueError('Provide the actual performed text, up to 20000 characters')
    with tempfile.TemporaryDirectory() as temp:
        info=FFmpegDecoder(Settings()).decode(audio,Path(temp)/'decoded.wav')
    if info['duration']>30:
        raise ValueError('Prepare an aligned original excerpt of at most 30 seconds; nothing was truncated')
    with audio.open('rb') as handle:
        audio_hash=hashlib.file_digest(handle,'sha256').hexdigest()
    row=dict(id=identifier,path=str(audio.resolve()),sha256=audio_hash,language=language,reference=text,
             reference_source=str(reference.resolve()),permissions='Pending original-contributor rights review',
             duration=info['duration'],conditions='Original recording; conditions need human review',
             language_switching=False,split='development',group_id=group,source_license='OWNED-CONSENT',
             training_allowed=False,training_permission='',rights_review=pending_rights(),
             review=dict(status='pending',reviewer='',listened=False,text_permission_checked=False))
    with output.open('x',encoding='utf-8') as handle:
        json.dump(dict(version=1,clips=[row]),handle,ensure_ascii=False,indent=2)
    return row


def main():
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('audio',type=Path)
    parser.add_argument('reference',type=Path)
    parser.add_argument('output',type=Path)
    parser.add_argument('--id',required=True)
    parser.add_argument('--language',required=True)
    parser.add_argument('--group',required=True)
    args=parser.parse_args()
    try:
        prepare_original(args.audio,args.reference,args.output,args.id,args.language,args.group)
        print('Original-recording review queue prepared. No rights or reference approval recorded; no training started.')
    except (OSError,ValueError) as exc:
        parser.error(str(exc))


if __name__=='__main__':main()
