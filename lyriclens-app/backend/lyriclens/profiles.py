"""Explicit multilingual model choices; preparation never happens in an HTTP request."""
from dataclasses import replace

LARGE_MODEL = "Systran/faster-whisper-large-v3"
LARGE_REVISION = "edaa852ec7e145841d8ffdb056a99866b5f0a478"


def profile_settings(settings, profile):
    if profile == "configured":
        return settings
    if profile == "large-v3":
        return replace(settings, model_id=LARGE_MODEL, revision=LARGE_REVISION, word_timestamps=True)
    raise ValueError("Unknown recognition model profile")


def available_profiles(settings):
    return [{"id":name,"label":label,"model_id":selected.model_id,"revision":selected.revision,
             "prepared":(selected.model_dir/"READY.json").exists(),
             "note":note}
            for name,label,note in [
                ("configured","Whisper Small (lighter)" if settings.model_id=="Systran/faster-whisper-small" else "Configured model","Uses the server-configured model and device."),
                ("large-v3","Whisper Large-v3 (experimental)","Larger multilingual model with native word alignment for segment timing; more memory and processing time. Singing accuracy varies.")]
            for selected in [profile_settings(settings,name)]]
