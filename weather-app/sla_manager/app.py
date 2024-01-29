from flask import Flask, jsonify, request
from prometheus_client import Gauge, CollectorRegistry, generate_latest
from prometheus_client.exposition import CONTENT_TYPE_LATEST
from datetime import datetime, timedelta
from confluent_kafka import Producer
from confluent_kafka import KafkaException
import json
import random
import requests
import sqlite3

app = Flask(__name__)

kafka_producer_config = {
    'bootstrap.servers': 'kafka:29092',  # Indirizzo del broker Kafka
    'client.id': 'prometheus-producer'
}

kafka_producer = Producer(kafka_producer_config)

# Funzione per inviare dati a un topic Kafka
def send_to_kafka(topic, data):
    try:
        # Invia i dati serializzati in formato JSON al topic Kafka
        kafka_producer.produce(topic, key='prometheus', value=json.dumps(data))
        kafka_producer.flush()
        print(f'Dati inviati con successo al topic {topic}: {message}')
    except Exception as e:
        print(f'Errore durante l\'invio dei dati a {topic}: {str(e)}')


# Funzione per creare il database SQLite e la tabella
def create_database():
    conn = sqlite3.connect('sla_manager_data.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sla_metrics (
            metric_name TEXT PRIMARY KEY,
            metric_value REAL
        )
    ''')
    conn.commit()

# Funzione per memorizzare una metrica nel database
def store_metric_in_database(metric_name, metric_value):
    conn = sqlite3.connect('sla_manager_data.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO sla_metrics (metric_name, metric_value) VALUES (?, ?)
    ''', (metric_name, metric_value))
    conn.commit()

# Funzione per caricare i dati iniziali dal database
def load_initial_data_from_database():
    conn = sqlite3.connect('sla_manager_data.db')
    cursor = conn.cursor()
    cursor.execute('SELECT metric_name, metric_value FROM sla_metrics')
    rows = cursor.fetchall()
    
    for row in rows:
        metric_name, metric_value = row
        sla_metrics[metric_name].set(metric_value)


# Dizionario per mantenere le metriche
sla_metrics = {
    'utenti_registrati': Gauge('utenti_registrati', 'Number of subscribed users'),
    'numero_richieste': Gauge('numero_richieste', 'Number of requests'),
    'cpu_usage': Gauge('cpu_usage', 'CPU Usage Percentage', ['service']),
    'memory_usage': Gauge('memory_usage', 'Memory Usage Bytes', ['service']),
    'utenti_registrati_desiderati': Gauge('utenti_registrati_desiderati', 'Desired number of subscribed users'),
    'numero_richieste_desiderati': Gauge('numero_richieste_desiderati', 'Desired number of requests'),
    'cpu_usage_desiderato': Gauge('cpu_usage_desiderato', 'Desired CPU Usage Percentage'),
    'memory_usage_desiderato': Gauge('memory_usage_desiderato', 'Desired Memory Usage Bytes'),
    'sla_manager_results': Gauge('sla_manager_results', 'SLA Manager Results', ['metric']),
    'violations_false_count_1_hour': Gauge('violations_false_count_1_hour', 'Number of False Violations after 1 hour'),
    'violations_false_count_3_hours': Gauge('violations_false_count_3_hours', 'Number of False Violations after 3 hours'),
    'violations_false_count_6_hours': Gauge('violations_false_count_6_hours', 'Number of False Violations after 6 hours'),
}

removed_metrics = {}

# Imposta i valori iniziali per le metriche desiderate
sla_metrics['utenti_registrati_desiderati'].set(20)
sla_metrics['numero_richieste_desiderati'].set(12)
sla_metrics['cpu_usage_desiderato'].set(0.10)
sla_metrics['memory_usage_desiderato'].set(7.2683648e+07)

# Chiamate per creare il database e caricare i dati iniziali
create_database()
load_initial_data_from_database()

# Funzione per ottenere il numero di utenti da database_service
def get_users_count_from_database_service():
    try:
        response = requests.get('http://database-service:5000/metrics?name=utenti_registrati')
        if response.status_code == 200:
            # Imposta il valore della metrica utenti_registrati
            users_count = float(response.text.split()[1])
            sla_metrics['utenti_registrati'].set(users_count)
            return users_count
        else:
            # Gestisci eventuali errori nella richiesta
            print(f"Failed to fetch user count from database service. Status code: {response.status_code}")
            return 0
    except Exception as e:
        print(f"Error during request to database service: {str(e)}")
        return 0

