# Diagnose recognition mistakes

Wrong words, omitted vocals and inaccurate timing are recognition problems even
when a job completes successfully. A completed status does not certify lyrics.

## Compare before correcting

1. Select the language actually sung instead of relying on whole-clip detection
   when you know it. Do not force one language onto a multilingual recording;
   use the existing passage-language workflow for that case.
2. The upload page shows the selected model and listening route above the
   advanced controls. **Try Large-v3 + compare vocals** selects the prepared
   Large-v3 profile and both original/separated audio when separation is ready.
   If separation is unavailable, it selects original audio only. The experimental
   gap protection below is independent and is not enabled by the shortcut.
3. Compare original audio and isolated vocals while listening. Separation can
   improve intelligibility or damage a voice; neither route is always better.
   Larger models use more memory and processing time and can still make mistakes.
4. Keep the original result. New recognition jobs do not replace its edits.

## Experimental gap protection

For words invented over melody-only sections, **Filter instrumental sections**
selects isolated vocals and enables protection below. It prefers prepared
Large-v3, then aligned Small, then the configured model. The shortcut is disabled
when vocal separation or a recognition model is unavailable.

**Reduce suspected hallucinations around instrumental gaps** is off by default
and can be switched independently of the model. It enables native word
timestamps and sets `hallucination_silence_threshold=2.0` in faster-whisper.
Check it explicitly to try it; uncheck it to compare without it.
The setting is sent for single uploads and batches, recorded in job provenance,
and inherited by passage retries unless explicitly changed.

It also enables conservative Silero voice activity detection: threshold 0.1,
ten seconds of detected silence before splitting, and three seconds of context
padding. The recognizer restores timestamps to the original audio timeline.
This is a speech detector, not a validated singing classifier; accompaniment
can trigger false detections, and isolated vocals may behave differently.
It can omit legitimate sung words, especially unusual or sustained singing.
If a passage is missing, compare with protection off. Do not use it as evidence
that remaining words are correct.

See the [pinned faster-whisper implementation](https://github.com/SYSTRAN/faster-whisper/blob/v1.2.1/faster_whisper/transcribe.py)
for the native option and word-anomaly checks. Existing jobs retain their original
settings and output; no text is removed from saved transcripts by this change.

## Repair a particular passage

Open the passage retranscription panel. The language initially follows the
recognized/result language. **Retry model** allows a prepared model override
instead of always reusing the original checkpoint. Selecting an unprepared
override is rejected before a new job is created; no model is downloaded by a
request. The default **Same model as this result** preserves existing behavior.

Choose the passage and language, select a model, decide whether gap protection
is appropriate, and click **Retranscribe passage**. Recognition includes two
seconds of surrounding audio and uses the original recording's timeline. It
creates a separate result and preserves the source recording and edits.

For a full retry, **Run again with a different language or mode** restores the
job's language, route, model and gap-protection setting in the upload form.
Change only the options you want to compare.

## Measure quality honestly

Compare the words actually sung against a human-reviewed reference, including
refrains and incomplete phrases. A different transcript, fewer repetitions or
more segments is not proof of higher accuracy. Use the
[real-song collection workflow](REAL_SONG_COLLECTION.md) for representative
paired evaluation; report transcription and timing quality separately.
