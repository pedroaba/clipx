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
    clip_type: str  # 'color', 'url', 'code', 'text'
    language: Optional[str] = None
    color_hex: Optional[str] = None


class ContentDetector:
    @staticmethod
    def detect(content: str) -> DetectionResult:
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