# Funzione per ottenere il numero di richieste da management_service
def get_requests_count_from_scraper_service():
    try:
        response = requests.get('http://scraper-service:5002/metrics?name=numero_richieste')
        if response.status_code == 200:
            # Imposta il valore della metrica numero_richieste
            requests_count = float(response.text.split()[1])
            sla_metrics['numero_richieste'].set(requests_count)
            return requests_count
        else:
            # Gestisci eventuali errori nella richiesta
            print(f"Failed to fetch requests count from management service. Status code: {response.status_code}")
            return 0
    except Exception as e:
        print(f"Error during request to management service: {str(e)}")
        return 0

# Funzione per ottenere le metriche da Prometheus
def get_prometheus_metrics():
    # Esempio di endpoint di Prometheus per CPU e Memory
    prometheus_endpoint = 'http://prometheus:9090'

    cpu_query = 'container_cpu_system_seconds_total{container_label_service_port=~"5000|5001|5002|5005"}'
    memory_query = 'container_memory_max_usage_bytes{container_label_service_port=~"5000|5001|5002|5005"}'

    cpu_metrics_url = f"{prometheus_endpoint}/api/v1/query?query={cpu_query}"
    memory_metrics_url = f"{prometheus_endpoint}/api/v1/query?query={memory_query}"

    # Effettua le richieste a Prometheus
    cpu_response = requests.get(cpu_metrics_url)
    memory_response = requests.get(memory_metrics_url)

    # Analizza le risposte e aggiorna i valori delle metriche
    cpu_metrics = cpu_response.json()['data']['result']
    memory_metrics = memory_response.json()['data']['result']

    for cpu_metric in cpu_metrics:
        service_port = cpu_metric['metric']['container_label_service_port']
        cpu_value = float(cpu_metric['value'][1])
        if 'cpu_usage' in sla_metrics:
            sla_metrics['cpu_usage'].labels(service=service_port).set(cpu_value)

    for memory_metric in memory_metrics:
        service_port = memory_metric['metric']['container_label_service_port']
        memory_value = float(memory_metric['value'][1])
        if 'memory_usage' in sla_metrics:
            sla_metrics['memory_usage'].labels(service=service_port).set(memory_value)

# Aggiungi una variabile per tenere traccia del tempo di avvio dell'applicazione
app_start_time = datetime.now()

def calculate_elapsed_time():
    # Calcola il tempo trascorso dall'avvio dell'applicazione
    elapsed_time = datetime.now() - app_start_time

    # Calcola il tempo trascorso per ciascun contatore
    elapsed_time_1_hour = elapsed_time.total_seconds() if elapsed_time.total_seconds() < 36 else 36      #3600
    elapsed_time_3_hours = elapsed_time.total_seconds() if elapsed_time.total_seconds() < 56 else 56  #10800
    elapsed_time_6_hours = elapsed_time.total_seconds() if elapsed_time.total_seconds() < 86 else 86  #21600

    return elapsed_time.total_seconds(), elapsed_time_1_hour, elapsed_time_3_hours, elapsed_time_6_hours

entry1=0
entry2=0
entry3=0

def update_violations_counts(false_checks_count):
    global entry1, entry2, entry3
    # Calcola il tempo trascorso
    elapsed_time_seconds, elapsed_time_1_hour, elapsed_time_3_hours, elapsed_time_6_hours = calculate_elapsed_time()

    # Aggiorna il conteggio totale
    global total_false_violations_count
    total_false_violations_count = false_checks_count

    # Aggiorna i tre contatori separati in base allo stato corrente del tempo
    if(entry1==0):
        if(elapsed_time_1_hour >= 36):
            sla_metrics['violations_false_count_1_hour'].set(total_false_violations_count)      #3600
            entry1=1
        else: 
            sla_metrics['violations_false_count_1_hour'].set(0)
    
    if(entry2==0):
        if(elapsed_time_3_hours >= 56):
            sla_metrics['violations_false_count_3_hours'].set(total_false_violations_count)   #10800
            entry2=1
        else: 
            sla_metrics['violations_false_count_3_hours'].set(0)

    if(entry3==0):
        if(elapsed_time_6_hours >= 86):
            sla_metrics['violations_false_count_6_hours'].set(total_false_violations_count)   #21600
            entry3=1
        else: 
            sla_metrics['violations_false_count_6_hours'].set(0)

false_checks_count=0


