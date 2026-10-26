"""音声・文字起こし・ログ・出力が Git に入らないことの検証。"""
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

MEDIA_EXT = (".wav", ".mp3", ".m4a", ".aac", ".flac", ".aif", ".aiff", ".ogg", ".opus", ".wma", ".caf",
             ".mp4", ".mov", ".m4v", ".webm", ".srt", ".vtt", ".ass", ".log")

MUST_IGNORE = [
    "input/episode.wav", "input/第1回 収録.m4a", "input/memo.txt",
    "output/episode_master.wav", "output/episode_publish.mp3", "output/episode_report.json",
    "output/episode_report.txt", "output/episode_process.log", "output/preview/ep/before.wav",
    "output/_work/ep/voice_clean.wav",
    "assets/opening.mp3", "assets/jingle.wav",
    "transcripts/ep.txt", "transcripts/ep.json", "ep.srt", "sub/ep.vtt",
    "rec.wav", "notes/ep.m4a", "tests/sample.flac", "docs/demo.mp4", "debug.log",
]
MUST_TRACK = ["README.md", "config/podcast.yaml", "podcast_tool/cli.py", "input/.gitkeep",
              "output/.gitkeep", "assets/.gitkeep", "requirements.txt"]


def _git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)


pytestmark = pytest.mark.skipif(shutil.which("git") is None or _git("rev-parse").returncode != 0,
                                reason="git リポジトリ内でのみ実行")


@pytest.mark.parametrize("path", MUST_IGNORE)
def test_media_and_outputs_are_ignored(path):
    assert _git("check-ignore", "-q", "--no-index", path).returncode == 0, f"{path} が除外されていません"


@pytest.mark.parametrize("path", MUST_TRACK)
def test_source_files_are_not_ignored(path):
    assert _git("check-ignore", "-q", "--no-index", path).returncode != 0, f"{path} が誤って除外されています"


def test_no_media_committed():
    files = _git("ls-files").stdout.splitlines()
    bad = [f for f in files if f.lower().endswith(MEDIA_EXT)]
    assert not bad, f"音声等がコミットされています: {bad}"
    outs = [f for f in files if f.split("/")[0] in ("input", "output", "assets") and not f.endswith(".gitkeep")]
    assert not outs, f"入出力・素材フォルダの中身がコミットされています: {outs}"
