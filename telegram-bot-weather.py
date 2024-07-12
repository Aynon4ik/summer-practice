import os
import json
import requests
import io

# Network methods
def post_message(msg_json):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if token:
        url = f'https://api.telegram.org/bot{token}/sendMessage'
        requests.post(url=url, json=msg_json)

def reply_to_message(text, msg):
    chat_id = msg['chat']['id']
    msg_id = msg['message_id']
    reply_msg = {
        'chat_id': chat_id,
        'text': text,
        'reply_parameters': {"message_id": msg_id}
    }
    post_message(reply_msg)

def send_message(text, msg):
    post_message({'chat_id': msg['chat']['id'], 'text': text})

def post_voice(data, voice_file):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if token:
        url = f"https://api.telegram.org/bot{token}/sendVoice"
        requests.post(url, data=data, files=voice_file)

def send_voice(voice, msg):
    post_voice(data={"chat_id": msg['chat']['id']}, voice_file={"voice": io.BytesIO(voice)})

# Command methods
def send_help_message(msg):
    help_texts = [
        "Я расскажу о текущей погоде для населенного пункта.",
        """
        Я могу ответить на:
        - Текстовое сообщение с названием населенного пункта.
        - Голосовое сообщение с названием населенного пункта.
        - Сообщение с геопозицией.
        """
    ]
    for text in help_texts:
        send_message(text, msg)

def handle_command(msg):
    cmd = msg['text']
    if cmd in ['/start', '/help']:
        send_help_message(msg)
    else:
        send_message("Неизвестная команда!", msg)

# Weather methods
def get_wind_direction(deg):
    directions = [
        "Северный", "Северо-северо-восточный", "Северо-восточный", "Востоко-северо-восточный",
        "Восточный", "Востоко-юго-восточный", "Юго-восточный", "Юго-юго-восточный",
        "Южный", "Юго-юго-западный", "Юго-западный", "Западо-юго-западный",
        "Западный", "Западо-северо-западный", "Северо-западный", "Северо-северо-западный"
    ]
    idx = int((deg + 11.25) // 22.5) % 16
    return directions[idx]

def format_weather(info):
    city = info['name']
    desc = info['weather'][0]['description']
    temp = info['main']['temp']
    feels_like = info['main']['feels_like']
    temp_min = info['main']['temp_min']
    temp_max = info['main']['temp_max']
    pressure = info['main']['pressure'] * 0.750064  # ГПа в мм.рт.ст
    wind_speed = info['wind']['speed']
    wind_deg = info['wind']['deg']
    wind_dir = get_wind_direction(wind_deg)

    return f"""
    Погода в городе {city}:
    Сейчас {desc}, температура {temp}°C, ощущается как {feels_like}°C.
    Температура: макс {temp_max}°C, мин {temp_min}°C.
    Давление: {int(pressure)} мм.рт.ст.
    Ветер: {wind_dir.lower()} ({wind_deg}°) со скоростью {wind_speed} м/с.
    """

def get_weather(place):
    token = os.getenv("OPEN_WEATHER_TOKEN")
    url = "https://api.openweathermap.org/data/2.5/weather"
    params = {"q": place, "appid": token, "lang": "ru", "units": "metric"}
    response = requests.get(url, params=params).json()

    if response['cod'] == '404':
        raise ValueError(f"Я не нашел населенный пункт {place}")
    elif response['cod'] == '200':
        return format_weather(response)
    else:
        raise RuntimeError("Произошла непредвиденная ошибка! Попробуйте позже")

# Voice message utilities
def download_file(file_id, token):
    url = f"https://api.telegram.org/bot{token}/getFile"
    response = requests.post(url, json={"file_id": file_id}).json()
    file_path = response["result"]["file_path"]
    download_url = f"https://api.telegram.org/file/bot{token}/{file_path}"
    return requests.get(download_url).content

def stt(voice, token):
    url = "https://stt.api.cloud.yandex.net/speech/v1/stt:recognize"
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.post(url, headers=headers, data=voice).json()
    return response["result"]

def tts(text, token):
    url = "https://tts.api.cloud.yandex.net/speech/v1/tts:synthesize"
    params = {"text": text, "voice": "ermil", "emotion": "good"}
    headers = {"Authorization": f"Bearer {token}"}
    return requests.post(url, data=params, headers=headers).content

def format_weather_for_voice(weather):
    replacements = {
        "°C": "градусов по Цельсию",
        "мм.рт.ст": "миллиметров ртутного столба",
        "м/с": "метров в секунду"
    }
    for old, new in replacements.items():
        weather = weather.replace(old, new)
    return weather

# Message handlers
def handle_text_message(msg):
    if msg['text'].startswith('/'):
        handle_command(msg)
    else:
        city = msg['text']
        try:
            weather = get_weather(city)
            send_message(weather, msg)
        except (ValueError, RuntimeError) as e:
            send_message(e.args[0], msg)

def handle_voice_message(msg, token):
    voice = msg['voice']
    if voice['duration'] > 30:
        send_message("Голосовое сообщение должно быть короче 30 секунд", msg)
        return

    tg_token = os.getenv("TELEGRAM_BOT_TOKEN")
    voice_data = download_file(file_id=voice["file_id"], token=tg_token)
    city = stt(voice=voice_data, token=token)
    
    try:
        weather = get_weather(city)
        voice_msg = tts(format_weather_for_voice(weather), token)
        send_voice(voice_msg, msg)
    except (ValueError, RuntimeError) as e:
        send_message(e.args[0], msg)

def handler(event, context):
    response = {'statusCode': 200, 'body': ''}
    update = json.loads(event['body'])

    if 'message' in update:
        msg = update['message']
        if 'text' in msg:
            handle_text_message(msg)
        elif 'voice' in msg:
            yc_token = context.token["access_token"]
            handle_voice_message(msg, yc_token)
        else:
            send_message("Могу ответить только на текстовое или голосовое сообщение", msg)

    return response
