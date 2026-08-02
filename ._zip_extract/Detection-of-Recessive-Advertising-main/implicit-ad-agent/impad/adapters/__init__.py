"""Input normalization into the stable runtime PostRecord."""

from .manual import post_record_from_manual
from .p1_schema import post_record_from_content_record

__all__ = [
    "post_record_from_content_record",
    "post_record_from_manual",
]
