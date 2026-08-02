import json
from types import SimpleNamespace

from run_demo import main, run_demo


class FakeAnalysisService:
    def __init__(self):
        self.calls = []

    def analyze(self, post, *, runtime_mode):
        self.calls.append((post, runtime_mode))
        index = len(self.calls)
        return SimpleNamespace(
            readable_report=f"report-{index}",
            run_metadata=SimpleNamespace(run_id=f"run_{index}"),
        )


def _samples(tmp_path):
    path = tmp_path / "samples.json"
    path.write_text(
        json.dumps(
            [
                {"text": "样本一", "blogger": "A"},
                {"text": "样本二", "blogger": "B"},
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return path


def test_run_demo_uses_unified_local_service_for_default_samples(tmp_path):
    service = FakeAnalysisService()

    results = run_demo(_samples(tmp_path), service=service)

    assert [item.readable_report for item in results] == [
        "report-1",
        "report-2",
    ]
    assert service.calls == [
        ({"text": "样本一", "blogger": "A"}, "local"),
        ({"text": "样本二", "blogger": "B"}, "local"),
    ]


def test_run_demo_image_path_still_uses_unified_local_service(tmp_path):
    service = FakeAnalysisService()

    results = run_demo(
        _samples(tmp_path),
        image_path="sample.jpg",
        service=service,
    )

    assert len(results) == 1
    assert service.calls == [(
        {
            "text": "分享一下最近入手的好物～",
            "blogger": "demo",
            "image_path": "sample.jpg",
        },
        "local",
    )]


def test_main_accepts_deprecated_llm_flag_and_prints_report_and_run_id(
    tmp_path,
    capsys,
):
    service = FakeAnalysisService()

    exit_code = main(
        ["--llm"],
        samples_path=_samples(tmp_path),
        service=service,
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "--llm 已弃用" in output
    assert "report-1" in output
    assert "run_id：run_1" in output
    assert all(mode == "local" for _, mode in service.calls)
