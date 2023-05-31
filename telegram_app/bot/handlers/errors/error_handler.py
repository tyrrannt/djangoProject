import logging
from aiogram.utils.exceptions import (Unauthorized, InvalidQueryID, TelegramAPIError,
                                      CantDemoteChatCreator, MessageNotModified, MessageToDeleteNotFound,
                                      MessageTextIsEmpty, RetryAfter,
                                      CantParseEntities, MessageCantBeDeleted)
from loguru import logger

from telegram_app.bot.loader import dp

logger.add("debug.json", format="{time} {level} {message}", level="DEBUG", rotation="10 MB", compression="zip",
           serialize=True)

@dp.errors_handler()
async def errors_handler(update, exception):
    """
    Exceptions handler. Catches all exceptions within task factory tasks.
    :param dispatcher:
    :param update:
    :param exception:
    :return: stdout logging
    """

    if isinstance(exception, CantDemoteChatCreator):
        logging.exception("Can't demote chat creator")
        logger.error(f'Cant remote chat creator')
        return True

    if isinstance(exception, MessageNotModified):
        logging.exception('Message is not modified')
        logger.error(f'Message is not modified')
        return True
    if isinstance(exception, MessageCantBeDeleted):
        logging.exception('Message cant be deleted')
        logger.error(f'Message cant be deleted')
        return True

    if isinstance(exception, MessageToDeleteNotFound):
        logging.exception('Message to delete not found')
        logger.error(f'Message to delete not found')
        return True

    if isinstance(exception, MessageTextIsEmpty):
        logging.exception('MessageTextIsEmpty')
        logger.error(f'MessageTextIsEmpty')
        return True

    if isinstance(exception, Unauthorized):
        logging.exception(f'Unauthorized: {exception}')
        logger.error(f'Unauthorized: {exception}')
        return True

    if isinstance(exception, InvalidQueryID):
        logging.exception(f'InvalidQueryID: {exception} \nUpdate: {update}')
        logger.error(f'InvalidQueryID: {exception} \nUpdate: {update}')
        return True

    if isinstance(exception, TelegramAPIError):
        logging.exception(f'TelegramAPIError: {exception} \nUpdate: {update}')
        logger.error(f'TelegramAPIError: {exception} \nUpdate: {update}')
        return True
    if isinstance(exception, RetryAfter):
        logging.exception(f'RetryAfter: {exception} \nUpdate: {update}')
        logger.error(f'RetryAfter: {exception} \nUpdate: {update}')
        return True
    if isinstance(exception, CantParseEntities):
        logging.exception(f'CantParseEntities: {exception} \nUpdate: {update}')
        logger.error(f'CantParseEntities: {exception} \nUpdate: {update}')
        return True

    logging.exception(f'Update: {update} \n{exception}')