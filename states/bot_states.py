from aiogram.fsm.state import State, StatesGroup

class BotStates(StatesGroup):
    main_menu = State()
    secondary_menu = State()
    cross_project_menu = State()