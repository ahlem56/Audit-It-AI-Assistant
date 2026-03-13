import json
import re


def extract_json_from_response(text: str):
    """
    Extract JSON object from an LLM response.
    """
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("No JSON object found in LLM response")

    json_str = match.group(0)
    return json.loads(json_str)