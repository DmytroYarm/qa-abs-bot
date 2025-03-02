import asyncio
import os

from dotenv import load_dotenv, find_dotenv

from config.config import Config
from bot.bot import TelegramBot


load_dotenv(find_dotenv())

async def main():
    config = Config(BOT_TOKEN=os.getenv("TOKEN"))
    bot = TelegramBot(config.BOT_TOKEN)
    await bot.start()

if __name__ == "__main__":
    asyncio.run(main())
