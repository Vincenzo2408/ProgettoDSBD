from flask import Flask, jsonify, request, current_app
from flask_mail import Mail, Message
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
import requests
import threading

app = Flask(__name__)
app.config['MAIL_SERVER'] = 'sandbox.smtp.mailtrap.io'
app.config['MAIL_PORT'] = 25
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USE_SSL'] = False
app.config['MAIL_USERNAME'] = '336f11a3d4abea'  # Inserisci il tuo nome utente Mailtrap
app.config['MAIL_PASSWORD'] = '1647b691be0e47'  # Inserisci la tua password Mailtrap
app.config['MAIL_DEFAULT_SENDER'] = 'peggy@examplebau.com'  # Inserisci il tuo indirizzo email di default

mail = Mail(app)

#USER_MANAGEMENT_SERVICE_URL = "http://user-management-service:5001"
DATABASE_SERVICE_URL = "http://database-service:5000"

# Utilizzato per bloccare l'esecuzione del job se è già in corso
scheduler_lock = threading.Lock()

# Variabile di stato per controllare l'esecuzione del job
is_job_running = False

def check_and_notify_preferences():
    global is_job_running

    with scheduler_lock:
        if is_job_running:
            print("Il job è già in esecuzione, quindi non verrà avviato nuovamente.")
            return

        is_job_running = True

    try:
        with app.app_context():
            # Ottieni tutti gli utenti dal servizio di gestione degli utenti
            users_response = requests.get(f"{DATABASE_SERVICE_URL}/users")

            if users_response.status_code == 200:
                users = users_response.json().get('users')

                for user in users:
                    user_id = user.get('id')
                    user_email = user.get('email')
                    satisfied_preferences = []
                    unsatisfied_preferences = []

                    # Ottieni le preferenze dell'utente direttamente dal servizio di database
                    preferences_response = requests.get(f"{DATABASE_SERVICE_URL}/user/preferences/{user_id}")

                    if preferences_response.status_code == 200:
                        user_preferences = preferences_response.json().get('preferences')

                        # Ottieni i dati della città dal servizio di database
                        cities_response = requests.get(f"{DATABASE_SERVICE_URL}/cities")

                        if cities_response.status_code == 200:
                            cities = cities_response.json().get('cities')

                            # Confronta le preferenze dell'utente con i dati della città
                            for preference in user_preferences:
                                for city in cities:
                                    if preference['city_name'] == city['name']:
                                        #if check_preference_satisfaction(preference, city):
                                        #    satisfied_preferences.append(preference)
                                        #else:
                                        #    unsatisfied_preferences.append(preference)
                                        
                                        if preference['temperature_max_preference'] >= city['temperature_max']: 
                                            satisfied_preferences.append(f"Temperatura Massima: {preference['temperature_max_preference']}")
                                        else: 
                                            unsatisfied_preferences.append(f"Temperatura Massima: {preference['temperature_max_preference']}")

                                        if preference['temperature_min_preference'] <= city['temperature_min']: 
                                            satisfied_preferences.append(f"Temperatura Minima: {preference['temperature_min_preference']}")
                                        else: 
                                            unsatisfied_preferences.append(f"Temperatura Minima: {preference['temperature_min_preference']}")

                                        if preference['rainfall_preference'] == city['rainfall']: 
                                            satisfied_preferences.append(f"Pioggia: {preference['rainfall_preference']}")
                                        else: 
                                            unsatisfied_preferences.append(f"Pioggia: {preference['rainfall_preference']}") 

                                        if preference['snow_preference'] == city['snow']:
                                            satisfied_preferences.append(f"Neve: {preference['snow_preference']}")
                                        else: 
                                            unsatisfied_preferences.append(f"Neve: {preference['snow_preference']}")

                            # Notifica l'utente via email con le preferenze soddisfatte e non soddisfatte
                            send_notification_email(user_email, preference['city_name'], satisfied_preferences, unsatisfied_preferences)
                    else:
                        print(f"Errore nel recupero delle preferenze per l'utente {user_id}")
            else:
                print("Errore nel recupero degli utenti")

    finally:
        is_job_running = False

def send_notification_email(recipient_email, city, satisfied_preferences, unsatisfied_preferences):
    with app.app_context():
        # Costruisci il messaggio email
        subject = f"Preference Notification"
        body = f"Per la città {city} abbiamo: \nPreferenze soddisfatte: {satisfied_preferences}\nPreferences non soddisfatte: {unsatisfied_preferences}"

        # Invia l'email
        msg = Message(subject=subject, recipients=[recipient_email])
        msg.body = body
        mail.send(msg)

if __name__ == '__main__':
    # Configura Flask-Mail
    mail.init_app(app)

    # Configura e avvia il pianificatore di compiti
    scheduler = BackgroundScheduler()
    scheduler.add_job(check_and_notify_preferences, IntervalTrigger(minutes=60), id='check_and_notify_preferences') #60
    scheduler.start()

    # Avvia il microservizio
    app.run(host='0.0.0.0', port=5005)
