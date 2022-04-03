import logging
import os
import sys
import time
from http import HTTPStatus
from json.decoder import JSONDecodeError

import requests
import telegram
from dotenv import load_dotenv
from requests import RequestException

from exceptions import CustomResponseExceptionError

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

HOMEWORK_STATUSES = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}

checked_status = None


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

        try:
            response = response.json()
        except JSONDecodeError:
            logger.error("Ответ не преобразован в JSON")
            raise JSONDecodeError("Ответ не преобразован в JSON")

        if int(response_status) != HTTPStatus.OK:
            error = response['error']['error']
            errortext = f'API сервиса Практикум.Домашка вернул ошибку: {error}'
            logger.error(errortext)
            raise CustomResponseExceptionError(errortext)
        return response
    except RequestException as error:
        errortext = f'API сервиса Практикум.Домашка вернул ошибку: {error}'
        logger.error(errortext)
        raise CustomResponseExceptionError(errortext)


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
    if 'homework_name' not in homework:
        raise KeyError("Отсутствует ключ homework_name в ответе API.")
    if 'status' not in homework:
        raise KeyError("Отсутствует ключ status в ответе API.")
    homework_name = homework.get('homework_name')
    homework_status = homework.get('status')
    if homework_status not in HOMEWORK_STATUSES:
        logger.error('Недокументированный статус домашней работы.')
        raise KeyError('Недокументированный статус домашней работы.')
    verdict = HOMEWORK_STATUSES[homework_status]
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


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
    last_error_msg = ''
    while True:
        try:
            response = get_api_answer(current_timestamp)
            homeworks = check_response(response)
            homework = homeworks[0]
            if homework:
                status = parse_status(homework)
                send_message(bot, status)
            else:
                logger.debug('В ответе от API отсутствует новый статус')

            current_timestamp = response['current_date']
            time.sleep(RETRY_TIME)
        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            print(last_error_msg)
            if last_error_msg != message:
                last_error_msg = message
                send_message(bot, message)
            time.sleep(RETRY_TIME)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        logger.debug('Прерывание программы пользователем')
        raise SystemExit
