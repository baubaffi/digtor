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


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает команду /start и приветствует пользователя."""

    user_name = update.effective_user.first_name if update.effective_user else ""
    text = (
        "Здравствуйте, {name}! Добро пожаловать в проект «Цифровой Торжокъ».\n"
        "Я помогу вам узнать о достопримечательностях города и проложить маршрут.\n"
        "Используйте команду /attractions, чтобы открыть список объектов."
    ).format(name=user_name)
    await update.message.reply_text(text)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает команду /help и выводит подсказку."""

    help_text = (
        "Доступные команды:\n"
        "/start — приветствие и краткая информация о боте;\n"
        "/attractions — список достопримечательностей;\n"
        "Нажмите на интересующий объект, чтобы получить подробности и ссылки на карту."
    )
    await update.message.reply_text(help_text)


async def show_attractions(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Отправляет пользователю список доступных достопримечательностей."""

    storage: AttractionStorage = context.application.bot_data["storage"]
    attractions = storage.all()

    if not attractions:
        await update.message.reply_text(
            "Извините, список достопримечательностей пока пуст. Попробуйте позже."
        )
        return

    # Формируем кнопки с названием каждой достопримечательности
    keyboard = [
        [InlineKeyboardButton(text=item.name, callback_data=f"attraction:{item.identifier}")]
        for item in attractions
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "Выберите достопримечательность, чтобы узнать подробности:",
        reply_markup=reply_markup,
    )


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
        f"<a href='{attraction.map_link}'>Точка на карте</a>",
        f"<a href='{attraction.route_link}'>Построить маршрут</a>",
    ]

    await query.edit_message_text(
        "\n".join(message_lines),
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )


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
    application.add_handler(CallbackQueryHandler(attraction_details, pattern=r"^attraction:"))

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
