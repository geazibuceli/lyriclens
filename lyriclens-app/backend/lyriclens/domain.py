import math
from typing import Literal, Annotated
from pydantic import BaseModel, Field, model_validator, model_serializer


class Segment(BaseModel):
    start: float = Field(ge=0, allow_inf_nan=False)
    end: float = Field(gt=0, allow_inf_nan=False)
    text: str = Field(max_length=20000)
    language: Literal['ko','ja','zh','en','es','pt','fr'] | None = None
    language_source: Literal['user instruction'] | None = None

    @model_serializer(mode='wrap')
    def serialize(self, handler):
        return {key: value for key, value in handler(self).items() if value is not None}

    @model_validator(mode="after")
    def order(self):
        if self.start >= self.end:
            raise ValueError("Segment start must precede end")
        return self


class Edit(BaseModel):
    pipeline: Literal["direct", "vocals"]
    segments: list[Segment] = Field(max_length=1000)


class RenameJob(BaseModel):
    title: str = Field(max_length=200)


class Retranscribe(BaseModel):
    language: str
    pipeline: Literal["direct", "vocals", "both"] = "direct"
    start: float = Field(ge=0, allow_inf_nan=False)
    end: float = Field(gt=0, allow_inf_nan=False)
    context_seconds: float = Field(default=2, ge=0, le=10, allow_inf_nan=False)

    @model_validator(mode="after")
    def order(self):
        if self.start >= self.end:
            raise ValueError("Region start must precede end")
        return self


class TranslationRequest(BaseModel):
    pipeline: Literal['direct', 'vocals'] = 'direct'
    source_language: str
    target_language: str


class MultilingualRequest(BaseModel):
    pipeline: Literal['direct','vocals'] = 'direct'
    default_language: str = 'auto'


class TranslationEdit(BaseModel):
    pipeline: Literal['direct', 'vocals'] = 'direct'
    target_language: str
    texts: list[Annotated[str, Field(max_length=20000)]] = Field(max_length=1000)


def validate_segments(segments, duration):
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("Invalid audio duration")
    result = [Segment.model_validate(s).model_dump(exclude_none=True) for s in segments]
    previous = -1.0
    for s in result:
        if s["end"] > duration or s["start"] < previous:
            raise ValueError("Timestamps must be ordered and within the original clip")
        previous = s["start"]
    return result


def validate_model_segments(segments, duration):
    # Validate bounds and finite values before sorting; preserve overlaps and times.
    checked = [validate_segments([segment], duration)[0] for segment in segments]
    ordered = sorted(checked, key=lambda segment: segment['start'])
    return validate_segments(ordered, duration), ordered != checked


def text_of(segments):
    return "\n".join(s["text"] for s in segments)


def lrc(segments):
    lines = []
    for segment in segments:
        centiseconds = round(segment['start'] * 100)
        stamp = f"[{centiseconds // 6000:02}:{centiseconds // 100 % 60:02}.{centiseconds % 100:02}]"
        # Every line of a merged passage shares its passage start time.
        lines.extend(stamp + line.strip() for line in segment['text'].splitlines() if line.strip())
    return '\n'.join(lines) + ('\n' if lines else '')


def srt(segments):
    def stamp(value):
        ms = round(value * 1000)
        return f"{ms // 3600000:02}:{ms // 60000 % 60:02}:{ms // 1000 % 60:02},{ms % 1000:03}"
    return "\n\n".join(f"{i}\n{stamp(s['start'])} --> {stamp(s['end'])}\n{s['text']}" for i, s in enumerate(segments, 1)) + "\n"
