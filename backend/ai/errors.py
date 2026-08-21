"""AI Module が投げるException。

Backend の Error Code へは `app` 側でMappingする。
ここでHTTP StatusやFrontend向け文言を決めない（層を混ぜない）。
"""

from __future__ import annotations


class AiError(Exception):
    """AI処理の失敗全般。"""


class AiTimeoutError(AiError):
    """所定時間内に結果を得られなかった。"""


class AiRateLimitedError(AiError):
    """Provider側のRate Limitに当たった。"""


class AiNotConfiguredError(AiError):
    """API Key / モデルID等の設定が足りない。"""
