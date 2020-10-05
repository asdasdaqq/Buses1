import requests
from urllib import parse
from json import loads
import time
import sqlite3
from telegram import ext
import redis
import Levenshtein

URL = 'https://api.tgt72.ru/api/v5/'
_BUS_COUNT = 3
_CACHE_LIFETIME = 10800
_LETTER_DIFFERENCE = 0.8


def cache_is_actual(tail: str) -> list:
    """Выдать данные из кэша по заданному хвосту запроса, запросить из API и выдать если данные просрочены
    Args:
        tail (str): Хвост адреса для запроса в API

    Returns:
        list: список данных из кэша/API
    """

    r = redis.Redis()
    answ = r.get(tail)
    if answ:
        return loads(answ.decode("utf-8"))
    else:
        url = parse.urljoin(URL, tail)
        request = requests.get(url).json()
        data = str(request['objects'])
        data = data.replace('"', '')
        data = data.replace("'", "\"")
        data = data.replace(r'\xa0', '')
        r.setex(tail, _CACHE_LIFETIME, data)
        answ = r.get(tail)
        return loads(answ.decode("utf-8"))


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
    cache = cache_is_actual('route/')
    for bus_num in cache:
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
    cache = cache_is_actual('route/')
    for bus_id in cache:
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
    cache = cache_is_actual('checkpoint/')
    for checkpoint in cache:
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
    cache = cache_is_actual('checkpoint/')
    for checkpoint in cache:
        if Levenshtein.jaro(parse.unquote(checkpoint['name']).lower(), name.lower()) >= _LETTER_DIFFERENCE:
            checkpoints.append(checkpoint)
    return checkpoints


