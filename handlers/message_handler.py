import logging

from aiogram import Router, Bot
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from states.bot_states import BotStates
from keyboards.keyboard_manager import KeyboardManager
from applications.language_scraper.scraper import scrape_languages, redis_client
from applications.cross_project_scraper import scrape_cross_project


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MessageHandler:
    def __init__(self, bot: Bot):
        self.bot = bot
        self.router = Router()
        self.setup_handlers()

    def setup_handlers(self):
        self.router.message.register(self.cmd_start, Command("start"))
        self.router.message.register(self.go_to_menu, lambda message: message.text == "🔗Link Scrapper", StateFilter(BotStates.main_menu))
        self.router.message.register(self.go_to_cross_project, lambda message: message.text == "🌍Cross-Project Scrapper", StateFilter(BotStates.main_menu))
        self.router.message.register(self.clear_cache, lambda message: message.text == "🗑️Clear Cache", StateFilter(BotStates.main_menu))
        self.router.message.register(self.back_to_main, lambda message: message.text == "🔙BACK", StateFilter(BotStates.secondary_menu))
        self.router.message.register(self.back_to_main, lambda message: message.text == "🔙BACK", StateFilter(BotStates.cross_project_menu))
        self.router.message.register(self.handle_message, StateFilter(BotStates.secondary_menu))
        self.router.message.register(self.handle_cross_project, StateFilter(BotStates.cross_project_menu))

    async def cmd_start(self, message: Message, state: FSMContext):
        await state.set_state(BotStates.main_menu)
        await message.answer(
            "🪼Hello World!",
            reply_markup=KeyboardManager.get_main_keyboard()
        )

    async def go_to_menu(self, message: Message, state: FSMContext):
        await state.set_state(BotStates.secondary_menu)
        await message.answer(
            "🔗Insert Links with 'https' start:",
            reply_markup=KeyboardManager.get_back_keyboard()
        )

    async def back_to_main(self, message: Message, state: FSMContext):
        await state.set_state(BotStates.main_menu)
        await message.answer(
            "🪼MAIN MENU",
            reply_markup=KeyboardManager.get_main_keyboard()
        )

    async def handle_message(self, message: Message):
        processing_msg = await message.answer("URL processing start, please wait...⏳")

        try:
            url = message.text

            results, error = await scrape_languages(url)

            if results:
                result_text = "Language links:\n\n"
                for lang_to_url in results:
                    if isinstance(lang_to_url, dict):
                        for lang, link in lang_to_url.items():
                            result_text += f"<b>{lang}:</b>\n{link}\n"
                        result_text += "\n-------------------------------------"
                    else:
                        result_text += f"Error: {lang_to_url}\n-------------------------------------\n"
                await message.answer(
                    result_text,
                    reply_markup=KeyboardManager.get_back_keyboard(),
                    parse_mode="HTML",
                    disable_web_page_preview=True
                )
            else:
                error_msg = "Could not find language versions for this URL"
                if error:
                    error_msg += f"\n{error}"

                await message.answer(
                    error_msg,
                    reply_markup=KeyboardManager.get_back_keyboard()
                )
        except Exception as e:
            logger.error(f"An error occurred during URL processing: {e}", exc_info=True)
            await message.answer(
                f"{str(e)}",
                reply_markup=KeyboardManager.get_back_keyboard()
            )
        finally:
            if processing_msg:
                try:
                    await processing_msg.delete()
                except Exception as e:
                    logger.error(f"Failed to delete processing_msg message: {e}", exc_info=True)

    async def clear_cache(self, message: Message):
        try:
            await redis_client.delete('cache', 'cache_keys')
            await message.answer("✅ Cache cleared successfully", reply_markup=KeyboardManager.get_main_keyboard())
        except Exception as e:
            logger.error(f"Failed to clear cache: {e}", exc_info=True)
            await message.answer(f"❌ Failed to clear cache: {e}", reply_markup=KeyboardManager.get_main_keyboard())

    async def go_to_cross_project(self, message: Message, state: FSMContext):
        await state.set_state(BotStates.cross_project_menu)
        await message.answer(
            "🌍Insert exist.ua link to find all languages across projects:",
            reply_markup=KeyboardManager.get_back_keyboard()
        )

    async def handle_cross_project(self, message: Message):
        processing_msg = await message.answer("Searching across projects, please wait...⏳")
        try:
            url = message.text.strip()
            result = await scrape_cross_project(url)

            lines = []
            for project, langs in result.items():
                if project == 'error':
                    lines.append(f"Error: {langs}")
                    continue
                lines.append(f"<b>── {project} ──</b>")
                if isinstance(langs, dict):
                    for lang, link in langs.items():
                        lines.append(f"<b>{lang}:</b>\n{link}")
                else:
                    lines.append(str(langs))
                lines.append("")

            result_text = "\n".join(lines) if lines else "No results found"
            await message.answer(
                result_text,
                reply_markup=KeyboardManager.get_back_keyboard(),
                parse_mode="HTML",
                disable_web_page_preview=True
            )
        except Exception as e:
            logger.error(f"Cross-project scraping error: {e}", exc_info=True)
            await message.answer(str(e), reply_markup=KeyboardManager.get_back_keyboard())
        finally:
            if processing_msg:
                try:
                    await processing_msg.delete()
                except Exception as e:
                    logger.error(f"Failed to delete processing_msg: {e}", exc_info=True)