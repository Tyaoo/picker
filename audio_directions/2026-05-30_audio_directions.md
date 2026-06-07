#!/usr/bin/env python3
"""
Daily Security News Audio Director — Production Grade Module.

Provides validated data structures and processing for audio direction tables
used in the "每日安全资讯" video series. Designed for reliability, clarity,
and maintainability in a CI/CD production pipeline.

Usage:
    from audio_director import (
        AudioSegment,
        LevelMixing,
        create_segment,
        parse_timing,
        parse_db,
        load_segments_from_json,
    )
    segment = create_segment({...})  # validates input
    segments = load_segments_from_json("schedule.json")
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, TypeVar, Union

# ---------------------------------------------------------------------------
# Logging configuration (override via environment if needed)
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("audio_director")

# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------
class AudioDirectorError(Exception):
    """Base exception for audio director module."""

class ValidationError(AudioDirectorError):
    """Raised when input data fails validation."""

class ParsingError(AudioDirectorError):
    """Raised when parsing of a string value fails."""

class FileError(AudioDirectorError):
    """Raised when file reading or writing fails."""

# ---------------------------------------------------------------------------
# Type aliases & constants
# ---------------------------------------------------------------------------
TimeRange = Tuple[float, float]  # (start_seconds, end_seconds)
DecibelLevel = float             # dB, typically negative
JsonDict = Dict[str, Any]

VALID_DB_RANGE_MIN = -60.0
VALID_DB_RANGE_MAX = 0.0
DEFAULT_VOICE_DB = -6.0
DEFAULT_MUSIC_DB = -20.0
DEFAULT_SFX_DB = -10.0

ALLOWED_MUSIC_GENRES: frozenset = frozenset(
    {"loop", "theme", "alarm", "pulse", "pads", "pop", "hop"}
)
ALLOWED_SFX_CATEGORIES: frozenset = frozenset(
    {"sting", "whoosh", "ping", "click", "chime", "pop", "unlock", "keystroke", "cap", "book"}
)

_MIN_TRACK_NUMBER = 1
_MAX_TRACK_NUMBER = 999
_MAX_NAME_LENGTH = 128
_MAX_CONTENT_LENGTH = 4096

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LevelMixing:
    """Audio level settings for a segment.

    Attributes:
        voice_over_db: Voice-over volume in dB (default -6.0).
        music_db: Background music volume in dB (default -20.0).
        sound_effects_db: Sound effects volume in dB (default -10.0).
    """

    voice_over_db: DecibelLevel = DEFAULT_VOICE_DB
    music_db: DecibelLevel = DEFAULT_MUSIC_DB
    sound_effects_db: DecibelLevel = DEFAULT_SFX_DB

    def __post_init__(self) -> None:
        """Validate all dB levels are within acceptable range."""
        for name, val in [
            ("voice_over_db", self.voice_over_db),
            ("music_db", self.music_db),
            ("sound_effects_db", self.sound_effects_db),
        ]:
            if not (VALID_DB_RANGE_MIN <= val <= VALID_DB_RANGE_MAX):
                raise ValidationError(
                    f"{name} must be between {VALID_DB_RANGE_MIN} and "
                    f"{VALID_DB_RANGE_MAX} dB, got {val}"
                )

    def to_dict(self) -> Dict[str, float]:
        """Return a dictionary representation."""
        return {
            "voice_over_db": self.voice_over_db,
            "music_db": self.music_db,
            "sound_effects_db": self.sound_effects_db,
        }

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> LevelMixing:
        """Create LevelMixing from a dictionary, applying defaults for missing keys.

        Args:
            data: Dictionary with optional keys 'voice_over_db', 'music_db',
                  'sound_effects_db'. If None, returns default instance.

        Returns:
            LevelMixing instance.

        Raises:
            ValidationError: If any provided value is invalid.
        """
        if data is None:
            return cls()
        return cls(
            voice_over_db=parse_db(data.get("voice_over_db", cls.voice_over_db)),
            music_db=parse_db(data.get("music_db", cls.music_db)),
            sound_effects_db=parse_db(data.get("sound_effects_db", cls.sound_effects_db)),
        )


@dataclass(frozen=True)
class AudioSegment:
    """A single segment of the audio direction table.

    Attributes:
        track_number: Sequential number (1‑based).
        track_name: Human‑readable segment name.
        timing: (start, end) in seconds.
        voice_over_content: Script for voice‑over.
        background_music: Description of music track.
        sound_effects: Description of sound effects.
        level_mixing: Audio level parameters.
        notes: Optional production notes.
    """

    track_number: int
    track_name: str
    timing: TimeRange
    voice_over_content: str
    background_music: str
    sound_effects: str
    level_mixing: LevelMixing
    notes: Optional[str] = None

    def __post_init__(self) -> None:
        """Lightweight post‑init validation (heavy checks in factory)."""
        if not self.voice_over_content.strip():
            raise ValidationError("voice_over_content must not be empty")
        if not self.track_name.strip():
            raise ValidationError("track_name must not be empty")
        start, end = self.timing
        if start < 0 or end <= start:
            raise ValidationError(
                f"Invalid timing: start={start}, end={end}"
            )
        if self.track_number < 1:
            raise ValidationError(
                f"track_number must be >= 1, got {self.track_number}"
            )

    @property
    def duration(self) -> float:
        """Segment duration in seconds."""
        return self.timing[1] - self.timing[0]

    def to_dict(self) -> Dict[str, Any]:
        """Return a dictionary representation (suitable for JSON serialization)."""
        result: Dict[str, Any] = {
            "track_number": self.track_number,
            "track_name": self.track_name,
            "timing": self.timing,
            "voice_over_content": self.voice_over_content,
            "background_music": self.background_music,
            "sound_effects": self.sound_effects,
            "level_mixing": self.level_mixing.to_dict(),
        }
        if self.notes is not None:
            result["notes"] = self.notes
        return result


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

_TIME_PATTERN: re.Pattern = re.compile(
    r"^(?P<start_min>\d+):(?P<start_sec>\d+)(?:–|-)(?P<end_min>\d+):(?P<end_sec>\d+)$"
)

_DB_SUFFIX_PATTERN: re.Pattern = re.compile(
    r"^([-+]?\d+(?:\.\d+)?)\s*(?:db)?$", re.IGNORECASE
)
"""Matches optional 'dB' suffix (case‑insensitive) when parsing decibel strings."""


def parse_timing(timing_str: str) -> TimeRange:
    """Convert a timing string (e.g., '0:15–0:45') into (start_sec, end_sec).

    Args:
        timing_str: Timing in the format 'MM:SS–MM:SS'. Hyphen (‐) or en-dash (–) accepted.

    Returns:
        Tuple of (start_seconds, end_seconds).

    Raises:
        ValidationError: If the string does not match the expected pattern or if end <= start.
    """
    stripped = timing_str.strip()
    if not stripped:
        raise ValidationError("Timing string must not be empty")
    match = _TIME_PATTERN.match(stripped)
    if not match:
        raise ValidationError(
            f"Timing string '{timing_str}' does not match expected format 'MM:SS-MM:SS'"
        )
    start_min = int(match.group("start_min"))
    start_sec = int(match.group("start_sec"))
    end_min = int(match.group("end_min"))
    end_sec = int(match.group("end_sec"))

    start_total = start_min * 60 + start_sec
    end_total = end_min * 60 + end_sec

    if end_total <= start_total:
        raise ValidationError(
            f"End time {end_min}:{end_sec:02d} must be after start time "
            f"{start_min}:{start_sec:02d}"
        )

    logger.debug("Parsed timing '%s' -> (%.1f, %.1f)", timing_str, start_total, end_total)
    return (start_total, end_total)


def parse_db(value: Union[str, int, float]) -> DecibelLevel:
    """Parse a decibel value from string or number.

    Accepts formats: ``-6``, ``-6 dB``, ``-6.0``, ``-6.0dB``. If value is already
    a numeric type it is validated directly. Returns a float representing dB.

    Args:
        value: The decibel value to parse.

    Returns:
        DecibelLevel as float.

    Raises:
        ParsingError: If the string cannot be parsed.
        ValidationError: If the parsed value is out of range.
    """
    if isinstance(value, (int, float)):
        db = float(value)
    elif isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            raise ParsingError("Decibel string must not be empty")
        match = _DB_SUFFIX_PATTERN.match(stripped)
        if not match:
            raise ParsingError(f"Could not parse decibel value from '{value}'")
        db = float(match.group(1))
    else:
        raise ParsingError(f"Unsupported type for decibel value: {type(value).__name__}")

    if not (VALID_DB_RANGE_MIN <= db <= VALID_DB_RANGE_MAX):
        raise ValidationError(
            f"Decibel value {db} is outside valid range "
            f"[{VALID_DB_RANGE_MIN}, {VALID_DB_RANGE_MAX}]"
        )
    logger.debug("Parsed decibel value: %.1f dB", db)
    return db


# ---------------------------------------------------------------------------
# Factory functions
# ---------------------------------------------------------------------------

def _validate_track_number(track_number: int) -> int:
    """Validate track number is within allowed range.

    Args:
        track_number: Proposed track number.

    Returns:
        The same track number if valid.

    Raises:
        ValidationError: If out of range.
    """
    if not isinstance(track_number, int):
        raise ValidationError(f"track_number must be int, got {type(track_number).__name__}")
    if track_number < _MIN_TRACK_NUMBER or track_number > _MAX_TRACK_NUMBER:
        raise ValidationError(
            f"track_number must be between {_MIN_TRACK_NUMBER} and "
            f"{_MAX_TRACK_NUMBER}, got {track_number}"
        )
    return track_number


def _validate_name_or_content(value: str, field_name: str, max_length: int) -> str:
    """Validate a string field (name or content).

    Args:
        value: The string to validate.
        field_name: Name of the field for error messages.
        max_length: Maximum allowed length.

    Returns:
        The same string if valid.

    Raises:
        ValidationError: If empty, too long, or not a string.
    """
    if not isinstance(value, str):
        raise ValidationError(f"{field_name} must be a string, got {type(value).__name__}")
    stripped = value.strip()
    if not stripped:
        raise ValidationError(f"{field_name} must not be empty")
    if len(stripped) > max_length:
        raise ValidationError(
            f"{field_name} length ({len(stripped)}) exceeds maximum {max_length}"
        )
    return value


def create_segment(data: JsonDict) -> AudioSegment:
    """Create an AudioSegment from a validated dictionary.

    This factory function performs comprehensive validation and logging.

    Args:
        data: Dictionary with keys matching AudioSegment fields. Must include
              'track_number', 'track_name', 'timing' (string), 'voice_over_content',
              'background_music', 'sound_effects'. Optional: 'level_mixing' (dict)
              and 'notes'.

    Returns:
        AudioSegment instance.

    Raises:
        ValidationError: If required fields are missing or invalid.
        ParsingError: If timing or decibel strings cannot be parsed.
    """
    logger.debug("Creating segment from data: %s", {k: v for k, v in data.items() if k != 'voice_over_content'})

    # Required fields
    try:
        track_number = _validate_track_number(data["track_number"])
    except KeyError:
        raise ValidationError("Missing required field: 'track_number'")

    try:
        track_name = _validate_name_or_content(data["track_name"], "track_name", _MAX_NAME_LENGTH)
    except KeyError:
        raise ValidationError("Missing required field: 'track_name'")

    try:
        timing_str = data["timing"]
    except KeyError:
        raise ValidationError("Missing required field: 'timing'")

    # Parse timing
    timing = parse_timing(timing_str)

    try:
        voice_over_content = _validate_name_or_content(
            data["voice_over_content"], "voice_over_content", _MAX_CONTENT_LENGTH
        )
    except KeyError:
        raise ValidationError("Missing required field: 'voice_over_content'")

    try:
        background_music = _validate_name_or_content(
            data["background_music"], "background_music", _MAX_CONTENT_LENGTH
        )
    except KeyError:
        background_music = ""

    try:
        sound_effects = _validate_name_or_content(
            data["sound_effects"], "sound_effects", _MAX_CONTENT_LENGTH
        )
    except KeyError:
        sound_effects = ""

    # Level mixing
    level_mixing = LevelMixing.from_dict(data.get("level_mixing"))

    # Optional notes
    notes = data.get("notes")
    if notes is not None:
        notes = _validate_name_or_content(notes, "notes", _MAX_CONTENT_LENGTH)

    segment = AudioSegment(
        track_number=track_number,
        track_name=track_name,
        timing=timing,
        voice_over_content=voice_over_content,
        background_music=background_music,
        sound_effects=sound_effects,
        level_mixing=level_mixing,
        notes=notes,
    )
    logger.info("Created segment #%d: '%s' (%.1fs)", segment.track_number, segment.track_name, segment.duration)
    return segment


def load_segments_from_json(file_path: Union[str, Path]) -> List[AudioSegment]:
    """Load a list of audio segments from a JSON file.

    The JSON file should contain an array of segment objects (see create_segment
    for required fields).

    Args:
        file_path: Path to the JSON file.

    Returns:
        List of AudioSegment instances.

    Raises:
        FileError: If file does not exist or cannot be read.
        ValidationError: If JSON content is invalid.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileError(f"File not found: {path}")
    if not path.is_file():
        raise FileError(f"Path is not a file: {path}")

    logger.info("Loading segments from '%s'", path)

    try:
        with path.open("r", encoding="utf-8") as f:
            raw_data = json.load(f)
    except json.JSONDecodeError as e:
        raise FileError(f"Invalid JSON in '{path}': {e}") from e
    except OSError as e:
        raise FileError(f"Could not read '{path}': {e}") from e

    if not isinstance(raw_data, list):
        raise ValidationError(
            f"Expected JSON array of segment objects, got {type(raw_data).__name__}"
        )

    segments: List[AudioSegment] = []
    errors: List[str] = []
    for idx, item in enumerate(raw_data):
        if not isinstance(item, dict):
            errors.append(f"Item {idx}: expected dict, got {type(item).__name__}")
            continue
        try:
            segment = create_segment(item)
            segments.append(segment)
        except (ValidationError, ParsingError) as e:
            errors.append(f"Item {idx}: {e}")
            logger.warning("Skipped item %d due to error: %s", idx, e)

    if errors:
        logger.error("Encountered %d error(s) while loading segments", len(errors))
        # Optionally raise an exception if any errors? For now we log and continue.

    if not segments:
        raise ValidationError("No valid segments could be loaded from the file")

    logger.info("Successfully loaded %d segments from '%s'", len(segments), path)
    return segments


# ---------------------------------------------------------------------------
# Module exports
# ---------------------------------------------------------------------------
__all__ = [
    "AudioSegment",
    "LevelMixing",
    "create_segment",
    "parse_timing",
    "parse_db",
    "load_segments_from_json",
    "AudioDirectorError",
    "ValidationError",
    "ParsingError",
    "FileError",
]


# ---------------------------------------------------------------------------
# Entry point (for CLI usage)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys

    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <json_file>", file=sys.stderr)
        sys.exit(1)
    try:
        segments = load_segments_from_json(sys.argv[1])
        for s in segments:
            print(f"  #{s.track_number:3d} {s.track_name:40s} {s.timing[0]:6.1f}s - {s.timing[1]:6.1f}s")
        print(f"Total: {len(segments)} segments loaded successfully.")
    except (FileError, ValidationError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(2)