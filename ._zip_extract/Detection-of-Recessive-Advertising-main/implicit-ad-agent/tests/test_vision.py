"""Vision routing stays local-file-only and degrades through capture state."""
from impad.agents import supervisor
from impad.graph import graph


def test_supervisor_does_not_schedule_missing_or_remote_image():
    missing = supervisor({
        "post": {"text": "hi", "image_path": "missing.jpg"}
    })
    remote = supervisor({
        "post": {
            "text": "hi",
            "image_url": "https://example.com/image.jpg",
        }
    })

    assert "vision" not in missing["plan"]
    assert "vision" not in remote["plan"]


def test_graph_marks_provided_but_unavailable_image_for_review():
    out = graph.invoke({
        "post": {
            "text": "这支面霜我亲测三个月，无限回购",
            "image_path": "no_such.jpg",
        }
    })

    assert out["verdict"] == "需复核"
    assert "image_capture_incomplete" in out["verdict_report"].reasons
    assert out["report"]
