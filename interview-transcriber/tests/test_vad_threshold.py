"""--vad-threshold（実験用VAD）: 標準は不変、指定時だけ Track-81 の比較実験と同じ設定、キャッシュは混ざらない。"""
import argparse
import json
import sys
import types

import pytest

import diarization as dz
import transcribe_interview as cli
import whisperx_runner as wx
from helpers import make_aligned

LINES = [("SPEAKER_00", "最初はそんなに大きなことをやろうとは思ってなかったんです。"), ("SPEAKER_01", "そうだったんですか。")]


class Rig:
    """WhisperX本体・ffmpeg・話者分離を差し替えて main を実行する。load_model に渡された引数と呼び出し回数を捕捉する。"""

    def __init__(self, tmp_path, monkeypatch, hf_token="dummy"):
        self.tmp, self.mp = tmp_path, monkeypatch
        self.load_calls, self.asr_runs, self.diar_runs = [], 0, 0
        self.aligned, self.diar = make_aligned(LINES)
        (tmp_path / "talk.m4a").write_bytes(b"dummy")
        rig = self

        class FakeModel:
            def transcribe(self, audio, batch_size=8, language="ja"):
                rig.asr_runs += 1
                return {"segments": rig.aligned["segments"], "language": "ja"}

        fake = types.ModuleType("whisperx")
        fake.load_model = lambda *a, **k: (rig.load_calls.append(k), FakeModel())[1]
        fake.load_audio = lambda p: [0.0]
        monkeypatch.setitem(sys.modules, "whisperx", fake)
        monkeypatch.setattr(wx, "check_ffmpeg", lambda: None)
        monkeypatch.setattr(wx, "validate_audio", lambda p: 10.0)
        monkeypatch.setattr(wx, "preprocess", lambda *a, **k: tmp_path / "x.wav")
        monkeypatch.setattr(wx, "align", lambda *a, **k: rig.aligned)
        monkeypatch.setattr(dz, "run_diarization", lambda *a, **k: (setattr(rig, "diar_runs", rig.diar_runs + 1), rig.diar)[1])
        if hf_token:
            monkeypatch.setenv("HF_TOKEN", hf_token)
        else:
            monkeypatch.delenv("HF_TOKEN", raising=False)
        for k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "EDITOR_PROVIDER"):
            monkeypatch.delenv(k, raising=False)

    def run(self, *extra, out="out"):
        rc = cli.main([str(self.tmp / "talk.m4a"), "--cache-dir", str(self.tmp / "cache"), "--output-dir", str(self.tmp / out),
                       "--speakers", str(self.tmp / "none.yaml"), "--dictionary", str(self.tmp / "none.yaml"), *extra])
        return rc, self.tmp / out


# ---------------------------------------------------------------- 1) 省略時は既存挙動が完全に不変
def test_default_does_not_pass_vad_options_at_all(tmp_path, monkeypatch):
    rig = Rig(tmp_path, monkeypatch)
    rc, out = rig.run()
    assert rc == 0 and len(rig.load_calls) == 1
    assert "vad_options" not in rig.load_calls[0]                         # WhisperXの既定（onset 0.5 / offset 0.363）のまま
    assert wx.vad_options(None) is None and wx.vad_signature(None) is None
    cached = json.loads((tmp_path / "cache" / "talk" / "whisper_result.json").read_text())
    assert set(cached["_sig"]) == {"fingerprint", "model", "language", "prompt"}   # 従来の署名（vad キーなし＝既存キャッシュと互換）
    assert "vad" not in cached["meta"]
    assert not (tmp_path / "cache" / "talk" / "vad_0.3").exists()         # 実験用ディレクトリは作らない
    assert wx.VAD_DEFAULT == {"onset": 0.5, "offset": 0.363}


def test_existing_default_cache_without_vad_key_is_still_reused(tmp_path, monkeypatch):
    rig = Rig(tmp_path, monkeypatch)
    rig.run()
    assert rig.asr_runs == 1
    rig.run(out="out2")                                                  # 同じ標準設定 → キャッシュ使用
    assert rig.asr_runs == 1


