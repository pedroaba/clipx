"""Heuristic classification of clipboard text.

The detector recognizes colors, URLs, JSON, and common source-code patterns.
Pygments is used when installed but is treated as an optional enhancement.
"""

import json
import re
from dataclasses import dataclass
from typing import Optional, Tuple

try:
    from pygments.lexers import guess_lexer, get_lexer_by_name
    from pygments.util import ClassNotFound
    HAS_PYGMENTS = True
except ImportError:
    HAS_PYGMENTS = False

HEX_COLOR_REGEX = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")
RGB_COLOR_REGEX = re.compile(r"^rgba?\(\s*\d+\s*,\s*\d+\s*,\s*\d+\s*(?:,\s*[\d.]+\s*)?\)$", re.IGNORECASE)
HSL_COLOR_REGEX = re.compile(r"^hsla?\(\s*\d+\s*,\s*[\d.]+%?\s*,\s*[\d.]+%?\s*(?:,\s*[\d.]+\s*)?\)$", re.IGNORECASE)
URL_REGEX = re.compile(r"^(https?|ftp|file)://[^\s/$.?#].[^\s]*$", re.IGNORECASE)


@dataclass
class DetectionResult:
    """Classification assigned to a piece of clipboard content.

    Attributes:
        clip_type (str): One of ``"color"``, ``"url"``, ``"code"``, or
            ``"text"``.
        language (Optional[str]): Detected programming or markup language for
            code clips; None otherwise.
        color_hex (Optional[str]): Normalized hex color for hex and RGB inputs,
            the original HSL(A) text for HSL inputs, or None for other types.
    """

    clip_type: str  # 'color', 'url', 'code', 'text'
    language: Optional[str] = None
    color_hex: Optional[str] = None


class ContentDetector:
    """Stateless helpers that classify clipboard content heuristically."""

    @staticmethod
    def detect(content: str) -> DetectionResult:
        """Classify content as a color, URL, code, or plain text.

        Detection checks, in order: hex/RGB/HSL colors, URLs, valid JSON,
        language-specific and symbol-based code heuristics, then plain text.
        Empty or whitespace-only content is classified as text.

        Args:
            content (str): Clipboard text to inspect.

        Returns:
            DetectionResult: The detected type and any associated metadata.
        """
        stripped = content.strip()
        if not stripped:
            return DetectionResult(clip_type="text")

        # 1. Check Color
        if HEX_COLOR_REGEX.match(stripped):
            return DetectionResult(clip_type="color", color_hex=stripped.upper())
        if RGB_COLOR_REGEX.match(stripped):
            return DetectionResult(clip_type="color", color_hex=ContentDetector._rgb_to_hex(stripped))
        if HSL_COLOR_REGEX.match(stripped):
            return DetectionResult(clip_type="color", color_hex=stripped)

        # 2. Check URL
        if URL_REGEX.match(stripped):
            return DetectionResult(clip_type="url")

        # 3. Check JSON
        if (stripped.startswith("{") and stripped.endswith("}")) or (stripped.startswith("[") and stripped.endswith("]")):
            try:
                json.loads(stripped)
                return DetectionResult(clip_type="code", language="json")
            except Exception:
                pass

        # 4. Check Code heuristics
        is_code, lang = ContentDetector._check_code(content)
        if is_code:
            return DetectionResult(clip_type="code", language=lang)

        return DetectionResult(clip_type="text")

    @staticmethod
    def _rgb_to_hex(rgb_str: str) -> Optional[str]:
        """Convert an RGB/RGBA function string to an uppercase hex color.

        The first three integers in the string are used. Each channel is
        clamped to the 0-255 range.

        Args:
            rgb_str (str): RGB or RGBA function text such as ``rgb(12, 34, 56)``.

        Returns:
            Optional[str]: ``#RRGGBB`` when three channel values are present,
            otherwise None.
        """
        nums = re.findall(r"\d+", rgb_str)
        if len(nums) >= 3:
            r, g, b = int(nums[0]), int(nums[1]), int(nums[2])
            r = min(255, max(0, r))
            g = min(255, max(0, g))
            b = min(255, max(0, b))
            return f"#{r:02X}{g:02X}{b:02X}"
        return None

    @staticmethod
    def _check_code(text: str) -> Tuple[bool, Optional[str]]:
        """Score text using language keywords and common programming symbols.

        Keyword matches contribute three points each and symbol occurrences one
        point each. When Pygments is available, it is consulted if the score is
        at least two or the text spans more than two lines; a non-plain lexer
        result marks the text as code. Otherwise a score of at least three
        marks it as code.

        Args:
            text (str): Clipboard text to evaluate.

        Returns:
            Tuple[bool, Optional[str]]: Whether the text is code and, when
            known, its language name or alias.
        """
        lines = text.splitlines()
        code_score = 0
        detected_lang = None

        code_keywords = [
            (r"\b(def|class|import|from|elif|lambda)\b", "python"),
            (r"\b(const|let|var|function|console\.log|=>)\b", "javascript"),
            (r"\b(SELECT|INSERT|UPDATE|DELETE|FROM|WHERE|JOIN)\b", "sql"),
            (r"^(#include|int main\(|void\s+\w+\()", "c"),
            (r"\b(fn\s+main|pub\s+fn|impl|struct|enum|match\s+)\b", "rust"),
            (r"^(package\s+main|func\s+\w+\(|import\s*\()", "go"),
            (r"^(<!DOCTYPE\s+html|<html|<div|<span|<body)", "html"),
            (r"^(#!\/bin\/(bash|sh|zsh)|curl\s+|chmod\s+|sudo\s+)", "bash"),
        ]

        for pattern, lang in code_keywords:
            if re.search(pattern, text, re.IGNORECASE if lang == "sql" else 0):
                code_score += 3
                if not detected_lang:
                    detected_lang = lang

        symbols = [";", "{", "}", "(", ")", "=>", "==", "!=", "::", "->"]
        for sym in symbols:
            if sym in text:
                code_score += 1

        # Check Pygments guesser if available
        if HAS_PYGMENTS and (code_score >= 2 or len(lines) > 2):
            try:
                lexer = guess_lexer(text)
                if lexer and lexer.name.lower() not in ("text", "plain text"):
                    norm = lexer.aliases[0] if lexer.aliases else lexer.name.lower()
                    return True, detected_lang or norm
            except Exception:
                pass

        if code_score >= 3:
            return True, detected_lang or "code"

        return False, None