def compare_with_current_time(tm: str) -> bool:
    """Сравнение времени с текущим

    Args:
        tm (str): Время в виде строки формата %H:%M

    Returns:
        bool: Сравниваемое время больше или равно текущему
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
    times = times[:_BUS_COUNT]
    return times


def route(update, context):
    """Выдаём все остановки с похожими названиями, если таких нет - говорим об этом

    Args:
        update (telegram.Update): Объект update который обрабатывается данной функцией
        context (CallbackContext): Объект контекста ответа API
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
        update (telegram.Update): Объект update который обрабатывается данной функцией
        context (CallbackContext): Объект контекста ответа API
    """
    def search(x):
        if x[0]['text'][-1].isalpha():
            return int(x[0]['text'][:-1])
        else:
            return int(x[0]['text'])
    answer_id = update.callback_query['id']
    chat_id = update.callback_query['message']['chat']['id']
    context.bot.answerCallbackQuery(answer_id)
    rt_list = []
    chk_id = int(update.callback_query.data)
    for rt_id in get_checkpoint_by_id(chk_id)['routes_ids']:
        rt_list.append([{'text': get_route_name_by_id(rt_id), 'callback_data': f'0,{rt_id},{chk_id}'}])
    rt_list = sorted(rt_list, key=lambda x: search(x))
    keyboard = {'inline_keyboard': rt_list}
    context.bot.send_message(chat_id=chat_id, text='Маршруты на данной остановке:', reply_markup=keyboard)


def final_times(update, context):
    """Возвращаем сообщение о ближайших автобусах, если таковых нет - говорим об этом

    Args:
        update (telegram.Update): Объект update который обрабатывается данной функцией
        context (CallbackContext): Объект контекста ответа API
    """
    answer_id = update.callback_query['id']
    chat_id = update.callback_query['message']['chat']['id']
    context.bot.answerCallbackQuery(answer_id)
    _, rt_id, chk_id = update.callback_query.data.split(',')
    schedule = ', '.join(get_bus_times(rt_id, chk_id))
    if schedule:
        context.bot.send_message(chat_id=chat_id, text=f'Ближайшие автобусы приедут в: {schedule}')
    else:
        context.bot.send_message(chat_id=chat_id, text='В ближайшее время автобусов нет')

    connect = sqlite3.connect('favourites.sqlite')
    cursor = connect.cursor()
    sql = "SELECT * FROM favs where chat_id=? and route_id=? and checkpoint_id=?"
    cursor.execute(sql, (chat_id, rt_id, chk_id))
    answer = cursor.fetchall()
    if not answer:
        btns = [[{'text': 'Yes', 'callback_data': f'1,{rt_id},{chk_id}'}], [{'text': 'No', 'callback_data': f'no'}]]
        keyboard = {'inline_keyboard': btns}
        context.bot.send_message(chat_id=chat_id, text='Добавить маршрут в избранное?', reply_markup=keyboard)
        return 'one'


def add_to_favs(update, context):
    """Добавление пары остановка - маршрут в избранное

    Args:
        update (telegram.Update): Объект update который обрабатывается данной функцией
        context (CallbackContext): Объект контекста ответа API
    """
    answer_id = update.callback_query['id']
    chat_id = update.callback_query['message']['chat']['id']
    pair = update.callback_query.data.split(',')
    context.bot.answerCallbackQuery(answer_id)
    chk_id = int(pair[2])
    rt_id = int(pair[1])
    connect = sqlite3.connect('favourites.sqlite')
    cursor = connect.cursor()
    chk_name = get_checkpoint_by_id(chk_id)['name']
    rt_name = get_route_name_by_id(rt_id)
    sql = "INSERT INTO favs VALUES (?,?,?,?)"
    if context.user_data.get('fav_name'):
        cursor.execute(sql, (context.user_data['fav_name'], chat_id, chk_id, rt_id))
    else:
        cursor.execute(sql, (f'{rt_name}/{chk_name}', chat_id, chk_id, rt_id))
    connect.commit()
    message = update.callback_query['message']['message_id']
    context.bot.editMessageText(chat_id=chat_id, message_id=message, text='Маршрут добавлен')
    context.user_data['fav_name'] = ''

    return ext.ConversationHandler.END


def clear_favs(update, context):
    """Очистка избранного

    Args:
        update (telegram.Update): Объект update который обрабатывается данной функцией
        context (CallbackContext): Объект контекста ответа API
    """
    chat_id = update.message['chat']['id']
    connect = sqlite3.connect('favourites.sqlite')
    cursor = connect.cursor()
    sql = "delete FROM favs where chat_id=?"
    cursor.execute(sql, [chat_id])
    connect.commit()


def check_from_favs(update, context):
    """Запрос избранного

    Args:
        update (telegram.Update): Объект update который обрабатывается данной функцией
        context (CallbackContext): Объект контекста ответа API
    """
    chat_id = update.message['chat']['id']
    connect = sqlite3.connect('favourites.sqlite')
    cursor = connect.cursor()
    sql = "SELECT distinct checkpoint_id, name FROM favs where chat_id=?"
    cursor.execute(sql, [chat_id])
    answer = cursor.fetchall()
    rt_list = []
    for fav in answer:
        rt_list.append([{'text': f'{fav[1]}', 'callback_data': f'2,{fav[1]}'}])
    keyboard = {'inline_keyboard': rt_list}
    if rt_list:
        context.bot.send_message(chat_id=chat_id, text='Ваше избранное:', reply_markup=keyboard)
    else:
        context.bot.send_message(chat_id=chat_id, text='Избранных остановок нет')


def times_from_favs(update, context):
    """Информация по выбранным маршрутам из избранного

        Args:
            update (telegram.Update): Объект update который обрабатывается данной функцией
            context (CallbackContext): Объект контекста ответа API
        """
    answer_id = update.callback_query['id']
    chat_id = update.callback_query['message']['chat']['id']
    context.bot.answerCallbackQuery(answer_id)
    pair = update.callback_query.data.split(',')
    name = pair[1]
    connect = sqlite3.connect('favourites.sqlite')
    cursor = connect.cursor()
    sql = "SELECT route_id, checkpoint_id FROM favs where chat_id=? and name=?"
    cursor.execute(sql, (chat_id, name))
    answer = cursor.fetchall()
    for rt in answer:
        rt_id = int(rt[0])
        chk_id = int(rt[1])
        bus_name = get_route_name_by_id(rt_id)
        schedule = ', '.join(get_bus_times(rt_id, chk_id))
        if schedule:
            context.bot.send_message(chat_id=chat_id, text=f'Автобус №{bus_name} приедет в: {schedule}')
        else:
            context.bot.send_message(chat_id=chat_id, text=f'Сегодня автобус №{bus_name} больше не приедет')


def no(update, context):
    """Функция для специального хэндлера чтобы обработать ответ "Нет" добавления в избранное

    Args:
        update (telegram.Update): Объект update который обрабатывается данной функцией
        context (CallbackContext): Объект контекста ответа API
    """
    answer_id = update.callback_query['id']
    chat_id = update.callback_query['message']['chat']['id']
    context.bot.answerCallbackQuery(answer_id)
    message = update.callback_query['message']['message_id']
    context.bot.deleteMessage(chat_id=chat_id, message_id=message)
    return ext.ConversationHandler.END


def start(update, context):
    """Информационное сообщение при первом взаимодействии с ботом

    Args:
        update (telegram.Update): Объект update который обрабатывается данной функцией
        context (CallbackContext): Объект контекста ответа API
    """
    chat_id = update.message['chat']['id']
    context.bot.send_message(chat_id=chat_id, text='Добро пожаловать в бот-помощник')


def fav_name(update, context):
    """Информационное сообщение при первом взаимодействии с ботом

    Args:
        update (telegram.Update): Объект update который обрабатывается данной функцией
        context (CallbackContext): Объект контекста ответа API
    """
    context.user_data['fav_name'] = update.message['text']
    chat_id = update.message['chat']['id']
    context.bot.send_message(chat_id=chat_id, text='Имя задано')


def main():
    with open('Token', 'r') as token_file:
        token = token_file.read()
    updater = ext.Updater(token, use_context=True)
    dp = updater.dispatcher
    dp.add_handler(ext.CommandHandler('start', start))
    dp.add_handler(ext.CommandHandler('favs', check_from_favs))
    dp.add_handler(ext.CommandHandler('clear', clear_favs))
    dp.add_handler(ext.ConversationHandler(
        entry_points=[ext.CallbackQueryHandler(final_times, pattern=r'[0][,]')],
        states={'one': [ext.MessageHandler(ext.Filters.text, fav_name),
                        ext.CallbackQueryHandler(add_to_favs, pattern=r'[1][,]'),
                        ext.CallbackQueryHandler(no, pattern=r'no')]},
        fallbacks=[]
    ))
    dp.add_handler(ext.MessageHandler(ext.Filters.text, route))
    dp.add_handler(ext.CallbackQueryHandler(times_from_favs, pattern=r'[2][,]'))
    dp.add_handler(ext.CallbackQueryHandler(call, pattern=r'[^0,^a-z]'))

    updater.start_polling()
    updater.idle()


if __name__ == '__main__':
    main()
