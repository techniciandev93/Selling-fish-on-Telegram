import argparse
import logging
from functools import partial

import redis
import requests
import validators
from environs import Env
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from telegram.ext import Filters, Updater
from telegram.ext import CallbackQueryHandler, CommandHandler, MessageHandler

from strapi import get_strapi_products, get_image_byte, create_user, add_product_to_cart

_database = None

logger = logging.getLogger('Logger selling fish telegram bot')


def start(update, context, host, headers):
    return handle_description(update, context, host, headers)


def handle_menu(update, context, host, headers):
    products_url = f'{host}/api/products'
    query = update.callback_query
    product = get_strapi_products(products_url, headers, query.data)
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
    cart_url = f'{host}/api/carts?filters[telegram_id][$eq]={chat_id}&populate[0]=cart_products.product'

    cart_response = requests.get(cart_url, headers=headers)
    cart_response.raise_for_status()
    cart_user = cart_response.json()
    if cart_user.get('data'):
        for cart_product in cart_user['data'][0]['attributes']['cart_products']['data']:
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
                                         'cart_id': cart_user['data'][0]['id']}

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
    products_url = f'{host}/api/products'
    if update.callback_query:
        if update.callback_query.data != 'cart':
            context.bot.delete_message(chat_id=update.effective_chat.id,
                                       message_id=update.callback_query.message.message_id)
    else:
        products = get_strapi_products(products_url, headers)
        keyboard = []
        for product in products['data']:
            keyboard.append([InlineKeyboardButton(product['attributes']['title'], callback_data=product['id'])])

        keyboard.append([InlineKeyboardButton('Моя корзина', callback_data='cart')])
        reply_markup = InlineKeyboardMarkup(keyboard)
        context.bot.send_message(chat_id=update.effective_chat.id, text='Пожалуйста выберите:',
                                 reply_markup=reply_markup)
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
        delete_products_url = f'{host}/api/cart-products/{cart_product_id}'
        response = requests.delete(delete_products_url, headers=headers)
        response.raise_for_status()
    return 'HANDLE_DESCRIPTION'


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
    elif user_reply.startswith('add_to_cart'):
        add_product_to_cart(host, chat_id, user_reply, headers)
        user_state = 'HANDLE_DESCRIPTION'
    elif user_reply.startswith('cart'):
        user_state = 'HANDLE_CART'
    elif user_reply.startswith('delete_products'):
        handle_delete_product_in_cart(update, context, host, headers)
        user_state = 'HANDLE_DESCRIPTION'
    elif user_reply.startswith('back_to_menu'):
        user_state = 'HANDLE_DESCRIPTION'
    elif user_reply.startswith('pay'):
        user_state = 'WAITING_EMAIL'
    else:
        user_state = db.get(chat_id).decode('utf-8')

    states_functions = {
        'START': start,
        'HANDLE_MENU': handle_menu,
        'HANDLE_DESCRIPTION': handle_description,
        'HANDLE_CART': handle_cart,
        'WAITING_EMAIL': handle_pay
    }
    state_handler = states_functions[user_state]
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
