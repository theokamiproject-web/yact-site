"""雑誌対談向けの整文。音声認識・話者分離から独立したモジュール。

- 標準は rule（外部LLMなし・無料）。LLMは --editor で明示したときだけ使うオプション機能。
- プロバイダ: rule / local（Ollama等のOpenAI互換API。無料） / claude / openai（有料API）
- APIキーは環境変数（.env）から読む。コードには書かない。環境にキーがあっても自動では使わない。
- 全文を一度に渡さず、話者交替・間・長さを見て会話のまとまり(chunk)に分け、
  前文脈を重複させる。出力は編集対象のturn idだけなので、重複出力は構造上発生しない。
- 結果は chunk 単位でキャッシュし、途中失敗しても再開できる。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from text_utils import effective_raw, tidy_punct

PROMPT_VERSION = "v1"
DROP_TOKEN = "<削除>"

SYSTEM_PROMPT = f"""あなたは日本語雑誌の対談記事を編集する編集者です。

以下の文章は音声から生成された逐語録です。
目的は、発言内容を変えずに読みやすい対談原稿へ整えることです。

【禁止事項】
- 原文にない情報を追加しない
- 要約しない
- 新しい発言を作らない
- 発言者を変更しない（発言を別の番号・別の話者へ移さない）
- 数字を変更しない
- 日付を変更しない
- 固有名詞を推測しない（表記ゆれの統一もしない。原文のまま）
- 聞き取れない部分を補完しない（[聞き取り不明 ...] はそのまま残す）
- 発言者の意見を強めたり弱めたりしない（「たぶん」「〜くらい」「〜と思う」などのぼかしは残す）
- 否定・肯定を変えない

【許可する編集】
- フィラー（えー、あのー、まあ、なんか 等）の削除
- 重複・不要な言い直しの整理
- 読点の調整
- 不自然な音声認識の区切りの結合
- 意味のない相槌の削除（聞き手の単純な「はい」「うん」「なるほど」「そうですね」）

【残すもの】
- 質問への返答など、意味のある応答（例: 「そうだったんですか？」「そうなんですよ。」）
- 話者本人の言葉遣い、語尾、話し方、キャラクター、口癖、重要な間
- 話し言葉のまま（「〜と説明した」のような地の文・三人称への書き換えは禁止）

