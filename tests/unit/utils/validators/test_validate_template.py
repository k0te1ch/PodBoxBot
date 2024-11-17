import pytest
from app.utils.validators import validate_template


@pytest.mark.parametrize(
    "template",
    [
        "Number: 1\nTitle: Example header\nComment: Example comment",
        '<pre language="text">Number: 1\nTitle: Example header\nComment: Example comment</pre>',
    ],
)
def test_valid_template(template):
    expected_output = {"number": "1", "title": "1. Example header", "comment": "Example comment"}
    assert validate_template(template) == expected_output


@pytest.mark.parametrize(
    "template",
    [
        "Number: 2\nTitle: Another Example\nComment: Another comment\nTags: tag1, tag2\nChapters: |\nChapter 1 - Sub 1\nChapter 2 - Sub 2",
        '<pre language="text">Number: 2\nTitle: Another Example\nComment: Another comment\nTags: tag1, tag2\nChapters: |\nChapter 1 - Sub 1\nChapter 2 - Sub 2</pre>',
    ],
)
def test_template_with_chapters_and_tags(template):
    expected_output = {
        "number": "2",
        "title": "2. Another Example",
        "comment": "Another comment",
        "tags": {"tag1", "tag2"},  # Изменяем список на множество
        "chapters": [["Chapter 1", "Sub 1"], ["Chapter 2", "Sub 2"]],
    }
    result = validate_template(template)
    assert result is not None
    assert result["number"] == expected_output["number"]
    assert result["title"] == expected_output["title"]
    assert result["comment"] == expected_output["comment"]
    assert set(result["tags"]) == expected_output["tags"]  # Сравниваем множества
    assert result["chapters"] == expected_output["chapters"]


@pytest.mark.parametrize(
    "template",
    [
        "Number: 1\nTitle: Incomplete header\nComment:",
        '<pre language="text">Number: 1\nTitle: Incomplete header\nComment:</pre>',
    ],
)
def test_invalid_template(template):
    assert validate_template(template) is None


@pytest.mark.parametrize(
    "template",
    [
        "Number: 3\nTitle: Example with extra fields\nComment: Example comment\nExtra: unexpected field",
        '<pre language="text">Number: 3\nTitle: Example with extra fields\nComment: Example comment\nExtra: unexpected field</pre>',
    ],
)
def test_template_with_extra_fields(template):
    expected_output = {
        "number": "3",
        "title": "3. Example with extra fields",
        "comment": "Example comment\nExtra: unexpected field",
    }
    assert validate_template(template) == expected_output  # Проверяем корректность извлечённого шаблона


@pytest.mark.parametrize("template", ["Number: 675\nTitle: Учимся на стульях\nComment: Рассказали кто что посмотрел, кто что прочитал, а кто успел и поболеть. В темах проговорили про потребительский терроризм, про полезность или бесполезность онлайн-курсов и про внутреннюю кухню продавцов на маркетплейсах.\nTags: стулья, маркетплейсы, бизнес, потребители, застройщики, квартиры, терроризм, онлайн-курсы, полезность, бесполезность\nChapters: |\n00:00:07 - Вступление и что нового за неделю\n00:31:20 - Потребительский терроризм\n00:44:46 - Онлайн-курсы вряд ли сделают из вас топового специалиста\n00:59:13 - Как продавать на маркетплейсах?\n01:40:09 - Озвучили наших патронов и анонсировали послешоу", '<pre language="text">Number: 675\nTitle: Учимся на стульях\nComment: Рассказали кто что посмотрел, кто что прочитал, а кто успел и поболеть. В темах проговорили про потребительский терроризм, про полезность или бесполезность онлайн-курсов и про внутреннюю кухню продавцов на маркетплейсах.\nTags: стулья, маркетплейсы, бизнес, потребители, застройщики, квартиры, терроризм, онлайн-курсы, полезность, бесполезность\nChapters: |\n00:00:07 - Вступление и что нового за неделю\n00:31:20 - Потребительский терроризм\n00:44:46 - Онлайн-курсы вряд ли сделают из вас топового специалиста\n00:59:13 - Как продавать на маркетплейсах?\n01:40:09 - Озвучили наших патронов и анонсировали послешоу</pre>'])
def test_template_with_multiple_tags_and_chapters(template):
    expected_output = {
        "number": "675",
        "title": "675. Учимся на стульях",
        "comment": "Рассказали кто что посмотрел, кто что прочитал, а кто успел и поболеть. В темах проговорили про потребительский терроризм, про полезность или бесполезность онлайн-курсов и про внутреннюю кухню продавцов на маркетплейсах.",
        "tags": {
            "стулья",
            "маркетплейсы",
            "бизнес",
            "потребители",
            "застройщики",
            "квартиры",
            "терроризм",
            "онлайн-курсы",
            "полезность",
            "бесполезность",
        },
        "chapters": [
            ["00:00:07", "Вступление и что нового за неделю"],
            ["00:31:20", "Потребительский терроризм"],
            ["00:44:46", "Онлайн-курсы вряд ли сделают из вас топового специалиста"],
            ["00:59:13", "Как продавать на маркетплейсах?"],
            ["01:40:09", "Озвучили наших патронов и анонсировали послешоу"],
        ],
    }
    result = validate_template(template)
    assert result is not None
    assert result["number"] == expected_output["number"]
    assert result["title"] == expected_output["title"]
    assert result["comment"] == expected_output["comment"]
    assert set(result["tags"]) == expected_output["tags"]
    assert result["chapters"] == expected_output["chapters"]