# ---------------------------------------------------------------- 2・3) 指定値が Track-81 比較実験と同じ形で渡る
@pytest.mark.parametrize("thr", [0.4, 0.3, 0.2])
def test_threshold_is_passed_as_onset_and_offset_exactly_like_the_track81_experiment(tmp_path, monkeypatch, thr):
    rig = Rig(tmp_path, monkeypatch)
    rc, out = rig.run("--vad-threshold", str(thr), out=f"vad_{thr}")
    assert rc == 0
    # Track-81 の比較（vad_asr.py）: whisperx.load_model(..., vad_options={"vad_onset": thr, "vad_offset": thr})
    assert rig.load_calls[0]["vad_options"] == {"vad_onset": thr, "vad_offset": thr}
    assert wx.vad_options(thr) == {"vad_onset": thr, "vad_offset": thr}


def test_whisperx_merges_vad_options_over_its_defaults_like_the_experiment():
    """WhisperX本体が vad_options を既定値へ上書きマージする仕様（onset 0.5 / offset 0.363）を前提にしている。"""
    import inspect
    import whisperx.asr as asr
    src = inspect.getsource(asr.load_model)
    assert '"vad_onset": 0.500' in src and '"vad_offset": 0.363' in src and "default_vad_options.update(vad_options)" in src


# ---------------------------------------------------------------- 4・5・6・7) キャッシュ署名と分離
def test_vad_is_part_of_the_asr_cache_signature(tmp_path, monkeypatch):
    rig = Rig(tmp_path, monkeypatch)
    rig.run("--vad-threshold", "0.3")
    cached = json.loads((tmp_path / "cache" / "talk" / "vad_0.3" / "whisper_result.json").read_text())
    assert cached["_sig"]["vad"] == {"onset": 0.3, "offset": 0.3}
    assert cached["meta"]["vad"] == {"onset": 0.3, "offset": 0.3}


def test_default_and_experimental_caches_do_not_mix_either_way(tmp_path, monkeypatch):
    rig = Rig(tmp_path, monkeypatch)
    rig.run()                                                            # 標準
    assert rig.asr_runs == 1
    rig.run("--vad-threshold", "0.3", out="v03")                         # 標準キャッシュを使わず再ASR
    assert rig.asr_runs == 2
    rig.run(out="again")                                                 # 標準に戻る: 0.3 のキャッシュを使わず、標準キャッシュを使う
    assert rig.asr_runs == 2
    assert "vad_options" not in rig.load_calls[0] and "vad_options" in rig.load_calls[1]
    rig.run("--vad-threshold", "0.3", out="v03b")                        # 0.3 は 0.3 のキャッシュを使う
    assert rig.asr_runs == 2
    std = json.loads((tmp_path / "cache" / "talk" / "whisper_result.json").read_text())["_sig"]
    exp = json.loads((tmp_path / "cache" / "talk" / "vad_0.3" / "whisper_result.json").read_text())["_sig"]
    assert "vad" not in std and exp["vad"]["onset"] == 0.3                # 互いに上書きしない


def test_different_thresholds_do_not_share_asr_cache(tmp_path, monkeypatch):
    rig = Rig(tmp_path, monkeypatch)
    rig.run("--vad-threshold", "0.3", out="a")
    rig.run("--vad-threshold", "0.2", out="b")
    assert rig.asr_runs == 2
    rig.run("--vad-threshold", "0.3", out="c")
    rig.run("--vad-threshold", "0.2", out="d")
    assert rig.asr_runs == 2                                             # それぞれ自分のキャッシュを使う
    assert [c["vad_options"]["vad_onset"] for c in rig.load_calls] == [0.3, 0.2]
    for d in ("vad_0.3", "vad_0.2"):
        assert (tmp_path / "cache" / "talk" / d / "aligned_result.json").exists()     # alignment も別


def test_diarization_cache_is_shared_across_vad_conditions(tmp_path, monkeypatch):
    rig = Rig(tmp_path, monkeypatch)
    rig.run()
    assert rig.diar_runs == 1
    rig.run("--vad-threshold", "0.3", out="v03")                         # VADに依存しない話者分離は再実行しない
    rig.run("--vad-threshold", "0.2", out="v02")
    assert rig.diar_runs == 1
    assert (tmp_path / "cache" / "talk" / "diarization_result.json").exists()    # 実験で共有キャッシュを消さない


def test_diarization_cache_from_a_different_audio_is_not_shared(tmp_path, monkeypatch):
    rig = Rig(tmp_path, monkeypatch)
    rig.run()
    p = tmp_path / "cache" / "talk" / "diarization_result.json"
    d = json.loads(p.read_text())
    d["audio_fp"] = "someotheraudio00"
    p.write_text(json.dumps(d))
    rig.run("--vad-threshold", "0.3", out="v03")
    assert rig.diar_runs == 2


