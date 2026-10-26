#!/usr/bin/env python3
"""動作確認用の素材を合成する（実際の番組素材の代わり）。

生成物:
  assets/opening.mp3, jingle.mp3, ending.mp3   … 和音の合成音（音量をわざと不揃いにしてある）
  input/<名前>.wav                               … 2人の話者（音量差 9dB）+ ハム・ノイズ + 前後の無音 + 長い無音

声は espeak-ng があればそれを使い、無ければ「声に似た」帯域制限ノイズで代用する。
使い方: python tools/make_test_assets.py [--name "第1回 テスト 収録"] [--minutes 3]
"""
from __future__ import annotations

import argparse
import json
import random
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SR = 44100

LINES_A = [
    "Welcome back to the show. Today we are talking about community theater.",
    "I think the most important thing is that everyone can join, no matter their experience.",
    "Last month we held a workshop at the city hall, and forty people came.",
    "Rehearsals are twice a week, usually on Tuesday and Saturday evening.",
    "The stage was small, but the audience was very close, and that made it special.",
    "Let us move on to the next topic.",
    "Thank you for listening. See you next time.",
]
LINES_B = [
    "Yes, and I was surprised how many children wanted to act.",
    "Right. Some of them had never been on a stage before.",
    "The parents helped with costumes and the lighting, which was great.",
    "I agree. We should do that again in the spring.",
    "Actually, I have a question about the budget for next year.",
    "That sounds good to me.",
]


def run(cmd):
    r = subprocess.run([str(c) for c in cmd], capture_output=True)
    if r.returncode != 0:
        sys.exit(f"failed: {' '.join(map(str, cmd))}\n{r.stderr.decode('utf-8', 'replace')[-2000:]}")
    return r


def duration(p: Path) -> float:
    r = run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", p])
    return float(r.stdout.decode().strip())


def make_bgm(out: Path, freqs: list[float], dur: float, gain_db: float, bpm: float) -> None:
    beat = 60.0 / bpm
    tones = "+".join(f"sin(2*PI*{f}*t)" for f in freqs)
    expr = f"({tones})/{len(freqs)}*(0.6+0.4*exp(-6*mod(t,{beat:.4f})))"
    kick = f"0.5*sin(2*PI*55*t)*exp(-25*mod(t,{beat * 2:.4f}))"
    run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
         f"aevalsrc='{expr}+{kick}|{expr}*0.9+{kick}':s={SR}:d={dur}",
         "-af", f"volume={gain_db}dB,afade=t=out:st={dur - 1.5}:d=1.5", "-c:a", "libmp3lame", "-b:a", "192k", out])


def synth_utterance(text: str, voice: str, out: Path, rnd: random.Random) -> None:
    if shutil.which("espeak-ng"):
        run(["espeak-ng", "-v", voice, "-s", "150", "-w", out, text])
        return
    # espeak-ng がない場合: 音節リズムで変調した帯域制限ノイズ
    d = max(1.5, len(text) / 14)
    f0 = 120 if "f" not in voice else 210
    run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
         f"aevalsrc='(0.5*sin(2*PI*{f0}*t)+0.3*sin(2*PI*{f0 * 2}*t)+0.2*(random(0)-0.5))"
         f"*(0.5+0.5*sin(2*PI*4.5*t+{rnd.random() * 6:.2f}))':s=22050:d={d:.2f}",
         "-af", "bandpass=f=900:w=1400", out])


def make_voice(out: Path, minutes: float, rnd: random.Random) -> dict:
    tmp = Path(tempfile.mkdtemp(prefix="podtest_"))
    try:
        items, t = [], 4.0  # 冒頭 4 秒の無音
        target = minutes * 60
        i = 0
        long_gap_done = topic_gap_done = False
        while t < target - 8:
            spk = i % 2
            text = (LINES_A if spk == 0 else LINES_B)[(i // 2) % (len(LINES_A) if spk == 0 else len(LINES_B))]
            p = tmp / f"u{i:03d}.wav"
            synth_utterance(text, "en-us" if spk == 0 else "en-gb+f3", p, rnd)
            items.append((p, t, 0.0 if spk == 0 else -9.0))   # 話者Bは 9dB 小さい
            t += duration(p)
            if not topic_gap_done and t > target * 0.45:
                t += 2.5          # 話題の切れ目（アイキャッチ候補）
                topic_gap_done = True
            elif not long_gap_done and t > target * 0.7:
                t += 7.0          # 異常に長い無音
                long_gap_done = True
            else:
                t += rnd.uniform(0.25, 0.8)   # 通常の会話の間
            i += 1
        total = t + 5.0  # 末尾 5 秒の無音
        args = ["ffmpeg", "-y", "-v", "error"]
        for p, _, _ in items:
            args += ["-i", p]
        g = [f"[{k}:a]aresample={SR},volume={gain}dB,adelay={int(pos * 1000)}:all=1[a{k}]"
             for k, (_, pos, gain) in enumerate(items)]
        n = len(items)
        g.append("".join(f"[a{k}]" for k in range(n)) + f"amix=inputs={n}:normalize=0:duration=longest,"
                 f"apad=whole_dur={total:.3f},atrim=end={total:.3f},volume=-6dB[v]")
        # 背景ノイズ: ピンクノイズ + 50Hz ハム + 20Hz のゴロゴロ
        g.append(f"anoisesrc=c=pink:a=0.004:r={SR}:d={total:.3f}:seed=7[n]")
        g.append(f"aevalsrc='0.006*sin(2*PI*50*t)+0.004*sin(2*PI*150*t)+0.01*sin(2*PI*20*t)':s={SR}:d={total:.3f}[h]")
        g.append("[v][n][h]amix=inputs=3:normalize=0:duration=first[o]")
        run(args + ["-filter_complex", ";".join(g), "-map", "[o]", "-ac", "1", "-c:a", "pcm_s16le", out])
        meta = [{"speaker": "A" if g == 0.0 else "B", "start": round(pos, 3), "end": round(pos + duration(p), 3)}
                for p, pos, g in items]
        return {"duration": total, "utterances": n, "items": meta}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="第1回 テスト 収録")
    ap.add_argument("--minutes", type=float, default=3.0)
    ap.add_argument("--root", type=Path, default=ROOT)
    a = ap.parse_args()
    rnd = random.Random(1234)
    (a.root / "assets").mkdir(parents=True, exist_ok=True)
    (a.root / "input").mkdir(parents=True, exist_ok=True)
    make_bgm(a.root / "assets" / "opening.mp3", [261.6, 329.6, 392.0, 523.3], 30, -4, 110)
    make_bgm(a.root / "assets" / "jingle.mp3", [392.0, 493.9, 587.3], 3.5, -10, 180)
    make_bgm(a.root / "assets" / "ending.mp3", [220.0, 277.2, 329.6, 440.0], 40, 0, 90)
    info = make_voice(a.root / "input" / f"{a.name}.wav", a.minutes, rnd)
    # 検証用: 発話ごとの話者と時刻（話者間の音量差の測定に使う）
    meta_dir = a.root / "output" / "_testmeta"
    meta_dir.mkdir(parents=True, exist_ok=True)
    (meta_dir / f"{a.name}.json").write_text(json.dumps(info["items"], ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"作成: assets/opening.mp3, jingle.mp3, ending.mp3, input/{a.name}.wav"
          f"（{info['duration']:.1f} 秒, 発話 {info['utterances']} 個）")


if __name__ == "__main__":
    main()
