import requests
from urllib import parse
import time
import sqlite3

from telegram import ext

URL = 'https://api.tgt72.ru/api/v5/'
BusCount = 3


def get_route_by_name(name: str) -> dict:
    """Получить объекта маршрута по его имени(номеру)

    Args:
        name (str): Номер маршрута (принимаем как строку потому что в API хранится как строка)

    Returns:
        dict:
            {'checkpoints_ids': Список с id остановок маршрута (list[int]),
            'description': Название маршрута (имеет вид 'Начальная остановка' - 'Конечная остановка') (str),
            'id': id маршрута (int),
            'name': Номер маршрута (str)}

    """
    url = parse.urljoin(URL, 'route/')
    r = requests.get(url).json()
    for bus_num in r['objects']:
        if bus_num['name'] == name:
            return bus_num
    return


def get_route_name_by_id(id: int) -> str:
    """Получить номер маршрута по его id
    Args:
        id (int): id маршрута из API

    Returns:
        Номер маршрута (str)

    """
    url = parse.urljoin(URL, 'route/')
    r = requests.get(url).json()
    for bus_id in r['objects']:
        if bus_id['id'] == id:
            return bus_id['name']
    return


def get_checkpoint_by_id(id: int) -> dict:
    """Получить объект остановки по её id

    Args:
        id (int): id остановки из API

    Returns:
        dict:
            {'code_number': Её кодовый номер (str),
            'name': Название (str),
            'lon' : Долготу (float),
            'lat': Широту (float),
            'projected_lon': Прогнозируемую долготу (float),
            'projected_lat': Прогнозируемую широту (float),
            'heading': Heading (float),
            'routes_ids': Список id маршрутов этой остановки (list[int]),
            'id': id остановки (int),
            'description': Описание остановки (str)}
    """
    url = parse.urljoin(URL, 'checkpoint/')
    r = requests.get(url).json()
    for checkpoint in r['objects']:
        if checkpoint['id'] == id:
            return checkpoint
    return


def get_checkpoint_by_name(name: str) -> list:
    """Поиск среди всех остановок по совпадению в названии

    Args:
        name (str):Строка поиска имени

    Returns:
        Список остановок с подходящим названием (list[dict])

    """
    checkpoints = []
    url = parse.urljoin(URL, 'checkpoint/')
    r = requests.get(url).json()
    for checkpoint in r['objects']:
        if parse.unquote(checkpoint['name']).lower().find(name.lower()) != -1:
            checkpoints.append(checkpoint)
    return checkpoints


def compare_with_current_time(tm: str) -> bool:
    """Сравнение времени с текущим

    Args:
        tm (str): Время в виде строки формата %H:%M

    Returns:
        bool: Если сравниваемое время больше или равно текущему - True
    """
    current_time = time.localtime().tm_hour * 60 + time.localtime().tm_min
    compare_time = time.strptime(tm, '%H:%M').tm_hour * 60 + time.strptime(tm, '%H:%M').tm_min
    return compare_time >= current_time


def get_bus_times(route_id: int, checkpoint_id: int) -> list:
    """Поиск ближайших трёх автобусов которые должны приехать на данную остановку

    Args:
        route_id (int): id маршрута из API
        checkpoint_id (int): id остановки из API

    Returns:
        Список времён ближайших трёх автобусов выбранного маршрута на данной остановке (list)

    """
    query = f'times/?route_id={route_id}&checkpoint_id={checkpoint_id}'
    url = parse.urljoin(URL, query)
    r = requests.get(url).json()
    r = r['objects'][0]['times']

    times = [tm for tm in r if compare_with_current_time(tm)]
    times = times[:BusCount]
    return times


def route(update, context):
    """Выдаём все остановки с похожими названиями, если таких нет - говорим об этом

    Args:
        update (:class:`telegram.Update`): Объект update который обрабатывается данной функцией
        context (CallbackContext): Объект контекста ответа API

    Returns:

    """
    chat_id = update.message['chat']['id']
    chk_list = []
    for chk in get_checkpoint_by_name(update.message['text'].strip()):
        chk_list.append([{'text': chk['name'] + ' ' + chk['description'], 'callback_data': f"{chk['id']}"}])
    keyboard = {'inline_keyboard': chk_list}
    if chk_list:
        context.bot.send_message(chat_id=chat_id, text='Остановки похожие на ваш запрос:', reply_markup=keyboard)
    else:
        context.bot.send_message(chat_id=chat_id, text='Похожих остановок не найдено, попробуйте другое название')


def call(update, context):
    """Выдаём сообщение какие маршруты присутствуют на выбранной остановке

    Args:
        update (:class:`telegram.Update`): Объект update который обрабатывается данной функцией
        context (CallbackContext): Объект контекста ответа API

    Returns:

    """
    answ_id = update.callback_query['id']
    chat_id = update.callback_query['message']['chat']['id']
    context.bot.answerCallbackQuery(answ_id)
    rt_list = []
    chk_id = int(update.callback_query.data)
    for rt_id in get_checkpoint_by_id(chk_id)['routes_ids']:
        rt_list.append([{'text': get_route_name_by_id(rt_id), 'callback_data': f'0,{rt_id},{chk_id}'}])
    keyboard = {'inline_keyboard': rt_list}
    context.bot.send_message(chat_id=chat_id, text='Маршруты на данной остановке:', reply_markup=keyboard)


