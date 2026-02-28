from aiogram.fsm.state import State, StatesGroup


class UploadFile(StatesGroup):
    type_episode = State()
    mp3 = State()
    template = State()
