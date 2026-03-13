import re

def normalize_citations(text: str) -> str:
    """
    Normalize citation formats like:
    [Source 1, Source 2, Source 3]
    [Source 1], [Source 2]
    [Source 1]; [Source 2]

    into:
    [Source 1][Source 2][Source 3]
    """

    pattern = r"\[(Source\s*\d+(?:\s*[,;]\s*Source\s*\d+)+)\]"

    matches = re.findall(pattern, text)

    for match in matches:
        sources = re.findall(r"Source\s*\d+", match)

        normalized = "".join([f"[{s.strip()}]" for s in sources])

        text = text.replace(f"[{match}]", normalized)

    # also fix patterns like: [Source 1], [Source 2]
    text = re.sub(
        r"\[Source\s*(\d+)\]\s*[,;]\s*\[Source\s*(\d+)\]",
        r"[Source \1][Source \2]",
        text
    )

    return text