def final_times(update, context):
    """Возвращаем сообщение об автобусах в ближайшие полчаса, если таковых нет - говорим об этом

    Args:
        update (:class:`telegram.Update`): Объект update который обрабатывается данной функцией
        context (CallbackContext): Объект контекста ответа API

    Returns:

    """
    answ_id = update.callback_query['id']
    chat_id = update.callback_query['message']['chat']['id']
    context.bot.answerCallbackQuery(answ_id)
    pair = update.callback_query.data.split(',')
    chk_id = pair[2]
    rt_id = pair[1]
    comm = ', '
    schedule = comm.join(get_bus_times(rt_id, chk_id))
    if schedule:
        context.bot.send_message(chat_id=chat_id, text=f'Ближайшие автобусы приедут в: {schedule}')
    else:
        context.bot.send_message(chat_id=chat_id, text='В ближайшее время автобусов нет')

    conn = sqlite3.connect('favourites.sqlite')
    cursor = conn.cursor()
    sql = f"SELECT * FROM favs where chat_id={chat_id} and route_id={rt_id} and checkpoint_id={chk_id}"
    cursor.execute(sql)
    answ = cursor.fetchall()
    if not answ:
        btns = [[{'text': 'Yes', 'callback_data': f'1,{rt_id},{chk_id}'}], [{'text': 'No', 'callback_data': f'no'}]]
        keyboard = {'inline_keyboard': btns}
        context.bot.send_message(chat_id=chat_id, text='Добавить маршрут в избранное?', reply_markup=keyboard)


def add_to_favs(update, context):
    """Добавление пары остановка - маршрут в избранное

    Args:
        update (:class:`telegram.Update`): Объект update который обрабатывается данной функцией
        context (CallbackContext): Объект контекста ответа API

    Returns:

    """
    answ_id = update.callback_query['id']
    chat_id = update.callback_query['message']['chat']['id']
    pair = update.callback_query.data.split(',')
    context.bot.answerCallbackQuery(answ_id)
    chk_id = int(pair[2])
    rt_id = int(pair[1])
    conn = sqlite3.connect('favourites.sqlite')
    cursor = conn.cursor()
    chk_name = get_checkpoint_by_id(chk_id)
    fav_name = get_route_name_by_id(rt_id)
    sql = f"INSERT INTO favs VALUES ('{fav_name}/{chk_name['name']}',{chat_id},{chk_id},{rt_id})"
    cursor.execute(sql)
    conn.commit()
    message = update.callback_query['message']['message_id']
    context.bot.editMessageText(chat_id=chat_id, message_id=message, text='Маршрут добавлен')


def clear_favs(update, context):
    """Очистка избранного

    Args:
        update (:class:`telegram.Update`): Объект update который обрабатывается данной функцией
        context (CallbackContext): Объект контекста ответа API

    Returns:

    """
    chat_id = update.message['chat']['id']
    conn = sqlite3.connect('favourites.sqlite')
    cursor = conn.cursor()
    sql = f"delete FROM favs where chat_id={chat_id}"
    cursor.execute(sql)
    conn.commit()


def check_from_favs(update, context):
    """Запрос избранного и выдача информации по выбранному маршруту оттуда

    Args:
        update (:class:`telegram.Update`): Объект update который обрабатывается данной функцией
        context (CallbackContext): Объект контекста ответа API

    Returns:

    """
    chat_id = update.message['chat']['id']
    conn = sqlite3.connect('favourites.sqlite')
    cursor = conn.cursor()
    sql = f"SELECT * FROM favs where chat_id={chat_id}"
    cursor.execute(sql)
    answ = cursor.fetchall()
    rt_list = []
    for fav in answ:
        bus_name = fav[0]
        chk_id = fav[2]
        rt_id = fav[3]
        rt_list.append([{'text': f'{bus_name}', 'callback_data': f'0,{rt_id},{chk_id}'}])
    keyboard = {'inline_keyboard': rt_list}
    context.bot.send_message(chat_id=chat_id, text='Ваше избранное:', reply_markup=keyboard)


def no(update, context):
    """Функция для специального хэндлера чтобы обработать ответ "Нет" добавления в избранное

    Args:
        update (:class:`telegram.Update`): Объект update который обрабатывается данной функцией
        context (CallbackContext): Объект контекста ответа API

    Returns:

    """
    answ_id = update.callback_query['id']
    chat_id = update.callback_query['message']['chat']['id']
    context.bot.answerCallbackQuery(answ_id)
    message = update.callback_query['message']['message_id']
    context.bot.deleteMessage(chat_id=chat_id, message_id=message)


def start(update, context):
    """Информационное сообщение при первом взаимодействии с ботом

    Args:
        update (:class:`telegram.Update`): Объект update который обрабатывается данной функцией
        context (CallbackContext): Объект контекста ответа API

    Returns:

    """
    chat_id = update.message['chat']['id']
    context.bot.send_message(chat_id=chat_id, text='Добро пожаловать в бот-помощник')

def main():
    with open('Token', 'r') as token_file:
        token = token_file.read()
    updater = ext.Updater(token, use_context=True)
    dp = updater.dispatcher
    dp.add_handler(ext.CommandHandler('start', start))
    dp.add_handler(ext.CommandHandler('favs', check_from_favs))
    dp.add_handler(ext.CommandHandler('clear', clear_favs))
    dp.add_handler(ext.MessageHandler(ext.Filters.text, route))
    dp.add_handler(ext.CallbackQueryHandler(final_times, pattern=r'[0][,]'))
    dp.add_handler(ext.CallbackQueryHandler(add_to_favs, pattern=r'[1][,]'))
    dp.add_handler(ext.CallbackQueryHandler(call, pattern=r'[^0,^a-z]'))
    dp.add_handler(ext.CallbackQueryHandler(no, pattern=r'no'))

    updater.start_polling()
    updater.idle()


if __name__ == '__main__':
    main()
