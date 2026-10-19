# Multilingual songs and transcript comparison

For a song with two or more of the seven supported languages:

1. Transcribe the recording normally and review the saved segment boundaries.
2. Choose the language in each segment's language selector. Split segments at language changes and adjust their start/end times as needed.
3. Save the transcript edits.
4. Select **Retranscribe saved multilingual passages**. At least two different language labels are required.

Recognition creates a new job using the same original recording, model revision and settings. Each saved interval is cropped and recognized with its specified language, then mapped back to the original timeline. Unlabeled segments use automatic language selection for that interval. Overlapping intervals are rejected. Gaps between saved intervals are omitted, so extend the intervals if they contain words you want recognized. The original job and its edits remain available.

Language labels are user instructions, not verified automatic language detection. A segment containing multiple languages should be split at the language change. Accuracy still depends on the recording and recognition model; no lower character error rate is guaranteed.

Translation respects saved segment languages. The translation source selector supplies the fallback for unlabeled segments. Segments already in the target language are copied unchanged; the remaining segments are translated. Changing a saved language label makes an earlier translation stale, just like changing its source text.

When both recognition routes finish, **Compare saved transcripts** groups segments by overlapping times and marks differing text. Toggle **Show only differences** to include matching passages. The comparison uses saved text and does not choose a correct answer. Different segmentation can itself produce a difference. Very long comparisons mark entire passages to bound memory use.

API: `POST /api/jobs/{id}/retranscribe-multilingual` accepts `pipeline` (`direct` or `vocals`) and `default_language` (a supported language or `auto`). Set optional `language` on segments through the existing edit endpoint before creating the job. New jobs expose `source_job_id`, `source_fingerprint`, `language_plan` and its method; raw responses retain individual passage outputs before timestamp validation.
