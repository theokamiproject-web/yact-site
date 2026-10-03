"""テスト用: 合成の alignment 結果と、偽のLLM(Anthropic互換)サーバ。"""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer


def make_aligned(lines, char_dur=0.1):
    """lines: [(speaker, text)] → (aligned_result, diarization_segments)。発言間に1秒の間。"""
    words, diar, t = [], [], 0.0
    for spk, text in lines:
        s = t
        for ch in text:
            dur = 0.9 if ch == "。" else char_dur  # 文末の句読点に「間」が含まれるWhisperX挙動を模す
            words.append({"word": ch, "start": round(t, 3), "end": round(t + dur, 3), "score": 0.9})
            t += dur
        diar.append({"start": s, "end": t, "speaker": spk})
    seg = {"text": "".join(l[1] for l in lines), "start": 0.0, "end": t, "words": words}
    return {"segments": [seg], "language": "ja"}, diar


class FakeLLM:
    """handler(user_text) -> 返す本文。/v1/messages に Anthropic 形式で応答する。"""

    def __init__(self, handler):
        self.handler, self.calls = handler, []
        outer = self

        class H(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["content-length"])))
                user = body["messages"][0]["content"]
                outer.calls.append({"system": body["system"], "user": user, "key": self.headers.get("x-api-key")})
                try:
                    text, code = outer.handler(user), 200
                except Exception as e:  # noqa
                    text, code = str(e), 400
                payload = json.dumps({"content": [{"type": "text", "text": text}]} if code == 200
                                     else {"error": text}).encode()
                self.send_response(code)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *a):
                pass

        self.srv = HTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.srv.server_port}"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def close(self):
        self.srv.shutdown()