#API per aggiungere nuova metrica
@app.route('/add_metric/<metric_name>')
def add_metric(metric_name):
    global sla_metrics, removed_metrics  

    # Controlla se la metrica è stata precedentemente rimossa
    if metric_name in removed_metrics:
        # Recupera la metrica rimossa dal dizionario delle metriche rimosse
        existing_metric = removed_metrics[metric_name]
        # Ripristina la metrica nello sla_metrics
        sla_metrics[metric_name] = existing_metric
        # Rimuovi la metrica dal dizionario delle metriche rimosse
        del removed_metrics[metric_name]

        return f'Metrica {metric_name} riaggiunta con successo.'

    # Controlla se la metrica è già presente
    #if metric_name in sla_metrics:
    #    return f'Metric {metric_name} already exists.'

    # Aggiungi la metrica
    #sla_metrics[metric_name] = Gauge(metric_name, f'Description for {metric_name}')

    return f'Metrica {metric_name} non presente tra quelli rimossi in precedenza.'

#API per rimuovere nuova metrica
@app.route('/remove_metric/<metric_name>')
def remove_metric(metric_name):
    global sla_metrics, removed_metrics 

    # Controlla se la metrica è presente
    if metric_name not in sla_metrics:
        return f'Metrica {metric_name} non esiste.'

    # Rimuovi la metrica e conserva il valore
    removed_metrics[metric_name] = sla_metrics.pop(metric_name)

    return f'Metrica {metric_name} rimossa con successo.'

@app.route('/get_data_from_db')
def get_data_from_db():
    try:
        conn = sqlite3.connect('sla_manager_data.db')
        cursor = conn.cursor()
        # Esempio di query per ottenere tutti i dati dalla tabella
        query = "SELECT * FROM sla_metrics;"
        cursor.execute(query)
        data = cursor.fetchall()

        # Puoi elaborare i dati come desiderato prima di restituirli
        # Ad esempio, qui converto i risultati in un elenco di dizionari
        results = []
        for row in data:
            metric_name, metric_value = row
            result = {'metric_name': metric_name, 'metric_value': metric_value}
            results.append(result)

        return jsonify(results)

    except Exception as e:
        return jsonify({'error': str(e)})


    
# Endpoint per ottenere le metriche
@app.route('/metrics')
def prometheus_metrics():
    global false_checks_count
    global false_actually_count

    # Ottieni i valori ottenuti
    users_count = get_users_count_from_database_service()
    requests_count = get_requests_count_from_scraper_service()
    get_prometheus_metrics()

    # Confronta i valori ottenuti con quelli desiderati
    users_check = sla_metrics['utenti_registrati_desiderati']._value.get() < users_count
    requests_check = sla_metrics['numero_richieste_desiderati']._value.get() <= requests_count

    # Confronta i valori di CPU e Memory per ogni porta
    cpu_checks = []
    memory_checks = []

    if 'cpu_usage' in sla_metrics:
        for service, cpu_metric in sla_metrics['cpu_usage']._metrics.items():
            cpu_value = cpu_metric._value.get()
            desired_cpu_value = sla_metrics['cpu_usage_desiderato']._value.get()
            cpu_checks.append(desired_cpu_value >= cpu_value)

    if 'memory_usage' in sla_metrics:
        for service, memory_metric in sla_metrics['memory_usage']._metrics.items():
            memory_value = memory_metric._value.get()
            desired_memory_value = sla_metrics['memory_usage_desiderato']._value.get()
            memory_checks.append(desired_memory_value >= memory_value)



    # Registra i risultati nei Gauge
    sla_metrics['sla_manager_results'].labels(metric='utenti_registrati_check').set(True if users_check else False)
    sla_metrics['sla_manager_results'].labels(metric='numero_richieste_check').set(True if requests_check else False)

    
    for i, check in enumerate(cpu_checks):
        sla_metrics['sla_manager_results'].labels(metric=f'cpu_check_{i}').set(True if check else False)

    for i, check in enumerate(memory_checks):
        sla_metrics['sla_manager_results'].labels(metric=f'memory_check_{i}').set(True if check else False)

    #Conta il numero totale di False per ciascun controllo (ad ogni ciclo -> mi serve per la probabilità)
    false_actually_count = sum(1 for check in [users_check, requests_check] + cpu_checks + memory_checks if not check)

    # Conta il numero totale di False per ciascun controllo (complessivo)
    false_checks_count = sum(1 for check in [users_check, requests_check] + cpu_checks + memory_checks if not check) + false_checks_count 

    # Aggiorna i tre contatori separati
    update_violations_counts(false_checks_count)

    # Salva i dati nel database
    store_metric_in_database('utenti_registrati_check', 1 if users_check else 0)
    store_metric_in_database('numero_richieste_check', 1 if requests_check else 0)

    for i, check in enumerate(cpu_checks):
        store_metric_in_database(f'cpu_check_{i}', 1 if check else 0)

    for i, check in enumerate(memory_checks):
        store_metric_in_database(f'memory_check_{i}', 1 if check else 0)

    # Definisci i dati che vuoi inviare a Kafka
    kafka_data = {
        'utenti_registrati_check': True if users_check else False,
        'numero_richieste_check': True if requests_check else False,
        'cpu_checks': [True if check else False for check in cpu_checks],
        'memory_checks': [True if check else False for check in memory_checks],
        'false_checks_count': false_checks_count,
    }

    # Specifica il topic Kafka in cui vuoi inviare i dati
    kafka_topic = 'prometheusdata'

    # Invia i dati a Kafka
    send_to_kafka(kafka_topic, kafka_data)

    
    # Restituisci i risultati dei confronti insieme al registro Prometheus
    registry = CollectorRegistry()
    
    for metric in sla_metrics.values():
        registry.register(metric)
    
    response_body = generate_latest(registry)
    return response_body, 200, {'Content-Type': CONTENT_TYPE_LATEST}


