"""Prepare explicitly licensed local research singing examples; never a runtime lyrics lookup.

Restricted recordings/references stay in ignored .runtime. Do not redistribute them with MIT code.
No model output is used to construct a reference. All examples are development diagnostics.
"""
import csv
import hashlib
import io
import json
import shutil
import urllib.request
import zipfile
from pathlib import Path
import fsspec
import soundfile as sf

REPO = Path(__file__).resolve().parents[2]
ROOT = REPO / ".runtime" / "singing-research"


def fetch(url,target):
    if not target.exists():
        with urllib.request.urlopen(url,timeout=90) as response:
            target.write_bytes(response.read())
    return target


def main():
    ROOT.mkdir(parents=True,exist_ok=True)
    rows=[]
    def add(identifier,language,target,reference,source,permissions,conditions,**extra):
        info=sf.info(target)
        if not 0 < info.duration <= 60:
            raise ValueError(f"{identifier}: duration outside the product limit")
        rows.append({"id":identifier,"path":target.name,"sha256":hashlib.sha256(target.read_bytes()).hexdigest(),
                     "language":language,"reference":reference,"reference_source":source,"permissions":permissions,
                     "duration":info.duration,"conditions":conditions,"language_switching":False,
                     "split":"development","content_type":"singing","research_only":True,**extra})
        (ROOT/"manifest.jsonl").write_text("\n".join(json.dumps(r,ensure_ascii=False) for r in rows)+"\n",encoding="utf-8")
        print(f"Prepared {identifier}: {info.duration:.2f}s",flush=True)
    archive=REPO/".runtime"/"vocadito.zip"
    fetch("https://zenodo.org/api/records/5578807/files/vocadito.zip/content",archive)
    if hashlib.md5(archive.read_bytes()).hexdigest()!="dea40fd18f14d899643c4ba221b33a46":
        raise ValueError("vocadito archive checksum mismatch")
    with zipfile.ZipFile(archive) as z:
        metadata=list(csv.DictReader(io.StringIO(z.read("vocadito_metadata.csv").decode("utf-8"))))
        for number,language in [(6,"en"),(10,"en"),(13,"fr"),(23,"fr"),(2,"es"),(35,"zh"),(36,"zh")]:
            name=next(n for n in z.namelist() if n.endswith(f"/vocadito_{number}.wav") and not n.startswith("__MACOSX"))
            target=ROOT/f"vocadito-{number}.wav"
            target.write_bytes(z.read(name))
            original=z.read(f"Annotations/Lyrics/vocadito_{number}_lyrics.txt").decode("utf-8-sig")
            reference=original.split("----")[-1].strip() if language=="zh" else original.strip()
            if language=="zh" and not any('\u4e00'<=c<='\u9fff' for c in reference):
                raise ValueError("Mandarin evaluation needs the supplied character reference, not pinyin")
            singer=next(r["singer_id"] for r in metadata if int(r["track_id"])==number)
            add(f"vocadito-{number}",language,target,reference,
                "Bittner et al., vocadito v3, DOI 10.5281/zenodo.5578807; trained-musician lyric annotation",
                "CC-BY-4.0; Bittner, Pasalo, Bosch, Meseguer Brocal and Rubinstein (2021)",
                "Solo unaccompanied natural singing; original recording retained",singer=singer,
                reference_original=original,reference_selection="Supplied Chinese-character section after separator" if language=="zh" else "Supplied lyric file unchanged")
    url="https://zenodo.org/api/records/4785016/files/CSD.zip/content"
    with fsspec.open(url,"rb",block_size=1024*1024) as remote:
        with zipfile.ZipFile(remote) as z:
            collected=0
            for number in range(2,16):
                identifier=f"kr{number:03}a"
                target=ROOT/f"csd-{identifier}.wav"
                target.write_bytes(z.read(f"CSD/korean/wav/{identifier}.wav"))
                if sf.info(target).duration>60:
                    print(f"Skipping overlength CSD clip {identifier}",flush=True)
                    continue
                reference=z.read(f"CSD/korean/lyric/{identifier}.txt").decode("utf-8-sig").strip()
                add(f"csd-{identifier}","ko",target,reference,
                    "Choi et al., CSD v1.0, DOI 10.5281/zenodo.4785016, supplied grapheme lyric file",
                    "CC-BY-NC-SA-4.0; KAIST Music and Audio Computing Lab; local noncommercial research only",
                    "Professional solo singing, plain delivery; original WAV retained; provider annotation",
                    singer="CSD single singer",song_id=identifier[:-1])
                collected+=1
                if collected==2:
                    break
    # The study's Supporting Text S1 supplies these exact folk-song phrases, independently of ASR.
    portuguese=[
        ("S07_NR_pop_L", "677e6b32ba58e59c5c44a724", "Se esta rua, se esta rua fosse minha"),
        ("S09_NR_pop_L", "677e6b36d8d57af84d2b4d50", "Se esta rua, se esta rua fosse minha"),
        ("S05_AL_cl_L", "677e6b1d672f7472f7d10117", "Alecrim, alecrim dourado que nasceu no campo sem ser semeado")]
    for identifier,file_id,reference in portuguese:
        target=ROOT/f"covox-{identifier}.wav"
        fetch(f"https://files.osf.io/v1/resources/cgexn/providers/osfstorage/{file_id}",target)
        add(f"covox-{identifier}","pt",target,reference,
            "Bruder and Larrouy-Maestri, CoVox (2025), DOI 10.3758/s13428-025-02664-9, Supplementary Supporting Text S1 and matching stimulus melody code",
            "Private noncommercial research; OSF root declares CC-BY-NC-ND-4.0, recording README states CC-BY-NC-SA; no media, references or derived transcripts redistributed",
            "Brazilian Portuguese solo singing; _L means lyrics, pop/cl are pop/operatic; study loudness-normalized audio retained unchanged",
            singer=identifier.split('_')[0],source_file_id=file_id)
    # Both official PJS downloads may be quota-limited; never treat an HTML response as audio.
    japanese=REPO/".runtime"/"pjs-corpus.zip"
    if japanese.exists() and zipfile.is_zipfile(japanese):
        with zipfile.ZipFile(japanese) as z:
            name=next(n for n in z.namelist() if n.lower().endswith("pjs056_song.wav"))
            target=ROOT/"pjs056.wav"
            target.write_bytes(z.read(name))
            add("pjs056","ja",target,"ところが、エリュシクトーンは、ニュムペーの制止も聞かずに、デーメーテールの樫を切り倒した",
                "Koguchi and Takamichi, PJS official project page, explicitly supplied singing sample 056 and displayed reference sentence",
                "CC-BY-SA-4.0; Junya Koguchi and Shinnosuke Takamichi",
                "Original composed Japanese phoneme-balanced song; no accompaniment; sample 056")
    (ROOT/"manifest.jsonl").write_text("\n".join(json.dumps(r,ensure_ascii=False) for r in rows)+"\n",encoding="utf-8")
    covered=sorted({r["language"] for r in rows})
    print(json.dumps({"clips":len(rows),"languages":covered,"missing":sorted(set(['ko','ja','zh','en','es','pt','fr'])-set(covered)),"manifest":str(ROOT/'manifest.jsonl')},indent=2),flush=True)


if __name__=="__main__":
    main()
