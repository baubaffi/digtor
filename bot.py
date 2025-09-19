"""Главный модуль телеграм-бота для проекта "Цифровой Торжокъ"."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (Application, CallbackQueryHandler, CommandHandler,
                          ContextTypes)
from telegram.error import TelegramError

# Включаем логирование для удобной отладки и мониторинга
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Attraction:
    """Структура данных, описывающая достопримечательность."""

    identifier: str
    name: str
    description: str
    address: str
    latitude: float
    longitude: float
    image_url: str

    @property
    def map_link(self) -> str:
        """Ссылка на карту с точкой достопримечательности."""

        return (
            "https://yandex.ru/maps/?" f"pt={self.longitude},{self.latitude}&z=16&l=map"
        )

    @property
    def route_link(self) -> str:
        """Ссылка на построение маршрута до точки."""

        return (
            "https://yandex.ru/maps/?"
            f"rtext=~{self.latitude}%2C{self.longitude}&rtt=auto"
        )


class AttractionStorage:
    """Хранилище данных о достопримечательностях."""

    def __init__(self, items: List[Attraction]) -> None:
        # Сохраняем элементы в словарь для быстрого доступа по идентификатору
        self._items: Dict[str, Attraction] = {item.identifier: item for item in items}

    @classmethod
    def from_json(cls, path: Path) -> "AttractionStorage":
        """Загружает достопримечательности из JSON-файла."""

        if not path.exists():
            raise FileNotFoundError(f"Файл с достопримечательностями не найден: {path}")

        with path.open("r", encoding="utf-8") as fh:
            payload = json.load(fh)

        attractions = [
            Attraction(
                identifier=item["id"],
                name=item["name"],
                description=item["description"],
                address=item["address"],
                latitude=float(item["coordinates"]["lat"]),
                longitude=float(item["coordinates"]["lon"]),
                image_url=item["image_url"],
            )
            for item in payload
        ]
        return cls(attractions)

    def all(self) -> List[Attraction]:
        """Возвращает список всех достопримечательностей."""

        return list(self._items.values())

    def get(self, identifier: str) -> Attraction | None:
        """Возвращает конкретную достопримечательность по идентификатору."""

        return self._items.get(identifier)


def build_main_menu_keyboard() -> InlineKeyboardMarkup:
    """Создаёт клавиатуру главного меню."""

    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(text="📍 Достопримечательности", callback_data="menu:attractions")],
            [InlineKeyboardButton(text="ℹ️ Советы по использованию", callback_data="menu:help")],
        ]
    )


def build_attractions_keyboard(attractions: List[Attraction]) -> InlineKeyboardMarkup:
    """Создаёт клавиатуру со списком достопримечательностей."""

    buttons = [
        [InlineKeyboardButton(text=item.name, callback_data=f"attraction:{item.identifier}")]
        for item in attractions
    ]
    buttons.append([InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="menu:main")])
    return InlineKeyboardMarkup(buttons)


async def delete_previous_photo(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> None:
    """Удаляет ранее отправленную фотографию, если она ещё есть в чате."""

    message_id = context.user_data.pop("photo_message_id", None)
    if not message_id:
        return

    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
    except TelegramError as exc:  # pragma: no cover - зависит от взаимодействия с API
        logger.debug("Не удалось удалить старую фотографию: %s", exc)


async def send_main_menu(
    update: Update, context: ContextTypes.DEFAULT_TYPE, *, via_callback: bool = False
) -> None:
    """Отображает главное меню с кнопками навигации."""

    keyboard = build_main_menu_keyboard()
    text = (
        "Здравствуйте, {name}! Я виртуальный гид проекта «Цифровой Торжокъ».\n"
        "С моей помощью вы узнаете историю главных достопримечательностей и сразу получите ссылки на карты.\n"
        "Выберите раздел на кнопках ниже, чтобы начать путешествие по городу."
    ).format(name=update.effective_user.first_name if update.effective_user else "")

    chat = update.effective_chat
    if chat is not None:
        await delete_previous_photo(context, chat.id)

    if via_callback and update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=keyboard)
        return

    if update.message:
        await update.message.reply_text(text, reply_markup=keyboard)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает команду /start и приветствует пользователя."""

    await send_main_menu(update, context)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает команду /help и выводит подсказку."""

    help_text = (
        "Чтобы познакомиться с Торжком, используйте кнопки главного меню.\n"
        "Кнопка «Достопримечательности» покажет список объектов с маршрутами, а «Советы по использованию» — подсказки по работе с ботом.\n"
        "Если вы хотите вернуться к началу, просто нажмите «Назад в меню»."
    )

    if update.message:
        chat = update.effective_chat
        if chat is not None:
            await delete_previous_photo(context, chat.id)
        await update.message.reply_text(help_text, reply_markup=build_main_menu_keyboard())


async def show_attractions(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Отправляет пользователю список доступных достопримечательностей."""

    storage: AttractionStorage = context.application.bot_data["storage"]
    attractions = storage.all()

    if not attractions:
        if update.callback_query and update.callback_query.message:
            await update.callback_query.edit_message_text(
                "Извините, список достопримечательностей пока пуст. Попробуйте позже."
            )
        elif update.message:
            await update.message.reply_text(
                "Извините, список достопримечательностей пока пуст. Попробуйте позже."
            )
        return

    reply_markup = build_attractions_keyboard(attractions)
    text = "Выберите достопримечательность, чтобы узнать подробности и увидеть фотографию:"

    chat = update.effective_chat
    if chat is not None:
        await delete_previous_photo(context, chat.id)

    if update.callback_query and update.callback_query.message:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup)
        return

    if update.message:
        await update.message.reply_text(text, reply_markup=reply_markup)


