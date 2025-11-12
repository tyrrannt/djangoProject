#  Copyright (c) 2025. Lorem ipsum dolor sit amet, consectetur adipiscing elit.
#  Morbi non lorem porttitor neque feugiat blandit. Ut vitae ipsum eget quam lacinia accumsan.
#  Etiam sed turpis ac ipsum condimentum fringilla. Maecenas magna.
#  Proin dapibus sapien vel ante. Aliquam erat volutpat. Pellentesque sagittis ligula eget metus.
#  Vestibulum commodo. Ut rhoncus gravida arcu.
import datetime

from aiogram import Router, types
from aiogram.types import InlineQueryResultArticle, InputTextMessageContent
from asgiref.sync import sync_to_async

from library_app.models import HelpTopic

router = Router()


@router.inline_query()
async def inline_search(query: types.InlineQuery):
    search_text = query.query.strip()

    # если пользователь просто ввёл @bot без текста — ничего не показываем
    if not search_text:
        await query.answer([], cache_time=5)
        return

    # ищем совпадения в модели TelegramNotification
    results = await sync_to_async(list)(
        HelpTopic.objects.filter(title__icontains=search_text)[:20]
    )

    articles = []
    for i, note in enumerate(results):
        message_text = f"<b>{note.title}</b>\n {note.text}"

        articles.append(
            InlineQueryResultArticle(
                id=str(i),
                title=note.text[:60],
                description=f"Дата: {datetime.datetime.today()}",
                input_message_content=InputTextMessageContent(message_text=message_text),
            )
        )

    await query.answer(articles, cache_time=5)
