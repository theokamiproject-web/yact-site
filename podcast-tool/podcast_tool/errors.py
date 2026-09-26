"""利用者に原因と対処が伝わるエラー型。"""


class PodcastError(Exception):
    """処理を止めるべきエラー。step=どの工程か, hint=対処方法。"""

    def __init__(self, message: str, step: str = "", hint: str = ""):
        super().__init__(message)
        self.step = step
        self.hint = hint

    def render(self) -> str:
        lines = []
        if self.step:
            lines.append(f"[エラー] 工程: {self.step}")
        lines.append(f"[エラー] {self}")
        if self.hint:
            lines.append(f"[対処] {self.hint}")
        return "\n".join(lines)


class ConfigError(PodcastError):
    def __init__(self, message: str, hint: str = ""):
        super().__init__(message, step="設定ファイルの読込", hint=hint or "config/podcast.yaml を確認してください。")
