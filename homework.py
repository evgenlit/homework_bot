import logging
import os
import sys
import time
from http import HTTPStatus

import requests
import telegram
from dotenv import load_dotenv
from requests import RequestException

from exceptions import CustomResponseException

load_dotenv()

logger = logging.getLogger(__name__)
logging.basicConfig(
    stream=sys.stdout,
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s - %(name)s',
)
logger.addHandler(logging.StreamHandler())

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_TIME = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

CHECKED_STATUS = ''
LAST_ERROR_MSG = ''
HOMEWORK_STATUSES = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}


def send_message(bot, message):
    """Отправка сообщений в Telegram чат."""
    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
        logger.info(f"Удачная отправка сообщения в Telegram: {message}")
    except telegram.TelegramError as error:
        logger.error(f"Cбой при отправке сообщения в Telegram: {error}")
        raise telegram.TelegramError(
            f"Cбой при отправке сообщения в Telegram: {message}"
        )


def get_api_answer(current_timestamp):
    """Выполнение запроса к API сервиса Практикум.Домашка."""
    timestamp = current_timestamp or int(time.time())
    params = {'from_date': timestamp}
    try:
        response = requests.get(ENDPOINT, headers=HEADERS, params=params)
        response_status = response.status_code
        response = response.json()
        if int(response_status) != HTTPStatus.OK:
            error = response['error']['error']
            errortext = f'API сервиса Практикум.Домашка вернул ошибку: {error}'
            logger.error(errortext)
            raise Exception(errortext)
        return response
    except RequestException as error:
        errortext = f'API сервиса Практикум.Домашка вернул ошибку: {error}'
        logger.error(errortext)
        raise CustomResponseException(errortext)


def check_response(response):
    """Проверка ответа API на корректность."""
    try:
        homeworks = response['homeworks']
        if not isinstance(homeworks, list):
            logger.error('Неверный тип данных у значения по ключу homeworks.')
            raise TypeError(
                'Неверный тип данных у значения по ключу homeworks.')
        if not homeworks:
            logger.error('Пустой ответ. Нет ни одной домашки.')
            raise TypeError('Пустой ответ. Нет ни одной домашки.')
        return homeworks
    except KeyError:
        logger.error('В ответе отсутствует ключ homeworks.')
        raise KeyError('В ответе отсутствует ключ homeworks.')


def parse_status(homework):
    """Получение статуса домашней работы."""
    global CHECKED_STATUS
    homework_name = homework.get('homework_name')
    homework_status = homework.get('status')
    if homework_status not in HOMEWORK_STATUSES:
        logger.error('Недокументированный статус домашней работы.')
        raise KeyError('Недокументированный статус домашней работы.')
    if homework_status != CHECKED_STATUS:
        verdict = HOMEWORK_STATUSES[homework_status]
        CHECKED_STATUS = homework_status
        return f'Изменился статус проверки работы "{homework_name}". {verdict}'
    else:
        return logger.debug('В ответе от API отсутствует новый статус')


def check_tokens():
    """Проверка обязательных переменных окружения."""
    return all([PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID])


def main():
    """Основная логика работы бота."""
    if not check_tokens():
        logger.critical("Отсутствуют обязательные переменные окружения.")
        raise SystemExit('Программа принудительно остановлена.')
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    current_timestamp = int(time.time())
    while True:
        try:
            response = get_api_answer(current_timestamp)
            homeworks = check_response(response)
            homework = homeworks[0]
            status = parse_status(homework)
            if status:
                send_message(bot, status)
            current_timestamp = response['current_date']
            time.sleep(RETRY_TIME)
        except Exception as error:
            global LAST_ERROR_MSG
            message = f'Сбой в работе программы: {error}'
            if LAST_ERROR_MSG != message:
                LAST_ERROR_MSG = message
                send_message(bot, message)
            time.sleep(RETRY_TIME)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        logger.debug('Прерывание программы пользователем')
        raise SystemExit
