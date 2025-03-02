from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

class KeyboardManager:
    @staticmethod
    def get_main_keyboard() -> ReplyKeyboardMarkup:
        keyboard = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="🔗Link Scrapper")]],
            resize_keyboard=True
        )
        return keyboard

    @staticmethod
    def get_back_keyboard() -> ReplyKeyboardMarkup:
        keyboard = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="🔙BACK")]],
            resize_keyboard=True
        )
        return keyboard
