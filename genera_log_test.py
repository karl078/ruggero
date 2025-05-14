import datetime
import os
import calendar # Aggiungi questa riga per importare il modulo calendar

# --- Configurazione per la generazione dei log di esempio ---
NUM_MESI_ARCHIVIO = 2 # Genera log per il mese corrente e 2 mesi archiviati
CLIENTI_IP = ["192.168.1.100", "192.168.1.101"]
BASE_DIR = r"c:\Users\Carlo\Documents\DEV\Rpi\Server raccolta dati misurazione acqua"
LOG_DIR = os.path.join(BASE_DIR, "logs")

# Assicurati che la directory dei log esista
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)
    print(f"Directory creata: {LOG_DIR}")

def genera_dati_log_mese(year, month, client_ips):
    """Genera stringhe di log per un dato anno/mese e lista di client."""
    log_lines = []
    # Rimosso giorni_esempio, ora si itera su tutti i giorni del mese
    ore_esempio = ["08:30", "12:15", "17:45"]
    livelli_acqua_esempio = {
        client_ips[0]: [150.00, 145.50, 160.20, 130.00, 125.80, 140.00, 155.0, 135.5, 165.0, 120.0, 115.8, 145.0], # Aggiunti più valori per varietà
        client_ips[1]: [110.75, 105.00, 120.00, 95.30, 115.00, 100.50, 118.0, 102.0, 122.0, 90.0, 112.0, 98.5]  # Aggiunti più valori per varietà
    }
    
    num_giorni_mese = calendar.monthrange(year, month)[1]

    for giorno_num in range(1, num_giorni_mese + 1): # Itera da 1 all'ultimo giorno del mese
        for client_ip in client_ips:
            # Prendi un livello di esempio, ciclando se necessario
            # Usa (giorno_num - 1) per l'indice basato su 0
            livello = livelli_acqua_esempio[client_ip][(giorno_num - 1) % len(livelli_acqua_esempio[client_ip])]
            # Prendi un'ora di esempio
            ora = ore_esempio[(giorno_num - 1) % len(ore_esempio)]
            # Formatta la data
            data_str = f"{giorno_num:02d}/{month:02d}/{year:04d}"
            log_lines.append(f"{data_str}    {ora}    {livello:.2f}    (Client: {client_ip})")
            # Aggiungi una seconda misurazione per lo stesso giorno per testare la logica "ultima misurazione"
            if (giorno_num -1) % 2 == 0 : # Ad esempio, per ogni due giorni (basato sull'indice)
                 livello_bis = livello - 5.0 # Leggermente diverso
                 ora_bis = "20:00" # Un'ora successiva
                 log_lines.append(f"{data_str}    {ora_bis}    {livello_bis:.2f}    (Client: {client_ip})")
    return "\n".join(log_lines)

# Calcola le date
oggi = datetime.date.today()
date_da_generare = [] # Lista di tuple (anno, mese, nome_file)

# Mese corrente
date_da_generare.append(
    (oggi.year, oggi.month, os.path.join(LOG_DIR, "measurements.log"))
)

# Mesi archiviati
data_corrente_per_ciclo = oggi
for i in range(NUM_MESI_ARCHIVIO):
    # Vai al primo giorno del mese corrente per evitare problemi con i mesi con meno giorni
    primo_del_mese_corrente = data_corrente_per_ciclo.replace(day=1)
    # Sottrai un giorno per andare all'ultimo giorno del mese precedente
    ultimo_del_mese_precedente = primo_del_mese_corrente - datetime.timedelta(days=1)
    
    nome_file_archivio = os.path.join(
        LOG_DIR,
        f"measurements.log.{ultimo_del_mese_precedente.year:04d}-{ultimo_del_mese_precedente.month:02d}"
    )
    date_da_generare.append(
        (ultimo_del_mese_precedente.year, ultimo_del_mese_precedente.month, nome_file_archivio)
    )
    data_corrente_per_ciclo = ultimo_del_mese_precedente # Aggiorna per il prossimo ciclo

print("Contenuto dei file di log generati (da copiare nei rispettivi file):\n")

for year, month, file_path in date_da_generare:
    contenuto_log = genera_dati_log_mese(year, month, CLIENTI_IP)
    print(f"--- Contenuto per: {file_path} ---")
    print(contenuto_log)
    print("--------------------------------------------------\n")
    
    # Scrive direttamente i file per comodità (puoi commentare se preferisci copiare manualmente)
    try:
        with open(file_path, "w") as f:
            f.write(contenuto_log)
        print(f"File '{file_path}' scritto con successo.")
    except IOError as e:
        print(f"Errore durante la scrittura del file '{file_path}': {e}")
    print("--------------------------------------------------\n")