async def attraction_details(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Выводит подробную информацию о выбранной достопримечательности."""

    query = update.callback_query
    if query is None or query.data is None:
        logger.warning("Получен пустой запрос от пользователя")
        return

    await query.answer()

    _, _, identifier = query.data.partition(":")
    storage: AttractionStorage = context.application.bot_data["storage"]
    attraction = storage.get(identifier)

    if not attraction:
        await query.edit_message_text(
            "К сожалению, не удалось найти информацию об этой достопримечательности."
        )
        return

    message_lines = [
        f"<b>{attraction.name}</b>",
        f"Адрес: {attraction.address}",
        "",
        attraction.description,
        "",
        "Выберите действие на кнопках ниже:",
    ]

    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(text="🗺 Открыть на карте", url=attraction.map_link)],
            [InlineKeyboardButton(text="🚗 Маршрут на Яндекс.Картах", url=attraction.route_link)],
            [InlineKeyboardButton(text="⬅️ Назад к списку", callback_data="menu:attractions")],
        ]
    )

    await query.edit_message_text(
        "\n".join(message_lines),
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard,
        disable_web_page_preview=True,
    )

    if query.message and query.message.chat:
        chat_id = query.message.chat.id
        await delete_previous_photo(context, chat_id)
        photo_message = await context.bot.send_photo(
            chat_id=chat_id,
            photo=attraction.image_url,
            caption=attraction.name,
            parse_mode=ParseMode.HTML,
        )
        context.user_data["photo_message_id"] = photo_message.message_id


async def log_application_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Логирует любые ошибки, возникающие при обработке обновлений."""

    if context.error:
        logger.error(
            "Произошла ошибка при обработке обновления %s",
            update,
            exc_info=(type(context.error), context.error, context.error.__traceback__),
        )
    else:
        logger.error("Произошла ошибка без исключения при обработке обновления %s", update)


async def handle_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает нажатия на кнопки главного меню."""

    query = update.callback_query
    if query is None or query.data is None:
        return

    await query.answer()
    _, _, action = query.data.partition(":")

    if action == "main":
        if query.message and query.message.chat:
            await delete_previous_photo(context, query.message.chat.id)
        await send_main_menu(update, context, via_callback=True)
    elif action == "attractions":
        await show_attractions(update, context)
    elif action == "help":
        if query.message and query.message.chat:
            await delete_previous_photo(context, query.message.chat.id)
        help_text = (
            "Используйте кнопки для навигации по боту.\n"
            "В разделе «Достопримечательности» можно открыть карту и построить маршрут.\n"
            "Возвращайтесь в меню, чтобы выбрать новый объект или прочитать подсказки ещё раз."
        )
        await query.edit_message_text(help_text, reply_markup=build_main_menu_keyboard())


def build_application(storage: AttractionStorage) -> Application:
    """Создаёт экземпляр телеграм-приложения и регистрирует обработчики."""

    load_dotenv()
    token = os.getenv("TELEGRAM_TOKEN")
    if not token:
        raise RuntimeError("Не задан токен бота TELEGRAM_TOKEN в переменных окружения")

    application = Application.builder().token(token).build()

    # Сохраняем хранилище в bot_data, чтобы иметь к нему доступ в обработчиках
    application.bot_data["storage"] = storage

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("attractions", show_attractions))
    application.add_handler(CallbackQueryHandler(handle_menu, pattern=r"^menu:"))
    application.add_handler(CallbackQueryHandler(attraction_details, pattern=r"^attraction:"))
    # Добавляем обработчик для логирования всех необработанных ошибок
    application.add_error_handler(log_application_error)

    return application


def main() -> None:
    """Точка входа для запуска бота."""

    base_dir = Path(__file__).resolve().parent
    storage = AttractionStorage.from_json(base_dir / "data" / "attractions.json")
    application = build_application(storage)

    logger.info("Запуск бота...")
    application.run_polling()


if __name__ == "__main__":
    main()
