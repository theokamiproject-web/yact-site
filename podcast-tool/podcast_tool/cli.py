"""コマンドライン: `podcast episode.wav`"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from . import __version__
from .config import load_config
from .errors import PodcastError
from .pipeline import AUDIO_EXTS, process

TOOL_ROOT = Path(__file__).resolve().parent.parent


def _default_config() -> Path:
    # 1) カレントの config/podcast.yaml  2) このツールに同梱の config/podcast.yaml
    for base in (Path.cwd(), TOOL_ROOT):
        p = base / "config" / "podcast.yaml"
        if p.is_file():
            return p
    return Path.cwd() / "config" / "podcast.yaml"


def _resolve_input(arg: str, input_dir: Path) -> Path:
    p = Path(arg)
    if p.is_file():
        return p
    if not p.is_absolute() and (input_dir / p).is_file():
        return input_dir / p
    raise PodcastError(f"入力ファイルが見つかりません: {arg}", step="事前チェック",
                       hint=f"{input_dir} に置くか、ファイルの場所をフルパスで指定してください。"
                            "スペースを含む名前は \"...\" で囲んでください。")


def main(argv: list[str] | None = None) -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")  # Windows の文字化け対策
        except Exception:
            pass
    ap = argparse.ArgumentParser(prog="podcast", description="ポッドキャスト音声の自動編集・マスタリング")
    ap.add_argument("inputs", nargs="*", help="入力ファイル（input/ 内のファイル名だけでも可）")
    ap.add_argument("--all", action="store_true", help="input/ 内の音声をすべて処理")
    ap.add_argument("-c", "--config", type=Path, help="設定ファイル（既定: config/podcast.yaml）")
    ap.add_argument("--analyze", action="store_true", help="解析のみ（音声は書き出さない）")
    ap.add_argument("--keep-work", action="store_true", help="中間ファイルを残す")
    ap.add_argument("-v", "--verbose", action="store_true", help="FFmpeg コマンドも表示")
    ap.add_argument("--version", action="version", version=f"podcast-tool {__version__}")
    args = ap.parse_args(argv)

    logger = logging.getLogger("podcast")
    logger.setLevel(logging.DEBUG)
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.DEBUG if args.verbose else logging.INFO)
    console.setFormatter(logging.Formatter("%(message)s"))
    console.addFilter(lambda r: not getattr(r, "file_only", False))
    logger.addHandler(console)

    try:
        cfg = load_config((args.config or _default_config()).resolve())
        if args.keep_work:
            cfg.data["output"]["keep_work_files"] = True
        input_dir = cfg.dir("input_dir")
        files: list[Path] = [_resolve_input(a, input_dir) for a in args.inputs]
        if args.all:
            files += sorted(p for p in input_dir.iterdir() if p.suffix.lower() in AUDIO_EXTS)
        if not files:
            ap.print_usage()
            print(f"\n入力ファイルを指定してください（例: podcast episode.wav）。input フォルダ: {input_dir}")
            return 2
        failed = 0
        for f in files:
            try:
                data = process(cfg, f, analyze_only=args.analyze)
                if args.analyze:
                    import json
                    print(json.dumps(data, ensure_ascii=False, indent=2))
                elif not data["qc"]["passed"]:
                    failed += 1
                    print("\n※ 品質チェックで NG の項目があります。レポートを確認してください。")
            except PodcastError as e:
                failed += 1
                print("\n" + e.render(), file=sys.stderr)
        return 1 if failed else 0
    except PodcastError as e:
        print("\n" + e.render(), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\n中断しました。", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
