"""FFmpeg / ffprobe の実行。

- 引数はリストで渡し、シェルを通さない（日本語・スペース入りパス対策）
- 実行したコマンドと失敗時の出力はすべてログに残す
"""
from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

from .errors import PodcastError

log = logging.getLogger("podcast")

REQUIRED_FILTERS = [
    "afftdn", "highpass", "lowpass", "dynaudnorm", "acompressor", "sidechaincompress",
    "alimiter", "loudnorm", "silencedetect", "astats", "ametadata", "asetnsamples",
    "amix", "adelay", "atrim", "asetpts", "volume", "aresample", "aformat", "asplit",
    "apad", "adeclick", "pan",
]

INSTALL_HINT = (
    "FFmpeg をインストールしてください。"
    " macOS: `brew install ffmpeg` / Windows: `winget install Gyan.FFmpeg`（インストール後にターミナルを開き直す）。"
    " 別の場所にある場合は config/podcast.yaml の ffmpeg.path に ffmpeg の実行ファイルを指定してください。"
)


class FFmpeg:
    def __init__(self, ffmpeg_path: str | None, ffprobe_path: str | None):
        self.ffmpeg = self._locate(ffmpeg_path, "ffmpeg")
        self.ffprobe = self._locate(ffprobe_path, "ffprobe", sibling_of=self.ffmpeg)
        self.version = self._version()
        self.commands: list[dict] = []  # レポート・再現用に全コマンドを記録

    @staticmethod
    def _locate(explicit: str | None, name: str, sibling_of: str | None = None) -> str:
        env = os.environ.get(f"PODCAST_{name.upper()}")
        for cand in (explicit, env):
            if cand:
                if Path(cand).is_file():
                    return str(Path(cand))
                found = shutil.which(cand)
                if found:
                    return found
                raise PodcastError(f"{name} が見つかりません: {cand}", step="事前チェック", hint=INSTALL_HINT)
        if sibling_of:
            exe = Path(sibling_of).with_name(name + Path(sibling_of).suffix)
            if exe.is_file():
                return str(exe)
        found = shutil.which(name)
        if not found:
            raise PodcastError(f"{name} が見つかりません（PATH 上にありません）", step="事前チェック", hint=INSTALL_HINT)
        return found

    def _version(self) -> str:
        out = subprocess.run([self.ffmpeg, "-hide_banner", "-version"], capture_output=True)
        first = out.stdout.decode("utf-8", "replace").splitlines()[:1]
        return first[0] if first else "unknown"

    def check_capabilities(self) -> None:
        out = subprocess.run([self.ffmpeg, "-hide_banner", "-filters"], capture_output=True)
        text = out.stdout.decode("utf-8", "replace")
        names = set()
        for line in text.splitlines():
            parts = line.split()
            if len(parts) >= 3 and "->" in parts[2]:
                names.add(parts[1])
        missing = [f for f in REQUIRED_FILTERS if f not in names]
        if missing:
            raise PodcastError(
                f"この FFmpeg には必要なフィルタがありません: {', '.join(missing)}（{self.version}）",
                step="事前チェック", hint="FFmpeg 5.0 以上の公式ビルド（full 版）を入れてください。")
        enc = subprocess.run([self.ffmpeg, "-hide_banner", "-encoders"], capture_output=True)
        if "libmp3lame" not in enc.stdout.decode("utf-8", "replace"):
            raise PodcastError("この FFmpeg は MP3 エンコーダ（libmp3lame）を含んでいません。",
                               step="事前チェック", hint="libmp3lame を含む FFmpeg ビルドを入れてください。")
        m = re.search(r"version n?(\d+)\.", self.version)
        if m and int(m.group(1)) < 5:
            raise PodcastError(f"FFmpeg が古すぎます: {self.version}", step="事前チェック",
                               hint="FFmpeg 5.0 以上に更新してください。")

    def run(self, args: list[str], step: str) -> subprocess.CompletedProcess:
        """ffmpeg を実行。失敗したら直近の出力付きで PodcastError を送出。"""
        cmd = [self.ffmpeg, "-hide_banner", "-nostdin"] + [str(a) for a in args]
        return self._exec(cmd, step)

    def probe(self, path: Path) -> dict:
        import json
        cmd = [self.ffprobe, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)]
        res = self._exec(cmd, "ファイル情報の取得")
        try:
            return json.loads(res.stdout.decode("utf-8", "replace"))
        except ValueError as e:
            raise PodcastError(f"ffprobe の出力を読めません: {e}", step="ファイル情報の取得")

    def _exec(self, cmd: list[str], step: str) -> subprocess.CompletedProcess:
        log.debug("[%s] $ %s", step, " ".join(_quote(c) for c in cmd))
        t0 = time.time()
        try:
            res = subprocess.run(cmd, capture_output=True)
        except OSError as e:
            raise PodcastError(f"FFmpeg を起動できません: {e}", step=step, hint=INSTALL_HINT)
        elapsed = time.time() - t0
        self.commands.append({"step": step, "cmd": cmd, "returncode": res.returncode, "sec": round(elapsed, 2)})
        stderr = res.stderr.decode("utf-8", "replace")
        if res.returncode != 0:
            tail = "\n".join(stderr.strip().splitlines()[-25:])
            log.error("[%s] FFmpeg が終了コード %s で失敗しました。\n$ %s\n--- FFmpeg 出力（末尾） ---\n%s",
                      step, res.returncode, " ".join(_quote(c) for c in cmd), tail)
            raise PodcastError(
                f"FFmpeg の処理に失敗しました（終了コード {res.returncode}）。最後の出力: "
                + (stderr.strip().splitlines()[-1] if stderr.strip() else "(なし)"),
                step=step, hint="output/ のログファイル（*_process.log）に詳しい出力があります。")
        log.debug("[%s] 完了 %.1f 秒", step, elapsed)
        res.stderr_text = stderr  # type: ignore[attr-defined]
        return res


def _quote(s: str) -> str:
    s = str(s)
    if not s or any(ch in s for ch in " \t\"'&|;()<>[]{}$`,"):
        return '"' + s.replace('"', '\\"') + '"'
    return s
