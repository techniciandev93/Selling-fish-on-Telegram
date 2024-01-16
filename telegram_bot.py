import argparse
import logging
from functools import partial

import redis
import validators
from environs import Env
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from telegram.ext import Filters, Updater
from telegram.ext import CallbackQueryHandler, CommandHandler, MessageHandler

from strapi import get_strapi_products, get_image_byte, create_user, add_product_to_cart, get_strapi_product, \
    get_user_cart, delete_product

_database = None

logger = logging.getLogger('Logger selling fish telegram bot')


def start(update, context, host, headers):
    return handle_description(update, context, host, headers)


def handle_menu(update, context, host, headers):
    query = update.callback_query

    if query.data.startswith('cart'):
        return handle_cart(update, context, host, headers)

    elif query.data.startswith('back_to_menu'):
        context.bot.delete_message(chat_id=update.effective_chat.id,
                                   message_id=update.callback_query.message.message_id)
        return 'HANDLE_DESCRIPTION'

    elif query.data.startswith('add_to_cart'):
        add_product_to_cart(host, query.message.chat_id, query.data, headers)
        context.bot.delete_message(chat_id=update.effective_chat.id,
                                   message_id=update.callback_query.message.message_id)
        return 'HANDLE_DESCRIPTION'

    product = get_strapi_product(host, headers, query.data)
    image_byte = get_image_byte(host, product)

    caption = f"{product['data']['attributes']['title']} " \
              f"({product['data']['attributes']['price']} руб.)\n\n" \
              f"{product['data']['attributes']['description']}"

    keyboard = [
        [InlineKeyboardButton('Назад', callback_data='back_to_menu')],
        [InlineKeyboardButton('Добавить в корзину', callback_data=f"add_to_cart_{product['data']['id']}")],
        [InlineKeyboardButton('Моя корзина', callback_data='cart')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    context.bot.send_photo(chat_id=update.effective_chat.id,
                           photo=image_byte, caption=caption,
                           reply_markup=reply_markup)
    return 'HANDLE_DESCRIPTION'


def handle_cart(update, context, host, headers):

    chat_id = update.callback_query.message.chat_id
    keyboard = []
    message = 'Корзина:\n\n'
    total_price_all_products = 0
    cart = {}

    user_cart = get_user_cart(host, chat_id, headers)
    if user_cart.get('data'):
        for cart_product in user_cart['data'][0]['attributes']['cart_products']['data']:
            cart_product_id = cart_product['attributes']['product']['data']['id']
            cart_product_price = cart_product['attributes']['product']['data']['attributes']['price']
            cart_product_title = cart_product['attributes']['product']['data']['attributes']['title']

            if cart_product_id in cart:
                cart[cart_product_id]['count'] += 1
                cart[cart_product_id]['total_price'] += cart_product_price
                cart[cart_product_id]['cart_product_ids'].append(cart_product['id'])
            else:
                cart[cart_product_id] = {'count': 1,
                                         'total_price': cart_product_price,
                                         'cart_product_ids': [cart_product['id']],
                                         'cart_id': user_cart['data'][0]['id']}

            if 'title' not in cart[cart_product_id]:
                cart[cart_product_id]['title'] = cart_product_title
            if 'price_per_kg' not in cart[cart_product_id]:
                cart[cart_product_id]['price_per_kg'] = cart_product_price
            total_price_all_products += cart_product_price

    for _, cart_product in cart.items():
        message += (f"{cart_product['title']}\n"
                    f"За килограмм {cart_product['price_per_kg']} руб.\n"
                    f"Добавлено {cart_product['count']} кг. на сумму {cart_product['total_price']} руб.\n\n")

        cart_product_ids = ','.join(map(str, cart_product['cart_product_ids']))
        keyboard.append([InlineKeyboardButton(f"Удалить {cart_product['title']}",
                                              callback_data=f"delete_products_{cart_product_ids}")])

    keyboard.append([InlineKeyboardButton('Назад', callback_data='back_to_menu')])
    keyboard.append([InlineKeyboardButton('Оплатить', callback_data='pay')])
    message += f'Общая сумма - {total_price_all_products} руб.'
    reply_markup = InlineKeyboardMarkup(keyboard)
    context.bot.send_message(chat_id=update.effective_chat.id, text=message, reply_markup=reply_markup)
    return 'HANDLE_DESCRIPTION'


def handle_description(update, context, host, headers):
    if update.callback_query:
        return handle_callback_query(update, context, host, headers)
    else:
        return handle_initial_message(update, context, host, headers)


def handle_callback_query(update, context, host, headers):
    query = update.callback_query
    data = query.data
    state = 'HANDLE_MENU'

    if data.startswith('pay'):
        state = handle_pay(update, context, host, headers)
    elif data.startswith('cart'):
        state = handle_cart(update, context, host, headers)
    elif data.startswith('delete_products'):
        state = handle_delete_product_in_cart(update, context, host, headers)
    elif data.startswith('add_to_cart'):
        add_product_to_cart(host, query.message.chat_id, data, headers)
        state = 'HANDLE_DESCRIPTION'

    if data.startswith('back_to_menu') or data.startswith('add_to_cart') or data.startswith('delete_products'):
        context.bot.delete_message(chat_id=query.message.chat_id, message_id=query.message.message_id)

    return state


def handle_initial_message(update, context, host, headers):
    products = get_strapi_products(host, headers)
    keyboard = []

    for product in products['data']:
        keyboard.append([InlineKeyboardButton(product['attributes']['title'], callback_data=product['id'])])

    keyboard.append([InlineKeyboardButton('Моя корзина', callback_data='cart')])
    reply_markup = InlineKeyboardMarkup(keyboard)
    context.bot.send_message(chat_id=update.effective_chat.id, text='Пожалуйста выберите:', reply_markup=reply_markup)
    return 'HANDLE_MENU'


def handle_pay(update, context, host, headers):
    if not update.message:
        context.bot.send_message(chat_id=update.effective_chat.id, text='Пожалуйста введите ваш email')
        return 'WAITING_EMAIL'
    email = update.message.text
    user_name = update.message.chat.username
    if validators.email(email):
        create_user(host, headers, email, user_name)
        return handle_description(update, context, host, headers)
    else:
        context.bot.send_message(chat_id=update.effective_chat.id, text='Пожалуйста укажите корректный email')
        return 'WAITING_EMAIL'


def handle_delete_product_in_cart(update, context, host, headers):
    cart_products = update.callback_query.data
    split_cart_product_ids = cart_products.split('_')[-1]
    for cart_product_id in split_cart_product_ids.split(','):
        delete_product(host, headers, cart_product_id)
    return 'HANDLE_MENU'


def handle_users_reply(update, context, host, headers):
    """
    Функция, которая запускается при любом сообщении от пользователя и решает как его обработать.
    Эта функция запускается в ответ на эти действия пользователя:
        * Нажатие на inline-кнопку в боте
        * Отправка сообщения боту
        * Отправка команды боту
    Она получает стейт пользователя из базы данных и запускает соответствующую функцию-обработчик (хэндлер).
    Функция-обработчик возвращает следующее состояние, которое записывается в базу данных.
    Если пользователь только начал пользоваться ботом, Telegram форсит его написать "/start",
    поэтому по этой фразе выставляется стартовое состояние.
    Если пользователь захочет начать общение с ботом заново, он также может воспользоваться этой командой.
    """
    db = get_database_connection()

    if update.message:
        user_reply = update.message.text
        chat_id = update.message.chat_id
    elif update.callback_query:
        user_reply = update.callback_query.data
        chat_id = update.callback_query.message.chat_id
    else:
        return

    if user_reply == '/start':
        user_state = 'START'
    else:
        user_state = db.get(chat_id).decode('utf-8')

    states_functions = {
        'START': start,
        'HANDLE_MENU': handle_menu,
        'HANDLE_DESCRIPTION': handle_description,
        'HANDLE_CART': handle_cart,
        'WAITING_EMAIL': handle_pay,
    }

    state_handler = states_functions.get(user_state, start)
    next_state = state_handler(update, context, host, headers)
    db.set(chat_id, next_state)


def get_database_connection():
    """
    Возвращает конекшн с базой данных Redis, либо создаёт новый, если он ещё не создан.
    """
    global _database
    if _database is None:
        database_password = env.str('REDIS_PASSWORD')
        database_host = env.str('REDIS_URL')
        database_port = env.int('REDIS_PORT')
        _database = redis.Redis(host=database_host, port=database_port, password=database_password)
    return _database


if __name__ == '__main__':
    try:
        env = Env()
        env.read_env()

        token = env.str('TELEGRAM_BOT_TOKEN')
        strapi_token = env.str('STRAPI_TOKEN')

        parser = argparse.ArgumentParser(description='Этот скрипт запускает телеграм бота по продаже рыбы, по умолчанию'
                                                     'без аргумента будет использоваться хост http://127.0.0.1:1337')
        parser.add_argument('--host', type=str, help='Укажите хост strapi в виде '
                                                     'схема(http или https)://ip адрес или домен:порт',
                            nargs='?', default='http://127.0.0.1:1337')
        args = parser.parse_args()
        strapi_headers = {'Authorization': f'bearer {strapi_token}'}

        handle_handle_users_reply_with_args = partial(handle_users_reply, host=args.host, headers=strapi_headers)

        logging.basicConfig(
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
        )
        logger.setLevel(logging.INFO)
        logger.info('Телеграм бот запущен')

        updater = Updater(token)
        dispatcher = updater.dispatcher
        dispatcher.add_handler(CallbackQueryHandler(handle_handle_users_reply_with_args))
        dispatcher.add_handler(MessageHandler(Filters.text, handle_handle_users_reply_with_args))
        dispatcher.add_handler(CommandHandler('start', handle_handle_users_reply_with_args))
        updater.start_polling()
        updater.idle()
    except Exception as error:
        logger.exception(error)
