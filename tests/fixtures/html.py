"""Разбор отрендеренных страниц стандартным html.parser: заголовки, мета-теги, JSON-скрипты."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from html.parser import HTMLParser


@dataclass
class PageInfo:
    h1_count: int = 0
    title: str = ""
    meta: dict = field(default_factory=dict)
    canonical: list = field(default_factory=list)
    scripts: list = field(default_factory=list)  # (attrs, text)
    ids: list = field(default_factory=list)

    def scripts_of_type(self, kind: str) -> list[str]:
        return [text for attrs, text in self.scripts if attrs.get("type") == kind]

    def script_by_id(self, script_id: str) -> str | None:
        return next((text for attrs, text in self.scripts if attrs.get("id") == script_id), None)

    def json_ld(self) -> list:
        return [json.loads(text) for text in self.scripts_of_type("application/ld+json")]


class _Parser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.info = PageInfo()
        self._in_title = False
        self._script: tuple[dict, list] | None = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if attrs.get("id"):
            self.info.ids.append(attrs["id"])
        if tag == "h1":
            self.info.h1_count += 1
        elif tag == "title":
            self._in_title = True
        elif tag == "meta" and attrs.get("name"):
            self.info.meta[attrs["name"]] = attrs.get("content", "")
        elif tag == "link" and "canonical" in (attrs.get("rel") or "").split():
            self.info.canonical.append(attrs.get("href", ""))
        elif tag == "script":
            self._script = (attrs, [])

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        elif tag == "script" and self._script is not None:
            attrs, chunks = self._script
            self.info.scripts.append((attrs, "".join(chunks)))
            self._script = None

    def handle_data(self, data):
        if self._in_title:
            self.info.title += data
        if self._script is not None:
            self._script[1].append(data)


def inspect(html: str) -> PageInfo:
    parser = _Parser()
    parser.feed(html)
    parser.close()
    return parser.info
