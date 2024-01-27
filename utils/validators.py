import re
import os
from typing import Optional


def validateTemplate(text: str) -> Optional[dict]:
    """
    Validation of a text template and information extraction.

    Arguments:
    text (str): A text block.

    Is returning:
    Optional[dictation]: Information from the text database in the form of a dictionary.
    It does not arouse anyone's suspicions in connection with the flexibility of validation.

    Example:
    >>> template = "Number: 1\\nTitle: Example header\\nComment: Example comment"
    >>> validate_template(template)
    {'number': '1', 'title': '1. Example of a header', 'comment': 'Example of a comment'}
    """
    headers = ["number", "title", "comment"]
    if "chapters" in text.lower():
        reg = r"Number: (\d+)\\nTitle: (.*?)\\nComment: (.*?)\\nTags: (.*?)\\nChapters: \|\\n(.*?)$"
        headers.extend(["tags", "chapters"])
    else:
        reg = r"Number: (\d+)\\nTitle: (.*?)\\nComment: (.*?)$"

    result = re.findall(reg, text.replace("\n", "\\n"), re.MULTILINE)
    if not result or len(result[0]) != len(headers):
        return None

    res = {
        header: value.replace("\\n", "\n") for header, value in zip(headers, result[0])
    }

    res["title"] = f'{res["number"]}. {res["title"]}'
    if "chapters" in res:
        res["chapters"] = [
            list(map(lambda x: x.strip(), re.split("-|—", x)))
            for x in filter(None, res["chapters"].split("\n"))
        ]
    if "tags" in res:
        res["tags"] = list(set(re.split(", |,| ,", res["tags"])))
    return res


def validatePath(path: str, encoding="UTF-8") -> None:
    if os.path.exists(path):
        return
    with open(path, "w", encoding=encoding) as f:
        f.write("")
