import re
import os
from typing import Optional


def validateTemplate(type, text) -> Optional[dict]:
    headers = ["number", "title", "comment"]
    if type == "main":
        reg = r"Number: (\d+)\\nTitle: (.*?)\\nComment: (.*?)\\nChapters: \|\\n(.*?)$"
        headers.append("chapters")
    elif type == "aftershow":
        reg = r"Number: (\d+)\\nTitle: (.*?)\\nComment: (.*?)$"
    else:
        return None

    result = re.findall(reg, text.replace("\n", "\\n"), re.MULTILINE)
    if len(result) < 1 or len(result[0]) != len(headers):
        return None

    res = {}
    for index, i in enumerate(map(lambda s: s.replace("\\n", "\n"), result[0])):
        res[headers[index]] = i
    
    res["title"] = f'{res["number"]}. {res["title"]}'
    if "chapters" in res:
        res["chapters"] = list(map(lambda x: list(map(lambda x: x.strip(), re.split("-|—", x))), list(filter(lambda x: x != "", res["chapters"].split("\n")))))
    return res


def validatePath(path: str, encoding="UTF-8") -> None:
    if os.path.exists(path):
        return 
    with open(path, "w", encoding=encoding) as f:
        f.write("")