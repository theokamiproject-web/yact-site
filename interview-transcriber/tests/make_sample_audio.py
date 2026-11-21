"""テスト用の合成音声（2話者の対談風）を作る。open_jtalk と ffmpeg が必要。
実音声ではないので認識精度の評価には使えない。パイプライン疎通確認用。
usage: python tests/make_sample_audio.py samples/sample_dialogue.m4a
"""
import subprocess, sys, tempfile
from pathlib import Path

VOICE = "/usr/share/hts-voice/nitech-jp-atr503-m001/nitech_jp_atr503_m001.htsvoice"
DIC = "/var/lib/mecab/dic/open-jtalk/naist-jdic"
LINES = [  # (話者, 台詞, 半音シフト)
    ("A", "えーと、今日はですね、この企画について話していきたいと思います。", 0),
    ("B", "はい。", 6),
    ("A", "そもそもこれを始めたのは、二〇二四年の十月ごろなんです。", 0),
    ("B", "そうだったんですか。", 6),
    ("A", "はい。参加者は三十人くらいでした。", 0),
]


def tts(text, out, shift):
    cmd = ["open_jtalk", "-x", DIC, "-m", VOICE, "-ow", str(out), "-fm", str(shift), "-r", "1.0"]
    subprocess.run(cmd, input=text.encode(), check=True)


def main(dst):
    tmp = Path(tempfile.mkdtemp())
    parts = []
    for i, (_, text, shift) in enumerate(LINES):
        w = tmp / f"{i}.wav"
        tts(text, w, shift)
        parts.append(w)
    lst = tmp / "list.txt"
    sil = tmp / "sil.wav"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono",
                    "-t", "0.8", str(sil)], check=True)
    ins = []
    for p in parts:
        ins += ["-i", str(p), "-i", str(sil)]
    n = len(parts) * 2
    flt = "".join(f"[{i}:a]aresample=48000,aformat=channel_layouts=mono[a{i}];" for i in range(n))
    flt += "".join(f"[a{i}]" for i in range(n)) + f"concat=n={n}:v=0:a=1[out]"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *ins, "-filter_complex", flt,
                    "-map", "[out]", dst], check=True)
    print("wrote", dst)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "samples/sample_dialogue.m4a")