【入出力の形式】
入力は「前の文脈（参考）」と「編集対象」で、各行は `[id] 話者: 発言` です。
「編集対象」の各行だけを、同じ id で1行ずつ出力してください。
- 行の順序と id は変えない。1つの id の内容を別の id に移さない。
- 発言全体を削除する場合は `[id] {DROP_TOKEN}` と出力する。
- 話者名は出力しない。発言テキストだけを書く。
- 説明・前置き・コードブロックは一切出力しない。"""


# ------------------------------------------------------------------ providers
class EditorError(RuntimeError):
    pass


class BaseEditor:
    name = "base"
    model = ""

    @property
    def cache_id(self) -> str:
        return f"{self.name}:{self.model}:{PROMPT_VERSION}"

    def complete(self, system: str, user: str) -> str:  # pragma: no cover
        raise NotImplementedError


class RuleEditor(BaseEditor):
    """LLMを使わない。ルールベースのclean結果をそのまま採用する。"""
    name = "rule"


def _http_json(url: str, headers: dict, body: dict, timeout: int = 180, retries: int = 4) -> dict:
    data = json.dumps(body).encode("utf-8")
    last: Exception | None = None
    for attempt in range(retries):
        req = urllib.request.Request(url, data=data, headers={"content-type": "application/json", **headers})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:300]
            last = EditorError(f"HTTP {e.code}: {detail}")
            if e.code not in (408, 429, 500, 502, 503, 504, 529):
                raise last
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last = EditorError(f"通信エラー: {e}")
        time.sleep(2 ** (attempt + 1))
    raise last or EditorError("unknown error")


class ClaudeEditor(BaseEditor):
    name = "claude"

    def __init__(self, api_key: str, model: str, base_url: str = "https://api.anthropic.com"):
        self.api_key, self.model, self.base_url = api_key, model, base_url.rstrip("/")

    def complete(self, system: str, user: str) -> str:
        res = _http_json(f"{self.base_url}/v1/messages",
                         {"x-api-key": self.api_key, "anthropic-version": "2023-06-01"},
                         {"model": self.model, "max_tokens": 8192, "temperature": 0, "system": system,
                          "messages": [{"role": "user", "content": user}]})
        return "".join(b.get("text", "") for b in res.get("content", []) if b.get("type") == "text")


class OpenAICompatEditor(BaseEditor):
    """OpenAI API、および Ollama / llama.cpp / vLLM などOpenAI互換のローカルLLM。"""

    def __init__(self, api_key: str | None, model: str, base_url: str, name: str = "openai"):
        self.api_key, self.model, self.base_url, self.name = api_key, model, base_url.rstrip("/"), name

    def complete(self, system: str, user: str) -> str:
        headers = {"authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        res = _http_json(f"{self.base_url}/chat/completions", headers,
                         {"model": self.model, "temperature": 0,
                          "messages": [{"role": "system", "content": system},
                                       {"role": "user", "content": user}]})
        return res["choices"][0]["message"]["content"]


def get_editor(provider: str | None = None, model: str | None = None) -> BaseEditor:
    """provider: rule（標準・LLM不使用）| local（OpenAI互換のローカルLLM）| claude | openai。

    標準は rule。APIキーが環境にあっても、明示指定がなければ外部APIは呼ばない。
    """
    env = os.environ
    provider = (provider or env.get("EDITOR_PROVIDER") or "rule").lower()
    model = model or env.get("EDITOR_MODEL")
    if provider in ("rule", "auto", "none"):
        return RuleEditor()
    if provider == "claude":
        key = env.get("ANTHROPIC_API_KEY")
        if not key:
            raise EditorError("ANTHROPIC_API_KEY が未設定です（.env を確認）")
        return ClaudeEditor(key, model or env.get("ANTHROPIC_MODEL", "claude-sonnet-5-5"),
                            env.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com"))
    if provider == "openai":
        key = env.get("OPENAI_API_KEY")
        if not key:
            raise EditorError("OPENAI_API_KEY が未設定です（.env を確認）")
        return OpenAICompatEditor(key, model or env.get("OPENAI_MODEL", "gpt-4.1"),
                                  env.get("OPENAI_BASE_URL", "https://api.openai.com/v1"))
    if provider == "local":
        base = env.get("LOCAL_LLM_BASE_URL")
        if not base:
            raise EditorError("LOCAL_LLM_BASE_URL が未設定です（例: http://localhost:11434/v1）")
        return OpenAICompatEditor(env.get("LOCAL_LLM_API_KEY"), model or env.get("LOCAL_LLM_MODEL", "local-model"),
                                  base, name="local")
    raise EditorError(f"未知のエディタ: {provider}")


# ------------------------------------------------------------------ chunking
def _line(t: dict) -> str:
    return f"[{t['id']}] {t['speaker_name']}: {effective_raw(t)}"


def build_chunks(turns: list[dict], target_chars: int = 2500, max_chars: int = 3600,
                 context_turns: int = 3, context_chars: int = 700) -> list[dict]:
    """会話のまとまり単位に分割。切れ目は 話者の交替・間・文末 を評価して選ぶ。

    返り値: [{"target": [turn,...], "context": [turn,...]}]
    """
    chunks: list[dict] = []
    n, i = len(turns), 0
    while i < n:
        size, j = 0, i
        while j < n and size + len(turns[j]["raw_text"]) <= max_chars:
            size += len(turns[j]["raw_text"])
            j += 1
        j = max(j, i + 1)
        if j < n:  # 続きがある → [0.6*target, j] の範囲で最も自然な切れ目を探す
            best_k, best_score, acc = j, -1.0, 0
            for k in range(i + 1, j + 1):
                acc += len(turns[k - 1]["raw_text"])
                if acc < target_chars * 0.6 or k == n:
                    continue
                prev, nxt = turns[k - 1], turns[k]
                score = prev.get("pause_after", 0.0)
                score += 0.8 if prev["speaker_id"] != nxt["speaker_id"] else 0.0
                score += 0.3 if prev["raw_text"].rstrip()[-1:] in "。？！?!" else 0.0
                score -= abs(acc - target_chars) / max(target_chars, 1) * 0.5  # 目標長から離れすぎない
                if score >= best_score:
                    best_k, best_score = k, score
            j = best_k
        target = turns[i:j]
        ctx: list[dict] = []
        total = 0
        for t in reversed(turns[max(0, i - context_turns):i]):
            if total + len(t["raw_text"]) > context_chars and ctx:
                break
            ctx.insert(0, t)
            total += len(t["raw_text"])
        chunks.append({"target": target, "context": ctx})
        i = j
    return chunks


def chunk_prompt(chunk: dict) -> str:
    parts = []
    if chunk["context"]:
        parts += ["【前の文脈（参考。出力しないこと）】"] + [_line(t) for t in chunk["context"]] + [""]
    parts += ["【編集対象（この各行を同じidで出力）】"] + [_line(t) for t in chunk["target"]]
    return "\n".join(parts)


_OUT_RE = re.compile(r"^\s*\[(\d+)\]\s*(.*)$")


def parse_output(text: str, expected_ids: list[int]) -> dict[int, str]:
    """`[id] 本文` 形式を解析。編集対象外のidは捨て、重複idは最初のものを採用する。"""
    out: dict[int, str] = {}
    last: int | None = None
    exp = set(expected_ids)
    for ln in text.splitlines():
        m = _OUT_RE.match(ln)
        if m:
            last = int(m.group(1))
            if last in exp and last not in out:
                body = m.group(2).strip()
                out[last] = "" if body == DROP_TOKEN else body
            else:
                last = None  # 文脈idや重複は無視
        elif ln.strip() and last is not None and last in out and out[last] != "":
            out[last] += ln.strip()  # 折返し行は直前idに連結
    # 話者ラベルが紛れ込んでいたら落とす（本文の一部とは扱わない。検出は quality_check 側でも行う）
    return out


# ------------------------------------------------------------------ run
@dataclass
class EditResult:
    texts: dict[int, str]          # id -> 編集後（"" は削除）
    sources: dict[int, str]        # id -> llm / rule / rule-fallback
    notes: list[str]


def run_edit(turns: list[dict], editor: BaseEditor, cache_path: Path | None = None,
             target_chars: int = 2500, log=lambda m: print(m, file=sys.stderr, flush=True)) -> EditResult:
    texts: dict[int, str] = {}
    sources: dict[int, str] = {}
    notes: list[str] = []
    if isinstance(editor, RuleEditor):
        for t in turns:
            texts[t["id"]] = tidy_punct(t["clean_text"])
            sources[t["id"]] = "rule"
        return EditResult(texts, sources, notes)

    cache: dict = {}
    if cache_path and Path(cache_path).exists():
        cache = json.loads(Path(cache_path).read_text(encoding="utf-8"))
    chunks = build_chunks(turns, target_chars=target_chars)
    for ci, ch in enumerate(chunks, 1):
        ids = [t["id"] for t in ch["target"]]
        user = chunk_prompt(ch)
        key = hashlib.sha1((editor.cache_id + user).encode("utf-8")).hexdigest()
        if key in cache:
            got = {int(k): v for k, v in cache[key].items()}
            log(f"[編集] chunk {ci}/{len(chunks)} キャッシュ使用")
        else:
            log(f"[編集] chunk {ci}/{len(chunks)}（{len(ids)}発言）{editor.name}:{editor.model}")
            try:
                got = parse_output(editor.complete(SYSTEM_PROMPT, user), ids)
            except Exception as e:  # noqa: BLE001 - 1chunkの失敗で全体を止めない
                notes.append(f"chunk {ci}（発言ID {ids[0]}–{ids[-1]}）のLLM編集に失敗: {e}。ルール整文で代替しました。")
                log(f"[警告] {notes[-1]}")
                got = {}
            if got and cache_path:
                cache[key] = {str(k): v for k, v in got.items()}
                Path(cache_path).parent.mkdir(parents=True, exist_ok=True)
                Path(cache_path).write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
        for t in ch["target"]:
            if t["id"] in got:
                texts[t["id"]], sources[t["id"]] = got[t["id"]], "llm"
            else:
                texts[t["id"]], sources[t["id"]] = t["clean_text"], "rule-fallback"
        missing = [i for i in ids if i not in got]
        if got and missing:
            notes.append(f"chunk {ci}: LLMが {len(missing)} 発言（ID {missing[:5]}…）を返さなかったためルール整文で代替しました。")
    return EditResult(texts, sources, notes)
