# Training sources and permissions

Training uses original contributor recordings with documented permission. This guide covers source selection, licensing and the review required before training.

The [source inventory](../evaluation/training-sources.json) tracks candidates and their review status.

## Sources and current status

| Source | Training status | Reason |
|---|---|---|
| Original recordings/compositions/lyrics | Preferred; recordings and written permissions pending | Permission must cover the recording, composition, lyrics and performance |
| CC0 / CC BY 4.0 datasets | Candidates only after component-rights review | The license must come from an authorized party and cover the intended material/use |
| vocadito v3 | Pending component-rights verification | CC BY 4.0 metadata; underlying composition rights still need review |
| GTSinger | Excluded | Noncommercial/share-alike license plus additional agreement |
| CSD | Excluded | Noncommercial/share-alike terms |
| CoVox | Excluded | Previously recorded license discrepancy |
| Songs uploaded to the application | Separate permission required | Training permission must cover the audio, reference text and weight distribution |

vocadito's [official record](https://zenodo.org/api/records/5578807), checked on 2026-10-16, lists CC BY 4.0. Component rights still need review before training.

## What the training gate checks

Training requires reviewed references, separate training/validation groups, documented training permission and:

- `source_license` equal to `CC0-1.0`, `CC-BY-4.0` or `OWNED-CONSENT`.
- `rights_review.status: verified`, a nonempty human `reviewed_by`, and `additional_terms: false`.
- Separate positive confirmations for recording, lyrics, composition, performer, model training and intended model-weight distribution.
- One to ten local evidence files, each with a matching SHA-256. Files must be within the manifest directory and no larger than 10 MiB each.

Record permission for the audio, lyrics, composition, performance, training and intended weight distribution. These permissions are separate from the MIT license for the application code.

`rights_review` is included in the annotation fingerprint. Changes to annotations or evidence require a new review; evidence files must match their recorded hashes. Model installation is a separate step.

## Prepare original examples

Use the [English and Portuguese recording prompts](../evaluation/original-recording-prompts.example.json) to collect examples. Record an original melody and performance, then transcribe the words actually sung. Each recording needs participant permission and reference review. Add other languages with a fluent reviewer.

Prepare an aligned excerpt of at most 30 seconds and its transcript:

```powershell
.\.venv311\Scripts\python.exe -m lyriclens.training_rights original.wav performed-text.txt .runtime/original-training-review.json --id original-001 --language en --group original-song-session-001
```

The command checks the audio with FFmpeg, hashes the file and creates a review queue with approvals pending. Use a new output path for each queue. The benchmark exporter checks unique IDs and split assignments when combining reviewed examples.

Use [rights-review.example.json](../evaluation/rights-review.example.json) to record rights holders, authorized uses, restrictions and supporting documents. Store written permissions and license records locally, for example under `.runtime/permissions/`.

After a human has checked the documents, update `rights_review` with the relevant confirmations and evidence path/hash, set `training_allowed` and the specific `training_permission`, and complete reference review through [BENCHMARK.md](BENCHMARK.md). Keep the review queue, exported manifest and relative evidence paths under the same directory, or update paths and re-review after moving them. Evidence documents, identities and recordings stay private and are not bundled into Git or uploaded automatically.

Training starts once the samples have passed reference and permission review.

License references: [MIT](https://opensource.org/license/mit), [CC0](https://creativecommons.org/publicdomain/zero/1.0/), [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) and [GTSinger terms](https://github.com/AaronZ345/GTSinger/blob/main/dataset_license.md).
