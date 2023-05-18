from aiogram.dispatcher.filters.state import State, StatesGroup


class UploadFile(StatesGroup):
    mp3 = State()
    template = State()
    