# API per CREATE/UPDATE del SLA
@app.route('/sla', methods=['POST', 'PUT'])
def create_update_sla():
    data = request.get_json()

    # Aggiorna il set di metriche e valori ammissibili in base ai dati forniti
    for metric_name, metric_value in data.items():
        if metric_name in sla_metrics:
            sla_metrics[metric_name].set(metric_value)

            # Salva i dati nel database
            store_metric_in_database(metric_name, metric_value)

    return jsonify({'message': 'SLA updated successfully'})

# API per QUERY dello stato del SLA
# Funzione per ottenere lo stato corrente del SLA
@app.route('/sla', methods=['GET'])
def sla_route():
    return get_sla_status()

# Funzione per ottenere lo stato corrente del SLA
def get_sla_status():
    sla_status = {}

    # Recupera lo stato corrente del SLA dalle metriche
    for metric_name, metric in sla_metrics.items():
        # Usa collect() per ottenere i valori etichettati della metrica
        metric_samples = metric.collect()

        if metric_name == 'cpu_usage':
            for sample in metric_samples:
                for i, sample_data in enumerate(sample.samples):
                    service = sample_data.labels['service']
                    value = sample_data.value
                    metric_key = f"cpu_usage_{service}_{i}"
                    sla_status[metric_key] = value

        elif metric_name == 'memory_usage':
            for sample in metric_samples:
                for i, sample_data in enumerate(sample.samples):
                    service = sample_data.labels['service']
                    value = sample_data.value
                    metric_key = f"memory_usage_{service}_{i}"
                    sla_status[metric_key] = value

        else:
            # Gestisci le altre metriche come originariamente
            metric_values = {f"{metric_name}_{i}": sample.samples[0].value for i, sample in enumerate(metric_samples)}
            sla_status.update(metric_values)

    return jsonify(sla_status)


# API per QUERY del numero di violazioni
@app.route('/violations', methods=['GET'])
def get_violations_count():
    violations_1_hour = sla_metrics['violations_false_count_1_hour']._value.get()
    violations_3_hours = sla_metrics['violations_false_count_3_hours']._value.get()
    violations_6_hours = sla_metrics['violations_false_count_6_hours']._value.get()

    return jsonify({
        'violations_1_hour': violations_1_hour,
        'violations_3_hours': violations_3_hours,
        'violations_6_hours': violations_6_hours
    })

# Endpoint per ottenere la probabilità di violazioni nei prossimi X minuti
@app.route('/probability_of_violations/<int:minutes>', methods=['GET'])
def probability_of_violations(minutes):
    global false_actually_count

    # Numero di violazioni attuali
    current_violations = false_actually_count

    # Fattore per il tempo (minore è il tempo, maggiore è il fattore)
    time_factor = 1 / minutes if minutes > 0 else 0

    # Fattore per le violazioni attuali (maggiore è il numero di violazioni, maggiore è il fattore)
    violations_factor = current_violations / 10  # numero massimo di violazioni

    # Calcolo della probabilità
    probability = 100 * (violations_factor * time_factor)

    # Limita la probabilità a 100%
    probability = min(probability, 100)

    return jsonify({f'Probabilità di violazione nei prossimi {minutes} minuti è pari a': probability})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5003, debug=True)




