# Conservative training-source selection

The project now prioritizes original contributor recordings with documented permissions. GTSinger is excluded from this selection: no corpus was downloaded, no acceptance was recorded and no GTSinger training is enabled. Historical CSD/CoVox research diagnostics remain separate from training. Existing files are not deleted or relicensed.

The machine-readable shortlist is [training-sources.json](../evaluation/training-sources.json). It is a source inventory, not permission to train.

## Sources and current status

| Source | Training status | Reason |
|---|---|---|
| Original recordings/compositions/lyrics | Preferred, pending actual recordings and written permissions | A contributor must control the relevant rights; a cover is not automatically an original composition |
| CC0 / CC BY 4.0 datasets | Candidates only after component-rights review | The license must come from an authorized party and cover the intended material/use |
| vocadito v3 | Pending component-rights verification | Zenodo's official API declares CC BY 4.0; the local ZIP does not independently establish permissions for every underlying composition |
| GTSinger | Excluded | Noncommercial/share-alike license plus additional agreement |
| CSD | Excluded from this training selection | Noncommercial/share-alike source; previous diagnostics are not training authorization |
| CoVox | Excluded | Previously recorded license discrepancy |
| Songs uploaded to the application | Excluded without specific rights evidence | Possession/upload of audio does not itself establish permission for training and weight distribution |

The vocadito metadata was checked on 2026-10-16 at [the official record API](https://zenodo.org/api/records/5578807). Its declared license is recorded, not treated as a guarantee that all component rights are cleared. No new third-party audio was downloaded for this selection.

## What the training gate checks

Alongside existing human reference review, training permission and split-isolation checks, the trainer now requires:

- `source_license` equal to `CC0-1.0`, `CC-BY-4.0` or `OWNED-CONSENT`.
- `rights_review.status: verified`, a nonempty human `reviewed_by`, and `additional_terms: false`.
- Separate positive confirmations for recording, lyrics, composition, performer, model training and intended model-weight distribution.
- One to ten local evidence files, each with a matching SHA-256. Files must be within the manifest directory and no larger than 10 MiB each.

This is a deliberately conservative project policy. It does not decide legal ownership, detect false declarations, create an authorization or guarantee that a dataset/model can be distributed. MIT describes the application's source code; it does not relicense audio, lyrics, compositions, dataset annotations or trained weights. Do not set review fields to true unless the evidence actually supports them. Permission for a singer's performance may not cover a third party's composition or lyrics.

`rights_review` is part of the reference annotation fingerprint. Changing declared rights, evidence hashes or other annotation fields invalidates an earlier review. Changing an evidence file without updating its recorded hash blocks training. A model cannot be automatically promoted by passing these checks.

## Prepare original examples

The [original recording prompts](../evaluation/original-recording-prompts.example.json) are newly authored sample text for English/Portuguese collection, not references for existing songs or an annotated dataset. They do not supply a recording, melody, participant consent, guaranteed uniqueness or human verification. Record an original melody/performance without third-party backing music, and write the words actually sung. Include other languages only with appropriate language review.

Prepare an aligned excerpt of at most 30 seconds and its transcript:

```powershell
.\.venv311\Scripts\python.exe -m lyriclens.training_rights original.wav performed-text.txt .runtime/original-training-review.json --id original-001 --language en --group original-song-session-001
```

This checks the audio with FFmpeg, hashes the original, and creates a new review queue with all approvals **pending** and training disabled. It neither changes the recording nor synthesizes reference lyrics. Existing queues are not overwritten. Add subsequent curated examples to the queue without replacing earlier annotations; the existing benchmark exporter validates unique IDs and splits.

Use [rights-review.example.json](../evaluation/rights-review.example.json) as a field template. Keep written source/participant permissions and license records locally, for example in `.runtime/permissions/`. Capture who controls the recording, lyrics/composition and performance, which uses are authorized, any restrictions, and applicable dates/identifiers. This field template is not a legal contract. For public model distribution or commercial plans, obtain advice appropriate to the actual rights and jurisdiction.

After a human has checked the documents, update `rights_review` with the relevant confirmations and evidence path/hash, set `training_allowed` and the specific `training_permission`, and complete reference review through [BENCHMARK.md](BENCHMARK.md). Keep the review queue, exported manifest and relative evidence paths under the same directory, or update paths and re-review after moving them. Evidence documents, identities and recordings stay private and are not bundled into Git or uploaded automatically.

Until these checks are complete, the correct result is **no eligible training samples**, not silently using a more restrictive dataset. The prepared CUDA environment/base model remain available for a later authorized training run. No new singing-quality improvement is claimed.

Official references: [MIT](https://opensource.org/license/mit), [CC0](https://creativecommons.org/publicdomain/zero/1.0/), [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/), [GTSinger terms](https://github.com/AaronZ345/GTSinger/blob/main/dataset_license.md). Open licenses do not eliminate every possible voice/privacy/third-party-rights issue.
