"""Shared annotation type definitions for Prototype Annotator scripts."""

from __future__ import annotations

import json
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
ANNOTATION_TYPES_PATH = SKILL_DIR / "references" / "annotation-types.json"


def load_annotation_types() -> dict:
    return json.loads(ANNOTATION_TYPES_PATH.read_text(encoding="utf-8"))


_CONFIG = load_annotation_types()

VALID_ANNOTATION_TYPES = set(_CONFIG["annotationTypes"])
ANNOTATION_TYPE_BY_DIMENSION = dict(_CONFIG["annotationTypeByDimension"])
TOPICS_BY_DIMENSION = {
    str(dimension): [str(topic) for topic in topics]
    for dimension, topics in _CONFIG["topicsByDimension"].items()
}
