import os
import pytest
from utils.validators import validatePath, validateTemplate


def test_validateTemplate_01():
    typeEpisode = "main"

    text = """Number: 600
Title: Название эпизода
Comment: Описание эпизода
Chapters: |
00:00:07 - Вступление и что нового за неделю
00:28:53 - Название темы 1
01:40:56 - Название темы 2
02:17:25 - Озвучили наших патронов и анонсировали послешоу"""

    result = validateTemplate(typeEpisode, text)
    assert result == {'number': '600', 
                      'title': '600. Название эпизода',
                      'comment': 'Описание эпизода', 
                      'chapters': [
                                ['00:00:07', 'Вступление и что нового за неделю'],
                                ['00:28:53', 'Название темы 1'],
                                ['01:40:56', 'Название темы 2'],
                                ['02:17:25', 'Озвучили наших патронов и анонсировали послешоу']
                                ]}
    

def test_validateTemplate_02():
    typeEpisode = "aftershow"
    
    text = """Number: 600
Title: Название эпизода
Comment: Описание эпизода"""

    result = validateTemplate(typeEpisode, text)
    assert result == {'number': '600', 
                      'title': '600. Название эпизода',
                      'comment': 'Описание эпизода'}
    

def test_validateTemplate_03():
    typeEpisode = "aftershow"
    
    text = """Number: 600
Title: Название эпизода
Comment: Описание эпизода
Chapters: |
00:00:07 - Вступление и что нового за неделю
00:28:53 - Название темы 1
01:40:56 - Название темы 2
02:17:25 - Озвучили наших патронов и анонсировали послешоу"""

    result = validateTemplate(typeEpisode, text)
    assert result == {'number': '600', 
                      'title': '600. Название эпизода',
                      'comment': 'Описание эпизода\nChapters: |\n00:00:07 - Вступление и что нового за неделю\n00:28:53 - Название темы 1\n01:40:56 - Название темы 2\n02:17:25 - Озвучили наших патронов и анонсировали послешоу'}
    

def test_validateTemplate_04():
    typeEpisode = "aftershow"
    
    text = "Number: 600\nTitle: Название эпизода"

    result = validateTemplate(typeEpisode, text)
    assert result == None

    typeEpisode = "main"
    
    result = validateTemplate(typeEpisode, text)
    assert result == None


def test_validateTemplate_05():
    typeEpisode = "main"
    
    text = "Number: 600\n"

    result = validateTemplate(typeEpisode, text)
    assert result == None

    typeEpisode = "aftershow"
    
    result = validateTemplate(typeEpisode, text)
    assert result == None


def test_validateTemplate_06():
    typeEpisode = "main"
    
    text = ""

    result = validateTemplate(typeEpisode, text)
    assert result == None

    typeEpisode = "aftershow"
    
    result = validateTemplate(typeEpisode, text)
    assert result == None


def test_validatePath_01():
    path = "test"
    if os.path.exists(path):
        os.remove(path)
    validatePath(path)
    assert os.path.exists(path)
    os.remove(path)


def test_validatePath_02():
    path = "test"
    if os.path.exists(path):
        os.remove(path)
    validatePath(path)
    with open(path, "w") as f:
        f.write("TestTestTest")

    with open(path, "r") as f:
        assert f.read() == "TestTestTest"

    validatePath(path)
    with open(path, "r") as f:
        assert f.read() == "TestTestTest"

    assert validatePath(path) == None
    os.remove(path)