# ---------------------------------------------------------------- 8) 不正な値の拒否
@pytest.mark.parametrize("bad", ["-1", "2", "abc", "0", "1", "1.5", "nan", "inf", "-0.3", ""])
def test_invalid_values_are_rejected_with_a_helpful_message(tmp_path, monkeypatch, capsys, bad):
    with pytest.raises(SystemExit) as e:
        cli.parse_args([str(tmp_path / "a.m4a"), "--vad-threshold", bad])
    assert e.value.code == 2
    err = capsys.readouterr().err
    assert "--vad-threshold" in err and ("0 より大きく 1 より小さい" in err or "数値で指定" in err) and "0.3" in err


@pytest.mark.parametrize("ok", ["0.4", "0.3", "0.2", "0.05", "0.95"])
def test_valid_values_are_accepted(tmp_path, ok):
    assert cli.parse_args([str(tmp_path / "a.m4a"), "--vad-threshold", ok]).vad_threshold == float(ok)
    assert cli.parse_args([str(tmp_path / "a.m4a")]).vad_threshold is None
    with pytest.raises(argparse.ArgumentTypeError):
        wx.parse_vad_threshold("2")


# ---------------------------------------------------------------- 9) 実験であることの記録
def test_experiment_is_recorded_in_log_review_raw_and_metadata(tmp_path, monkeypatch, capsys):
    rig = Rig(tmp_path, monkeypatch)
    rc, out = rig.run("--vad-threshold", "0.3", out="vad_0.3")
    assert rc == 0
    assert "Experimental VAD threshold: 0.3" in capsys.readouterr().err
    review = (out / "review_required.md").read_text()
    assert "実験用VAD閾値 0.3" in review and "vad_onset=0.3" in review and "標準" in review
    assert "実験用VAD閾値 0.3" in (out / "01_raw_transcript.md").read_text()
    meta = json.loads((out / "run_metadata.json").read_text())
    assert meta["vad"] == {"mode": "experimental", "onset": 0.3, "offset": 0.3, "threshold": 0.3}


def test_default_run_is_recorded_as_standard_and_has_no_experiment_banner(tmp_path, monkeypatch, capsys):
    rig = Rig(tmp_path, monkeypatch)
    rc, out = rig.run()
    assert "Experimental VAD" not in capsys.readouterr().err
    meta = json.loads((out / "run_metadata.json").read_text())
    assert meta["vad"] == {"mode": "default", "onset": 0.5, "offset": 0.363, "threshold": None}
    assert "実験用VAD" not in (out / "review_required.md").read_text()
    assert "実験用VAD" not in (out / "01_raw_transcript.md").read_text()


def test_explicit_output_dir_is_respected(tmp_path, monkeypatch):
    rig = Rig(tmp_path, monkeypatch)
    rc, out = rig.run("--vad-threshold", "0.3", out="my_own_dir")        # 勝手に別ディレクトリへ変えない
    assert out.name == "my_own_dir" and (out / "transcript.json").exists()
    assert not (tmp_path / "out").exists()


# ---------------------------------------------------------------- 10・11) 完走性
def test_experimental_run_completes_without_hf_token_or_api_keys(tmp_path, monkeypatch):
    monkeypatch.setattr("whisperx_runner.log", lambda m: None)
    rig = Rig(tmp_path, monkeypatch, hf_token=None)
    monkeypatch.setattr(dz, "run_diarization", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no token")))
    rc, out = rig.run("--vad-threshold", "0.3")
    assert rc == 0
    for f in ["01_raw_transcript.md", "02_clean_transcript.md", "03_magazine_interview.md", "transcript.json", "review_required.md"]:
        assert (out / f).exists(), f
    assert "話者分離に失敗" in (out / "review_required.md").read_text()
    assert "実験用VAD閾値 0.3" in (out / "review_required.md").read_text()


def test_default_run_still_completes_without_hf_token_or_api_keys(tmp_path, monkeypatch):
    rig = Rig(tmp_path, monkeypatch, hf_token=None)
    monkeypatch.setattr(dz, "run_diarization", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no token")))
    rc, out = rig.run()
    assert rc == 0 and (out / "03_magazine_interview.md").exists()
