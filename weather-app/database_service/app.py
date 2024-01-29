# database_service/app.py
from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from prometheus_client import start_http_server, Counter, Gauge
from prometheus_client.exposition import generate_latest
import requests
import json
import schedule
import time
from flask_caching import Cache
from random import uniform

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////tmp/test.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['CACHE_TYPE'] = 'simple'  
cache = Cache(app)
db = SQLAlchemy(app)


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)
    city_subscriptions = db.relationship('CitySubscription', backref='user', lazy='dynamic')

class City(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    temperature_max = db.Column(db.Integer)
    temperature_min = db.Column(db.Integer)
    rainfall = db.Column(db.Boolean)
    snow = db.Column(db.Boolean)
    city_subscriptions = db.relationship('CitySubscription', backref='city', lazy='dynamic')

class CitySubscription(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    city_id = db.Column(db.Integer, db.ForeignKey('city.id'))
    temperature_max_preference = db.Column(db.Integer)
    temperature_min_preference = db.Column(db.Integer)
    snow_preference = db.Column(db.Boolean)
    rainfall_preference = db.Column(db.Boolean)

    def __init__(self, user_id, city_id, temperature_max_preference, temperature_min_preference, snow_preference, rainfall_preference):
        self.user_id = user_id
        self.city_id = city_id
        self.temperature_max_preference = temperature_max_preference
        self.temperature_min_preference = temperature_min_preference
        self.snow_preference = snow_preference
        self.rainfall_preference = rainfall_preference


# Funzione per convertire Kelvin in Celsius
def convert_kelvin_to_celsius(kelvin):
    return kelvin - 273.15 if kelvin is not None else None

def load_cities():
    cities_to_scrape = ["Rome,IT", "Lucca", "Paris", "London", "New York", "Tokyo"]

    for city_name in cities_to_scrape:
        scraping_response = requests.get(f'http://scraper-service:5002/weather/{city_name}')

        if scraping_response.status_code == 200:
            weather_data = scraping_response.json()
            temperature_max = convert_kelvin_to_celsius(weather_data.get('main', {}).get('temp_max'))
            temperature_min = convert_kelvin_to_celsius(weather_data.get('main', {}).get('temp_min'))
            rainfall = True if weather_data.get('weather', [])[0].get('main') == 'Rain' else False
            snow = True if weather_data.get('weather', [])[0].get('main') == 'Snow' else False

            # Cerca la città nel database per verificare se esiste già
            existing_city = City.query.filter_by(name=city_name).first()

            if existing_city:
                # Aggiorna i valori della città esistente
                existing_city.temperature_max = temperature_max #+ uniform(-5, 5)
                existing_city.temperature_min = temperature_min
                existing_city.rainfall = rainfall
                existing_city.snow = snow
              
            else:
                # Aggiungi la città al database
                city = City(
                    name=city_name,
                    temperature_max=temperature_max,
                    temperature_min=temperature_min,
                    rainfall=rainfall,
                    snow=snow
                )
                db.session.add(city)
        else:
            print(f"Failed to fetch weather data for {city_name}")

    db.session.commit()
    print("City data loaded successfully")


# Funzione per inizializzare il caricamento delle città al lancio del microservizio
def init_load_cities():
    with app.app_context():
        load_cities()

@app.route('/cities', methods=['GET'])
def get_all_cities():
    cities = City.query.all()

    city_list = []

    for city in cities:
        city_data = {
            "id": city.id,
            "name": city.name,
            "temperature_max": city.temperature_max,
            "temperature_min": city.temperature_min,
            "rainfall": city.rainfall,
            "snow": city.snow
        }
        city_list.append(city_data)

    return jsonify({"cities": city_list}), 200

# Aggiorna le preferenze dell'utente per una specifica città o sottoscrive una nuova città
@app.route('/user/subscribe_to_city', methods=['POST'])
def subscribe_to_city():
    subscription_data = request.get_json()

    user = User.query.filter_by(username=subscription_data['username']).first()
    if not user:
        return jsonify({"message": "Utente non trovato"}), 404

    city = City.query.filter_by(name=subscription_data['city_name']).first()
    if not city:
        return jsonify({"message": "Città non trovata"}), 404

    # Verifica se l'utente è già sottoscritto a questa città
    if user.city_subscriptions.filter_by(city_id=city.id).first():
        return jsonify({"message": "L'utente è già sottoscritto a questa città"}), 400

    # Aggiungi la sottoscrizione della città per l'utente
    city_subscription = CitySubscription(
        user_id=user.id,
        city_id=city.id,
        temperature_max_preference=subscription_data['temperature_max_preference'],
        temperature_min_preference=subscription_data['temperature_min_preference'],
        snow_preference=subscription_data['snow_preference'],
        rainfall_preference=subscription_data['rainfall_preference']
    )
    db.session.add(city_subscription)
    db.session.commit()

    return jsonify({"message": "Sottoscrizione alla città effettuata con successo"}), 200


@app.route('/user', methods=['POST'])
def add_user():
    user_data = request.get_json()

    new_user = User(
        username=user_data['username'],
        email=user_data['email'],
        password=user_data['password']
    )

    db.session.add(new_user)
    db.session.commit()

    return jsonify({"message": "Utente registrato con successo"}), 200


# Ottieni le informazioni sull'utente comprese le preferenze e le sottoscrizioni
@app.route('/user/<username>', methods=['GET'])
def get_user(username):
    user = User.query.filter_by(username=username).first()

    if user:
        user_data = {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "subscriptions": []  
        }

        # Aggiungi le città di sottoscrizione
        subscriptions = CitySubscription.query.filter_by(user_id=user.id).all()
        for subscription in subscriptions:
            city_subscription_data = {
                "city_name": subscription.city.name,
                "temperature_max_preference": subscription.temperature_max_preference,
                "temperature_min_preference": subscription.temperature_min_preference,
                "snow_preference": subscription.snow_preference,
                "rainfall_preference": subscription.rainfall_preference
            }
            user_data['subscriptions'].append(city_subscription_data)

        return jsonify(user_data), 200
    else:
        return jsonify({"message": "Utente non trovato"}), 404

# Aggiorna le preferenze dell'utente
@app.route('/user/modify_to_city', methods=['POST'])
def update_user_preferences():
    subscription_data = request.get_json()

    username = subscription_data.get('username')
    user = User.query.filter_by(username=username).first()

    if not user:
        return jsonify({"message": "Utente non trovato"}), 404

    city_name = subscription_data.get('city_name')
    city = City.query.filter_by(name=city_name).first()

    if not city:
        return jsonify({"message": "Città non trovata"}), 406

    # Cerca la sottoscrizione esistente per la stessa città
    city_subscription = user.city_subscriptions.filter_by(city_id=city.id).first()

    if city_subscription:
        # Se esiste, aggiorna i valori
        city_subscription.temperature_max_preference = subscription_data.get('temperature_max_preference')
        city_subscription.temperature_min_preference = subscription_data.get('temperature_min_preference')
        city_subscription.snow_preference = subscription_data.get('snow_preference')
        city_subscription.rainfall_preference = subscription_data.get('rainfall_preference')
        db.session.commit()
        return jsonify({"message": "Modifiche alla città effettuata con successo"}), 200
    else:
        return jsonify({"message": "Utente non sottoscritto"}), 400


@app.route('/user/login', methods=['POST'])
def login():
    login_data = request.get_json()
    username = login_data.get('username')
    password = login_data.get('password')

    user = User.query.filter_by(username=username, password=password).first()

    if user:
        return jsonify({"message": "Login effettuato con successo"})
    else:
        return jsonify({"message": "Credenziali non valide"}), 401

from flask import jsonify

@app.route('/users', methods=['GET'])
def get_users():
    users = User.query.all()

    user_list = []

    for user in users:
        user_data = {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "subscriptions": []  
        }

        # Aggiungi le città di sottoscrizione
        subscriptions = CitySubscription.query.filter_by(user_id=user.id).all()
        for subscription in subscriptions:
            city_subscription_data = {
                "city_name": subscription.city.name,
                "temperature_max_preference": subscription.temperature_max_preference,
                "temperature_min_preference": subscription.temperature_min_preference,
                "snow_preference": subscription.snow_preference,
                "rainfall_preference": subscription.rainfall_preference
            }
            user_data['subscriptions'].append(city_subscription_data)

        user_list.append(user_data)

    return jsonify({"users": user_list})


@app.route('/user/subscriptions/<username>', methods=['GET'])
def get_user_subscriptions(username):
    user = User.query.filter_by(username=username).first()

    if user:
        subscriptions = CitySubscription.query.filter_by(user_id=user.id).all()

        subscription_list = []

        for subscription in subscriptions:
            subscription_data = {
                "city_name": subscription.city.name,
                "temperature_max_preference": subscription.temperature_max_preference,
                "temperature_min_preference": subscription.temperature_min_preference,
                "snow_preference": subscription.snow_preference,
                "rainfall_preference": subscription.rainfall_preference
            }

            subscription_list.append(subscription_data)

        return jsonify({"subscriptions": subscription_list}), 200
    else:
        return jsonify({"message": "Utente non trovato"}), 404

@app.route('/user/preferences/<user_id>', methods=['GET'])
def get_user_preferences(user_id):
    # Cerca l'utente nel database
    user = User.query.filter_by(id=user_id).first()

    if user:
        # Ottieni le preferenze dell'utente dalla tabella CitySubscription
        preferences = CitySubscription.query.filter_by(user_id=user.id).all()

        # Formatta le preferenze in un elenco di dizionari
        preferences_data = []
        for preference in preferences:
            preference_data = {
                "city_name": preference.city.name,
                "temperature_max_preference": preference.temperature_max_preference,
                "temperature_min_preference": preference.temperature_min_preference,
                "snow_preference": preference.snow_preference,
                "rainfall_preference": preference.rainfall_preference
            }
            preferences_data.append(preference_data)

        return jsonify({"preferences": preferences_data}), 200
    else:
        return jsonify({"message": "Utente non trovato"}), 404

#Creare una metrica di tipo Gauge per conteneri il numero di utenti iscritti
users_gauge = Gauge('utenti_registrati', 'Number of subscribed users')


@app.route('/metrics')
def metrics():
    # Ottieni il numero di utenti dalla tabella User
    total_users = User.query.count()

    # Imposta il valore del Gauge per il numero di utenti iscritti
    users_gauge.set(total_users)

    # Ritorna le metriche di Prometheus
    return f"utenti_registrati {total_users}", 200

    
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        init_load_cities()

    # Configura Flask-Cache
    cache.init_app(app)

    # Configura e avvia il pianificatore di compiti
    scheduler = BackgroundScheduler()
    scheduler.start()
    scheduler.add_job(
        func=init_load_cities,
        trigger=IntervalTrigger(minutes=20),
        id='load_cities_job',
        name='Caricamento Città',
        replace_existing=True
    )

    # Avvia il microservizio
    app.run(host='0.0.0.0', port=5000, debug=True)



