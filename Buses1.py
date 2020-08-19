import requests
import urllib.parse
from telegram import ext


def get_route_by_name(name:str) -> dict:
    """Получить объекта маршрута по его имени(номеру)

    Args:
        name: Номер маршрута (принимаем как строку потому что в API хранится как строка)

    Returns:
        Словарь конкретного маршрута, содержит:
        id остановок маршрута, название маршрута (имеет вид 'Начальная остановка' - 'Конечная остановка'),
        id самого маршрута,
        его номер

    """
    url = 'https://api.tgt72.ru/api/v5/route/'
    r = requests.get(url).json()
    for bus_num in r['objects']:
        if bus_num['name'] == name:
            return bus_num
    pass


def get_route_name_by_id(id:int) -> str:
    """Получить номер маршрута по его id
    Args:
        id: id маршрута из API

    Returns:
        Номер маршрута в виде строки

    """
    url = 'https://api.tgt72.ru/api/v5/route/'
    r = requests.get(url).json()
    for bus_id in r['objects']:
        if bus_id['id'] == id:
            return bus_id['name']
    pass


def get_checkpoint_by_id(id: int) -> dict:
    """Получить название остановки по её id

    Args:
        id: id остановки из API

    Returns:
        Название остановки из API

    """
    url = 'https://api.tgt72.ru/api/v5/checkpoint/'
    r = requests.get(url).json()
    for checkpoint in r['objects']:
        if checkpoint['id'] == id:
            return checkpoint
    pass


def get_checkpoint_by_name(name:str) -> list:
    """Поиск среди всех остановок по совпадению в названии

    Args:
        name:Строка поиска имени

    Returns:
        Список остановок с подходящим названием

    """
    checkpoints = []
    url = 'https://api.tgt72.ru/api/v5/checkpoint/'
    r = requests.get(url).json()
    for checkpoint in r['objects']:
        if urllib.parse.unquote(checkpoint['name']).lower().find(name.lower()) != -1:
            checkpoints.append(checkpoint)
    return checkpoints


def get_bus_times(route_id: int, checkpoint_id: int) -> list:
    """

    Args:
        route_id: id маршрута из API
        checkpoint_id: id остановки из API

    Returns:
        Список времён когда на выбранной остановке будет проезжать выбранный маршрут

    """
    url = 'https://api.tgt72.ru/api/v5/times/?route_id='+str(route_id)+'&checkpoint_id='+str(checkpoint_id)
    r = requests.get(url).json()
    return r['objects'][0]['times']


def route(update, context):

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

    answ_id = update.callback_query['id']
    chat_id = update.callback_query['message']['chat']['id']
    context.bot.answerCallbackQuery(answ_id)
    rt_list = []
    chk_id = int(update.callback_query.data)
    for rt_id in get_checkpoint_by_id(chk_id)['routes_ids']:
        rt_list.append([{'text': get_route_name_by_id(rt_id), 'callback_data': '0,' + str(rt_id) + ',' + str(chk_id)}])
    keyboard = {'inline_keyboard': rt_list}
    context.bot.send_message(chat_id=chat_id, text='Маршруты на данной остановке:', reply_markup=keyboard)


def final_times(update, context):

    answ_id = update.callback_query['id']
    chat_id = update.callback_query['message']['chat']['id']
    context.bot.answerCallbackQuery(answ_id)
    pair = update.callback_query.data.split(',')
    context.bot.send_message(chat_id=chat_id, text=str(get_bus_times(pair[1], pair[2])))


def main():
    updater = ext.Updater('1267970793:AAFIiTln0imXgRAQQOk3rX-byuEmZXf7A_s', use_context=True)
    dp = updater.dispatcher
    dp.add_handler(ext.MessageHandler(ext.Filters.text, route))
    dp.add_handler(ext.CallbackQueryHandler(call, pattern=r'[^0]'))
    dp.add_handler(ext.CallbackQueryHandler(final_times, pattern=r'[0]'))
    updater.start_polling()
    updater.idle()


if __name__ == '__main__':
    main()
