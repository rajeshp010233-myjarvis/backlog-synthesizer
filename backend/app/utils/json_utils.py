"""Robust JSON extraction from LLM responses that may include markdown fences."""

import re
import json
from typing import Any


def extract_json(raw: str) -> Any:
    """Extract a JSON object or array from an LLM response string.

    Tries (in order):
    1. Direct parse of the trimmed response.
    2. Content inside a ```json ... ``` or ``` ... ``` code fence.
    3. The first JSON object (``{...}``) found via regex.
    4. The first JSON array  (``[...]``) found via regex.

    Raises ValueError if no valid JSON can be found.
    """
    text = raw.strip()

    # 1. Direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 2. Code-fence extraction
    fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if fence_match:
        try:
            return json.loads(fence_match.group(1))
        except json.JSONDecodeError:
            pass

    # 3. First {...} blob
    obj_match = re.search(r"\{[\s\S]*\}", text)
    if obj_match:
        try:
            return json.loads(obj_match.group(0))
        except json.JSONDecodeError:
            pass

    # 4. First [...] blob
    arr_match = re.search(r"\[[\s\S]*\]", text)
    if arr_match:
        try:
            return json.loads(arr_match.group(0))
        except json.JSONDecodeError:
            pass

    raise ValueError(f"No valid JSON found in LLM response (first 300 chars): {text[:300]!r}")
