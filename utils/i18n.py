"""国际化工具模块"""
import json
import os
from pathlib import Path

_I18N_DIR = Path(__file__).parent.parent / "i18n"


class I18N:
    """国际化管理器，支持运行时切换语言"""

    def __init__(self, lang: str = "zh"):
        self._lang = lang
        self._translations: dict[str, dict[str, str]] = {}
        self._load_all()

    def _load_all(self):
        for f in _I18N_DIR.glob("*.json"):
            lang = f.stem
            with open(f, "r", encoding="utf-8") as fp:
                self._translations[lang] = json.load(fp)

    @property
    def lang(self) -> str:
        return self._lang

    @lang.setter
    def lang(self, value: str):
        if value in self._translations:
            self._lang = value

    @property
    def available_languages(self) -> list[str]:
        return list(self._translations.keys())

    def t(self, key: str, **kwargs) -> str:
        """获取翻译文本，支持 {placeholder} 格式化"""
        text = self._translations.get(self._lang, {}).get(key, key)
        if kwargs:
            try:
                text = text.format(**kwargs)
            except KeyError:
                pass
        return text

    def __getitem__(self, key: str) -> str:
        return self.t(key)


# 全局单例
i18n = I18N()
