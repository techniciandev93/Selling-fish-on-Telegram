from io import BytesIO

import requests


def get_strapi_products(host, headers):
    products_url = f'{host}/api/products'
    params = {'populate': 'picture'}
    response = requests.get(products_url, headers=headers, params=params)
    response.raise_for_status()
    return response.json()


def get_strapi_product(host, headers, product_id):
    product_url = f'{host}/api/products/{product_id}'
    params = {'populate': 'picture'}
    response = requests.get(product_url, headers=headers, params=params)
    response.raise_for_status()
    return response.json()


def get_image_byte(host, product):
    img_url = f"{host}{product['data']['attributes']['picture']['data'][0]['attributes']['url']}"
    response = requests.get(img_url)
    response.raise_for_status()
    image_byte = BytesIO(response.content)
    return image_byte


def get_or_create_user_cart(host, telegram_id, headers):
    strapi_cart_url = f'{host}/api/carts/'
    cart = {
        'data': {
            'telegram_id': telegram_id
        }
    }
    params = {'filters[telegram_id][$eq]': telegram_id}

    response = requests.get(strapi_cart_url, headers=headers, params=params)
    response.raise_for_status()
    cart_response = response.json()
    if cart_response['data']:
        return cart_response['data'][0]['id']
    else:
        response = requests.post(strapi_cart_url, json=cart, headers=headers)
        response.raise_for_status()
        cart_response = response.json()
        return cart_response['data']['id']


def add_product_to_cart(host, telegram_id, user_reply, headers):
    create_cart_product_url = f'{host}/api/cart-products'
    product_id = user_reply.split('_')[-1]
    cart_id = get_or_create_user_cart(host, telegram_id, headers)
    cart = {
        'data': {
            'cart': cart_id,
            'product': product_id
        }
    }
    response = requests.post(create_cart_product_url, json=cart, headers=headers)
    response.raise_for_status()


def create_user(host, headers, email, user_name):
    client_strapi_url = f'{host}/api/clients/'
    client_fields = {
        "data": {
            "username": user_name,
            "email": email
        }
    }
    response = requests.post(client_strapi_url, headers=headers, json=client_fields)
    return response.ok


def get_user_cart(host, chat_id, headers):
    cart_url = f'{host}/api/carts'
    cart_params = {'filters[telegram_id][$eq]': chat_id, 'populate[0]': 'cart_products.product'}
    cart_response = requests.get(cart_url, headers=headers, params=cart_params)
    cart_response.raise_for_status()
    user_cart = cart_response.json()
    return user_cart


def delete_product(host, headers, cart_product_id):
    delete_product_url = f'{host}/api/cart-products/{cart_product_id}'
    response = requests.delete(delete_product_url, headers=headers)
    response.raise_for_status()
