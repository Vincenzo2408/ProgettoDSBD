from flask import Flask, jsonify, request
from prometheus_client import start_http_server, Counter, Gauge
from prometheus_client.exposition import generate_latest
import requests

app = Flask(__name__)

OPENWEATHERMAP_API_KEY = "daa8321f6f6e7ee16b75fecbd8cdc66a"  # Sostituisci con la tua chiave API
#DATABASE_SERVICE_URL = 'http://database-service:5000'  # Aggiungi l'URL del tuo database service

numero_richieste=Gauge('numero_richieste', 'Number of requests')

@app.route('/weather/<city>', methods=['GET'])
def get_weather(city):
    numero_richieste.inc()
    # Recupera dati meteo dalla API di OpenWeatherMap per la città specificata
    weather_data = fetch_weather_data(city)

    return jsonify(weather_data)

def fetch_weather_data(city):
    # Effettua una richiesta alla API di OpenWeatherMap
    api_url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={OPENWEATHERMAP_API_KEY}"
    response = requests.get(api_url)

    if response.status_code == 200:
        # Restituisci i dati meteo grezzi
        return response.json()
    else:
        # Se la richiesta fallisce, restituisci un messaggio di errore
        return {"message": "Errore al collegamento API"}, 500


@app.route('/metrics')
def metrics():
    return f"Numero_richieste {numero_richieste._value.get()}", 200



if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5002)
