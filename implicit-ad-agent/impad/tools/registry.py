"""Stable P2 tool registry and readiness metadata."""
from .comment_anomaly import comment_anomaly
from .detect_logo_product import detect_logo_product
from .image_text_consistency import image_text_consistency
from .ocr_extract import ocr_extract
from .sentiment import sentiment_curve
from .text_intent import analyze_text_intent
from .topic_drift import topic_drift

TOOLS_V1 = [
    analyze_text_intent,
    sentiment_curve,
    ocr_extract,
    image_text_consistency,
    detect_logo_product,
    topic_drift,
    comment_anomaly,
]

TOOL_READINESS = {
    "analyze_text_intent": True,
    "sentiment_curve": True,
    "topic_drift": True,
    "comment_anomaly": True,
    "ocr_extract": True,
    "image_text_consistency": True,
    "detect_logo_product": True,
}

