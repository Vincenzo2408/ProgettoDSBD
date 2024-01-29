# user_management_service/app.py
from flask import Flask, jsonify, request
from flask_jwt_extended import JWTManager, jwt_required, create_access_token, get_jwt_identity, verify_jwt_in_request
import requests
import json

app = Flask(__name__)
app.config['JWT_SECRET_KEY'] = 'your-secret-key'
jwt = JWTManager(app)

# URL del database_service
DATABASE_SERVICE_URL = 'http://database-service:5000'

# Aggiorna le preferenze dell'utente
@app.route('/user/preferences', methods=['POST'])
@jwt_required()  
def add_weather_preferences():
    verify_jwt_in_request()
    current_user = get_jwt_identity()

    subscription_data = request.get_json()
    required_fields = ['city_name', 'temperature_max_preference', 'temperature_min_preference', 'rainfall_preference', 'snow_preference']

    # Verifica se tutti i campi richiesti sono presenti nella richiesta
    if all(field in subscription_data for field in required_fields):
        subscription_data['username'] = current_user

        # Verifica se l'utente è già sottoscritto a questa città
        user_subscriptions_response = requests.get(f'{DATABASE_SERVICE_URL}/user/subscriptions/{current_user}')
        if user_subscriptions_response.status_code == 200:
            user_subscriptions = user_subscriptions_response.json().get('subscriptions')
            subscribed_city_names = [sub['city_name'] for sub in user_subscriptions]

            if subscription_data['city_name'] in subscribed_city_names:
                # Invia una richiesta al database_service per sottoscrivere l'utente alla città
                subscribe_response = requests.post(f'{DATABASE_SERVICE_URL}/user/modify_to_city', json=subscription_data)

                if subscribe_response.status_code == 200:
                    # Aggiorna la lista delle sottoscrizioni dell'utente
                    user_subscriptions.append(subscription_data)
                    return jsonify({"message": "Modifica alle preferenze effettuata con successo!"})
                else:
                    return jsonify({"message": "Modifica non effettuata"}), subscribe_response.status_code
            else:
                return jsonify({"message": "L'utente non è sottoscritto a questa città"}), 400
        else:
            return jsonify({"message": "Errore nel recupero delle sottoscrizioni dell'utente"}), user_subscriptions_response.status_code
    else:
        return jsonify({"message": "Campi mancanti nella richiesta di sottoscrizione"}), 400

@app.route('/user/subscribe_to_city', methods=['POST'])
@jwt_required()  # Aggiunto il decoratore jwt_required per richiedere un token JWT valido
def subscribe_to_city():
    verify_jwt_in_request()
    current_user = get_jwt_identity()

    subscription_data = request.get_json()
    required_fields = ['city_name', 'temperature_max_preference', 'temperature_min_preference', 'rainfall_preference', 'snow_preference']

    # Verifica se tutti i campi richiesti sono presenti nella richiesta
    if all(field in subscription_data for field in required_fields):
        subscription_data['username'] = current_user

        # Verifica se l'utente è già sottoscritto a questa città
        user_subscriptions_response = requests.get(f'{DATABASE_SERVICE_URL}/user/subscriptions/{current_user}')
        if user_subscriptions_response.status_code == 200:
            user_subscriptions = user_subscriptions_response.json().get('subscriptions')
            subscribed_city_names = [sub['city_name'] for sub in user_subscriptions]

            if subscription_data['city_name'] not in subscribed_city_names:
                # Invia una richiesta al database_service per sottoscrivere l'utente alla città
                subscribe_response = requests.post(f'{DATABASE_SERVICE_URL}/user/subscribe_to_city', json=subscription_data)

                if subscribe_response.status_code == 200:
                    return jsonify({"message": "Sottoscrizione alla città effettuata con successo!"})
                else:
                    return jsonify({"message": "Errore nella sottoscrizione alla città"}), subscribe_response.status_code
            else:
                return jsonify({"message": "L'utente è già sottoscritto a questa città"}), 400
        else:
            return jsonify({"message": "Errore nel recupero delle sottoscrizioni dell'utente"}), user_subscriptions_response.status_code
    else:
        return jsonify({"message": "Campi mancanti nella richiesta di sottoscrizione"}), 400

@app.route('/user', methods=['POST'])
def add_user():
    user_data = request.get_json()

    username = user_data.get('username')
    email = user_data.get('email')
    password = user_data.get('password')

    # Invia una richiesta al database_service per aggiungere un nuovo utente senza preferenze iniziali
    new_user_response = requests.post(
        f'{DATABASE_SERVICE_URL}/user',
        json={"username": username, "email": email, "password": password}
    )
    
    if new_user_response.status_code == 200:
        access_token = create_access_token(identity=username)
        return jsonify({"message": "Utente registrato con successo", "token": access_token})
    else:
        return jsonify({"message": "Errore durante la registrazione dell'utente"}), new_user_response.status_code

@app.route('/user/login', methods=['POST'])
def login():
    login_data = request.get_json()
    username = login_data.get('username')
    password = login_data.get('password')

    # Invia una richiesta al database_service per il login
    login_response = requests.post(f'{DATABASE_SERVICE_URL}/user/login', json={"username": username, "password": password})
    
    if login_response.status_code == 200:
        access_token = create_access_token(identity=username)
        return jsonify({"token": access_token})
    else:
        return jsonify({"message": "Credenziali non valide"}), 401

@app.route('/users', methods=['GET'])
def get_users():
    # Invia una richiesta al database_service per ottenere la lista degli utenti
    users_response = requests.get(f'{DATABASE_SERVICE_URL}/users')

    if users_response.status_code == 200:
        users = users_response.json().get('users')
        user_list = []

        for user in users:
            user_data = {
                "id": user.get('id'),
                "username": user.get('username'),
                "email": user.get('email'),
                "subscriptions": []  # Campo per le città di sottoscrizione
            }

            # Aggiungi le sottoscrizioni delle città solo se presenti
            if 'subscriptions' in user:
                user_data['subscriptions'] = user.get('subscriptions')

            user_list.append(user_data)

        return jsonify({"users": user_list})
    else:
        return jsonify({"message": "Errore durante il recupero degli utenti"}), users_response.status_code

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001)

