"""配置計算の単体テスト（FFmpeg 不要）。"""
import copy
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from podcast_tool.analyze import Silence  # noqa: E402
from podcast_tool.config import Config, validate  # noqa: E402
from podcast_tool.errors import ConfigError  # noqa: E402
from podcast_tool.timeline import build, envelope_expr, gain_at  # noqa: E402

BASE = yaml.safe_load((ROOT / "config" / "podcast.yaml").read_text(encoding="utf-8"))
ASSETS = {"opening": 30.0, "jingle": 3.5, "ending": 40.0}


def cfg(**over):
    data = copy.deepcopy(BASE)
    for dotted, v in over.items():
        node = data
        keys = dotted.split("__")
        for k in keys[:-1]:
            node = node[k]
        node[keys[-1]] = v
    c = Config.__new__(Config)
    c.data, c.path, c.root, c.sha256 = data, ROOT / "config" / "podcast.yaml", ROOT, ""
    validate(c)
    return c


# 600 秒の声: 冒頭 5 秒・末尾 6 秒が無音、途中にいくつか無音
SIL = [Silence(0, 5), Silence(100, 100.8), Silence(290, 292.0), Silence(305, 305.4),
       Silence(400, 408), Silence(594, 600)]


def test_trim_head_tail():
    tl = build(cfg(jingle__positions=[]), 600, SIL, ASSETS)
    assert tl.trim_start == pytest.approx(5 - 0.3)
    assert tl.trim_end == pytest.approx(594 + 0.6)


def test_jingle_uses_silence_near_target_and_prefers_longer():
    # 50% 地点 ≒ source 299.95 秒。305.4 の短い無音(0.4秒)は min_silence 未満、290〜292 の 2 秒の無音を選ぶ
    tl = build(cfg(), 600, SIL, ASSETS)
    assert len(tl.jingles) == 1
    j = tl.jingles[0]
    assert j.silence.start == 290
    assert j.cut_src == pytest.approx(291.0)
    # 会話を切らない: 切れ目の前後のセグメント境界が無音の中にある
    assert tl.segments[0].src_end == pytest.approx(291.0)
    assert tl.segments[1].src_start == pytest.approx(291.0)


def test_jingle_skipped_when_no_silence_in_window():
    tl = build(cfg(jingle__positions=[{"seconds": 200}], jingle__search_window_sec=20), 600, SIL, ASSETS)
    assert tl.jingles == []
    assert any("挿入しません" in w for w in tl.warnings)


def test_jingle_nearest_mode():
    tl = build(cfg(jingle__positions=[{"seconds": 200}], jingle__search_window_sec=20,
                   jingle__on_no_silence="nearest"), 600, SIL, ASSETS)
    assert len(tl.jingles) == 1


def test_multiple_jingles_and_timeline_lengths():
    c = cfg(jingle__positions=[{"minutes": 1.6}, {"percent": 50}])
    tl = build(c, 600, SIL, ASSETS)
    assert [round(j.cut_src, 1) for j in tl.jingles] == [100.4, 291.0]
    # 完成尺 = OP の声開始 + 本編 + (ジングル + 前後の間) × 回数 + ED のテール
    per = ASSETS["jingle"] + c.num("jingle.gap_before_sec") + c.num("jingle.gap_after_sec")
    expected_voice_end = c.num("opening.solo_sec") + tl.main_duration + per * 2
    assert tl.voice_out_end == pytest.approx(expected_voice_end)
    assert tl.total == pytest.approx(expected_voice_end + c.num("ending.tail_sec") + c.num("ending.fade_out_sec"))
    # セグメントは時間順に重ならない
    for a, b in zip(tl.segments, tl.segments[1:]):
        assert a.out_start + a.duration <= b.out_start


def test_jingles_too_close_are_dropped():
    tl = build(cfg(jingle__positions=[{"seconds": 286}, {"seconds": 290}]), 600, SIL, ASSETS)
    assert len(tl.jingles) == 1
    assert any("以内のため" in w for w in tl.warnings)


def test_long_silence_reported_not_removed():
    tl = build(cfg(jingle__positions=[]), 600, SIL, ASSETS)
    assert [c["duration"] for c in tl.long_silences] == [8.0]
    assert tl.main_duration == pytest.approx(594.6 - 4.7)  # 本編は短くなっていない


def test_short_bgm_is_truncated_with_warning():
    tl = build(cfg(jingle__positions=[]), 600, SIL, {"opening": 10.0, "jingle": 3.0, "ending": 12.0})
    assert tl.opening.length == 10.0
    assert tl.opening.envelope[-1] == (10.0, None)
    assert tl.ending.length == 12.0
    assert sum("短いため" in w for w in tl.warnings) == 2


def test_disabled_opening_and_ending():
    tl = build(cfg(opening__enabled=False, ending__enabled=False, jingle__positions=[]), 600, SIL, ASSETS)
    assert tl.voice_out_start == 0
    assert tl.opening is None and tl.ending is None
    assert tl.total == pytest.approx(tl.main_duration)


def test_envelope_values():
    pts = [(0.0, 0.0), (6.5, 0.0), (8.0, -12.0), (14.0, -12.0), (18.0, None)]
    assert gain_at(pts, 3) == pytest.approx(0.0)
    assert gain_at(pts, 10) == pytest.approx(-12.0)
    assert gain_at(pts, 18) is None
    expr = envelope_expr(pts)
    assert expr.count("if(") == 5 and "'" not in expr


def test_config_validation_errors():
    with pytest.raises(ConfigError):
        cfg(loudness__target_lufs=0)
    with pytest.raises(ConfigError):
        cfg(jingle__positions=[{"minute": 3}])
    with pytest.raises(ConfigError):
        cfg(ending__rise_sec=20, ending__tail_sec=5)
