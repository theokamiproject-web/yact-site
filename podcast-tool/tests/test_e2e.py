"""通し試験: 合成素材で実際に FFmpeg を動かし、出力を測定する（FFmpeg が無ければスキップ）。"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg がありません")


@pytest.fixture(scope="module")
def project(tmp_path_factory):
    d = tmp_path_factory.mktemp("proj スペース 日本語")
    (d / "config").mkdir()
    shutil.copy(ROOT / "config" / "podcast.yaml", d / "config" / "podcast.yaml")
    subprocess.run([sys.executable, str(ROOT / "tools" / "make_test_assets.py"), "--root", str(d),
                    "--minutes", "2", "--name", "第2回 テスト"], check=True)
    return d


def run(project, *args):
    return subprocess.run([sys.executable, str(ROOT / "podcast.py"), "-c", str(project / "config" / "podcast.yaml"),
                           *args], capture_output=True, text=True, encoding="utf-8")


def test_full_pipeline(project):
    src = project / "input" / "第2回 テスト.wav"
    before = src.read_bytes()
    r = run(project, "第2回 テスト.wav")
    assert r.returncode == 0, r.stdout + r.stderr
    out = project / "output"
    rep = json.loads((out / "第2回 テスト_report.json").read_text(encoding="utf-8"))
    cfg = yaml.safe_load((project / "config" / "podcast.yaml").read_text(encoding="utf-8"))
    tgt, tp = cfg["loudness"]["target_lufs"], cfg["loudness"]["true_peak_max_dbtp"]
    for k in ("after_master", "after_publish"):
        assert abs(rep["loudness"][k]["integrated_lufs"] - tgt) <= cfg["loudness"]["tolerance_lu"]
        assert rep["loudness"][k]["true_peak_dbtp"] <= tp
    assert rep["qc"]["passed"]
    assert (out / "第2回 テスト_master.wav").stat().st_size > 0
    assert (out / "第2回 テスト_publish.mp3").stat().st_size > 0
    assert src.read_bytes() == before  # 元音源は変更されていない
    assert not list(out.glob(".*.tmp.*"))
    assert not (out / "_work").exists()


def test_reproducible(project):
    out = project / "output"
    first = (out / "第2回 テスト_master.wav").read_bytes()
    first_mp3 = (out / "第2回 テスト_publish.mp3").read_bytes()
    r = run(project, "第2回 テスト.wav")
    assert r.returncode == 0, r.stdout + r.stderr
    assert (out / "第2回 テスト_master.wav").read_bytes() == first
    assert (out / "第2回 テスト_publish.mp3").read_bytes() == first_mp3


def test_missing_bgm_is_clear_error(project):
    ed = project / "assets" / "ending.mp3"
    tmp = ed.with_suffix(".bak")
    ed.rename(tmp)
    try:
        r = run(project, "第2回 テスト.wav")
        assert r.returncode == 1
        assert "BGM ファイルが見つかりません" in r.stderr and "ending.mp3" in r.stderr
    finally:
        tmp.rename(ed)


def test_missing_input_is_clear_error(project):
    r = run(project, "ないファイル.wav")
    assert r.returncode == 1
    assert "入力ファイルが見つかりません" in r.stderr
