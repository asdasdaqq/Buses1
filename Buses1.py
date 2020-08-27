import requests
from urllib import parse
import time

from telegram import ext

URL = 'https://api.tgt72.ru/api/v5/'


def get_route_by_name(name:str) -> dict:
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


def get_route_name_by_id(id:int) -> str:
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
            'projected_lat': Прогнозируемую широту (float),
            'name': Название (str),
            'lon' : Долготу (float),
            'heading': Heading (float),
            'projected_lon': Прогнозируемую долготу (float),
            'lat': Широту (float),
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


def time_format(tm: time.struct_time) -> time.struct_time:
    """Форматирование времени для возможности сравнения со временем в формате %H:%M

    Args:
        tm (time.struct_time):

    Returns:
        Время с типом time.struct_time для возможного сравнения со временем в формате %H:%M
    """
    return time.strptime(time.strftime('%H:%M', tm), '%H:%M')


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
    timenow = time_format(time.localtime(time.time()))
    times = [tm for tm in r if time.strptime(tm, '%H:%M') >= timenow]
    times = times[:3]
    return times


def route(update, context):
    """Выдаём все остановки с похожими названиями, если таких нет - говорим об этом

    Args:
        update (Update): Объект update который обрабатывается данной функцией
        context (CallbackContext): Объект контекста ответа API

    Returns:

    """
    chat_id = update.message['chat']['id']
    chk_list = []
    for chk in get_checkpoint_by_name(update.message['text']):
        chk_list.append([{'text': chk['name'] + ' ' + chk['description'], 'callback_data': chk['id']}])
    keyboard = {'inline_keyboard': chk_list}
    if chk_list:
        context.bot.send_message(chat_id=chat_id, text='Остановки похожие на ваш запрос:', reply_markup=keyboard)
    else:
        context.bot.send_message(chat_id=chat_id, text='Похожих остановок не найдено, попробуйте другое название')


def call(update, context):
    """Выдаём сообщение какие маршруты присутствуют на выбранной остановке

    Args:
        update (Update): Объект update который обрабатывается данной функцией
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
        update (Update): Объект update который обрабатывается данной функцией
        context (CallbackContext): Объект контекста ответа API

    Returns:

    """
    answ_id = update.callback_query['id']
    chat_id = update.callback_query['message']['chat']['id']
    context.bot.answerCallbackQuery(answ_id)
    pair = update.callback_query.data.split(',')
    schedule = get_bus_times(pair[1], pair[2])
    if schedule:
        context.bot.send_message(chat_id=chat_id, text=f'Ближайшие автобусы приедут в: {schedule}')
    else:
        context.bot.send_message(chat_id=chat_id, text='В ближайшие полчаса автобусов нет')


def main():
    with open('Token', 'r') as token_file:
        token = token_file.read()
    updater = ext.Updater(token, use_context=True)
    dp = updater.dispatcher
    dp.add_handler(ext.MessageHandler(ext.Filters.text, route))
    dp.add_handler(ext.CallbackQueryHandler(call, pattern=r'[^0]'))
    dp.add_handler(ext.CallbackQueryHandler(final_times, pattern=r'[0]'))
    updater.start_polling()
    updater.idle()


if __name__ == '__main__':
    main()
