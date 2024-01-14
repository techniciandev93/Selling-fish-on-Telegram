# Бот по продаже рыбы

Телеграм бот по продаже рыбы с cms Strapi

## Как установить

Python 3.10 должен быть уже установлен.
Затем используйте `pip` (или `pip3`, есть конфликт с Python2) для установки зависимостей:
```
pip install -r requirements.txt
```

Создайте файл `.env` в корневой директории проекта и добавьте переменные окружения:

```
STRAPI_TOKEN= токен strapi
TELEGRAM_BOT_TOKEN= токен телеграмм бота
REDIS_URL= url к бд redis
REDIS_PORT= порт бд redis
REDIS_PASSWORD= пароль бд redis
```
## Как запустить
### Для запуска Strapi
Strapi предоставляет множество возможных вариантов развертывания проекта, включая [Strapi Cloud](https://cloud.strapi.io/). 
Просмотрите [раздел документации по развертыванию](https://docs.strapi.io/dev-docs/deployment), чтобы найти лучшее решение для вашего случая использования.

### `develop`

Запустите приложение Strapi с включенной автоперезагрузкой. [Узнать подробнее](https://docs.strapi.io/dev-docs/cli#strapi-develop)

```
npm run develop
# or
yarn develop
```

### `start`

Запустите приложение Strapi с отключенной автоперезагрузкой. [Узнать подробнее](https://docs.strapi.io/dev-docs/cli#strapi-start)

```
npm run start
# or
yarn start
```

### `build`

Создайте свою админ-панель. [Узнать подробнее Узнать](https://docs.strapi.io/dev-docs/cli#strapi-build)

```
npm run build
# or
yarn build
```
### Для запуска телеграм бота
```
python telegram_bot.py
```

По умолчанию без аргумента будет использоваться хост http://127.0.0.1:1337

### Для запуска со своим хостом
Укажите хост strapi в виде - схема(http или https)://ip адрес или домен:порт
```
python telegram_bot.py --host http://127.0.0.1:1337
```

## Примечания

- Для работы скрипта необходимо иметь API-токен Telegram. Вы можете получить его, создав бота через [BotFather](https://core.telegram.org/bots#botfather).

В cms strapi необходимо:
- Создать товары
- Создать каталог
- Создать иерархию
- Создать прайсбук
- В прайсбук добавить товары
- В иерархии подцепить товары к категориям
- В каталоге указать иерархию с товарами
- В меню каталога, напротив каталога необходимо - опубликовать каталог