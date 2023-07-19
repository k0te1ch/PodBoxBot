from aiogram.filters.state import State, StatesGroup


class UploadFile(StatesGroup):
    typeEpisode = State()
    mp3 = State()
    template = State()
    