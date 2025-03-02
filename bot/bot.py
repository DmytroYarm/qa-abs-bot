from aiogram import Bot, Dispatcher
import logging
from handlers.message_handler import MessageHandler

class TelegramBot:
    def __init__(self, token: str):
        self.bot = Bot(token=token)
        self.dp = Dispatcher()
        self.message_handler = MessageHandler(self.bot)
        self.setup_routers()

    def setup_routers(self):
        self.dp.include_router(self.message_handler.router)

    async def start(self):
        logging.basicConfig(level=logging.INFO)
        await self.dp.start_polling(self.bot)
