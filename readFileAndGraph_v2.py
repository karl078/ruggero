#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patheffects as path_effects
import mpld3
import numpy as np
import time
import datetime
import calendar
from mese import mese
from git import Repo
import logging
from logging.handlers import TimedRotatingFileHandler
import configparser # Importa configparser
import re # Importa il modulo per le espressioni regolari
import os # Aggiunto import per os
import threading # Aggiunto per il lock nella rotazione dei log
import sys # Importato per sys.exit in caso di configurazione errata

# Ottiene il percorso assoluto della directory in cui si trova lo script
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# !!! CONFIGURAZIONE UTENTE RICHIESTA !!!
# Specifica il percorso della directory radice del tuo repository Git clonato (la cartella "ruggero").
#
# OPZIONE 1 (Default): La cartella "ruggero" è una sottodirectory di dove si trova questo script.
REPO_ROOT_DIR = os.path.join(SCRIPT_DIR, "ruggero")
#
# OPZIONE 2: Specifica un percorso assoluto.
# Se usi questa opzione, decommenta e modifica la riga seguente, e commenta quella dell'OPZIONE 1.
# Esempio Windows: REPO_ROOT_DIR = r"C:\Utenti\TuoNome\Documenti\ruggero"
# Esempio Linux:   REPO_ROOT_DIR = "/home/tuoutente/ruggero"
# REPO_ROOT_DIR = r"PERCORSO_ASSOLUTO_ALLA_TUA_CARTELLA_RUGGERO" # <--- MODIFICA QUI SE USI OPZIONE 2

# Verifica se la directory del repository esiste
if not os.path.isdir(REPO_ROOT_DIR):
    error_message = (
        f"ERRORE CRITICO: La directory del repository 'REPO_ROOT_DIR' non esiste o non è una directory.\n"
        f"Percorso configurato: '{REPO_ROOT_DIR}'\n"
        f"Verifica la configurazione di REPO_ROOT_DIR in {os.path.basename(__file__)} e assicurati che la cartella esista."
    )
    print(error_message, file=sys.stderr)
    sys.exit(1) # Esce con un codice di errore

# Global Configuration
# PATH_OF_GIT_REPO punta alla directory .git, all'interno di REPO_ROOT_DIR
PATH_OF_GIT_REPO = os.path.join(REPO_ROOT_DIR, '.git')

# HTML_OUTPUT_PATH è dove verrà salvato index.html, all'interno di REPO_ROOT_DIR
HTML_OUTPUT_PATH = os.path.join(REPO_ROOT_DIR, "index.html")

# Definizioni dei percorsi per i file di log (relativi a SCRIPT_DIR)
LOG_DIRECTORY = os.path.join(SCRIPT_DIR, 'logs')
MEASUREMENT_LOG_FILE_PATH = os.path.join(LOG_DIRECTORY, 'measurements.log') # Log delle misurazioni corrente
SCRIPT_EVENT_LOG_FILE = os.path.join(LOG_DIRECTORY, 'graph_generator_events.log') # Log eventi di questo script
CLIENT_MAP_INI_FILE = os.path.join(SCRIPT_DIR, 'client_map.ini') # Percorso del file .ini per mappatura IP->Nome

# Logger per questo script
logger = logging.getLogger(__name__)

# Variabili globali per la gestione della rotazione del log degli eventi dello script
script_event_file_handler = None
current_script_event_log_year_month = None # Tupla (year, month)
script_event_log_rotation_lock = threading.Lock()

# Dizionario per la mappatura IP -> Nome Cliente
client_name_map = {}

# Variabile globale per il timestamp del commit, impostata nel main
now_timestamp_for_commit = None


def _setup_script_event_handler_for_month(year, month):
    """
    Crea, configura e aggiunge un FileHandler a `logger` per il mese specificato.
    Imposta script_event_file_handler e current_script_event_log_year_month.
    Assume che eventuali vecchi handler siano già stati rimossi e chiusi.
    """
    global script_event_file_handler, current_script_event_log_year_month, logger

    if script_event_file_handler: # Salvaguardia
        logger.warning(f"_setup_script_event_handler_for_month chiamato con un handler esistente per {current_script_event_log_year_month}. Verrà sostituito.")
        logger.removeHandler(script_event_file_handler)
        script_event_file_handler.close()

    # Usa lo stesso formatter definito in setup_logging per coerenza
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(module)s - %(message)s')
    new_handler = logging.FileHandler(SCRIPT_EVENT_LOG_FILE, mode='a', encoding='utf-8') # 'a' per appendere
    new_handler.setFormatter(formatter)
    
    logger.addHandler(new_handler)
    script_event_file_handler = new_handler
    current_script_event_log_year_month = (year, month)
    # Logga questo evento importante. Poiché l'handler potrebbe essere appena stato aggiunto,
    # questo messaggio andrà al nuovo file e alla console (se configurata).
    logger.info(f"Handler per {SCRIPT_EVENT_LOG_FILE} configurato per il mese {year:04d}-{month:02d}.")

def manage_script_event_log_rotation():
    """
    Gestisce la rotazione del file di log degli eventi dello script (graph_generator_events.log).
    Se è iniziato un nuovo mese, archivia il vecchio log e ne inizia uno nuovo.
    Da chiamare all'avvio dello script.
    """
    global script_event_file_handler, current_script_event_log_year_month, logger, script_event_log_rotation_lock

    now_dt = datetime.datetime.now()
    target_year, target_month = now_dt.year, now_dt.month

    with script_event_log_rotation_lock:
        if current_script_event_log_year_month is None or current_script_event_log_year_month != (target_year, target_month):
            
            if current_script_event_log_year_month is not None: # Cambio di mese durante l'esecuzione (improbabile per script batch) o tra esecuzioni
                prev_year, prev_month = current_script_event_log_year_month
                # Logga l'intenzione di rotazione. Questo andrà al vecchio file di log se l'handler è ancora attivo,
                # o alla console se l'handler file è già stato rimosso/chiuso.
                logger.info(f"Rilevato cambio di mese per {SCRIPT_EVENT_LOG_FILE} da {prev_year:04d}-{prev_month:02d} a {target_year:04d}-{target_month:02d}. Inizio rotazione.")

                if script_event_file_handler:
                    logger.removeHandler(script_event_file_handler)
                    script_event_file_handler.close()
                    script_event_file_handler = None
                
                archive_log_filename = f"{SCRIPT_EVENT_LOG_FILE}.{prev_year:04d}-{prev_month:02d}"
                if os.path.exists(SCRIPT_EVENT_LOG_FILE):
                    try:
                        os.rename(SCRIPT_EVENT_LOG_FILE, archive_log_filename)
                        logger.info(f"File {SCRIPT_EVENT_LOG_FILE} archiviato come {archive_log_filename}.")
                    except OSError as e:
                        logger.error(f"Errore durante l'archiviazione di {SCRIPT_EVENT_LOG_FILE} a {archive_log_filename}: {e}")
                else: # Non dovrebbe accadere se l'handler era attivo
                    logger.warning(f"File {SCRIPT_EVENT_LOG_FILE} (atteso per {prev_year:04d}-{prev_month:02d}) non trovato per l'archiviazione.")
            
            elif os.path.exists(SCRIPT_EVENT_LOG_FILE): # Primo avvio e il file esiste (potrebbe essere del mese precedente)
                try:
                    mod_time = os.path.getmtime(SCRIPT_EVENT_LOG_FILE)
                    mod_dt = datetime.datetime.fromtimestamp(mod_time)
                    if (mod_dt.year, mod_dt.month) != (target_year, target_month):
                        archive_log_filename = f"{SCRIPT_EVENT_LOG_FILE}.{mod_dt.year:04d}-{mod_dt.month:02d}"
                        os.rename(SCRIPT_EVENT_LOG_FILE, archive_log_filename)
                        logger.info(f"File {SCRIPT_EVENT_LOG_FILE} esistente (del {mod_dt.year:04d}-{mod_dt.month:02d}) archiviato come {archive_log_filename} all'avvio.")
                except Exception as e:
                    logger.error(f"Errore durante la gestione di {SCRIPT_EVENT_LOG_FILE} esistente all'avvio: {e}")

            _setup_script_event_handler_for_month(target_year, target_month)

def git_push(files_to_add):
    """Aggiunge, committa e pusha i file specificati al repository Git."""
    try:
        repo = Repo(PATH_OF_GIT_REPO)
        
        existing_files_to_add = [f for f in files_to_add if os.path.exists(f)]
        if not existing_files_to_add:
            logger.info("Nessun file HTML nuovo o modificato da committare.")
            return

        repo.index.add(existing_files_to_add)
        
        # Controlla se ci sono modifiche da committare dopo l'add
        # repo.is_dirty() controlla la working directory, non l'index.
        # repo.index.diff("HEAD") controlla le modifiche nell'index rispetto all'ultimo commit.
        if not repo.index.diff(repo.head.commit) and not repo.is_dirty(untracked_files=True): # untracked_files=True per essere sicuri
            logger.info("Nessuna modifica rilevata nei file HTML da committare rispetto all'ultimo commit.")
            # Potrebbe esserci un commit vuoto se i file sono stati aggiunti ma erano identici a HEAD.
            # Per evitare commit vuoti, si potrebbe fare un diff prima dell'add, ma è più complesso.
            # La logica attuale committerà se l'add ha cambiato l'index.
            # Se l'add non ha cambiato nulla (file già tracciati e identici), il diff("HEAD") sarà vuoto.
            # Se i file sono nuovi, diff("HEAD") mostrerà cambiamenti.
            # Per una logica più precisa:
            # staged_changes = repo.index.diff(repo.head.commit)
            # working_dir_changes = repo.index.diff(None) # Modifiche non ancora staged
            # if not staged_changes and not working_dir_changes:
            #     logger.info("Nessuna modifica rilevata nei file HTML da committare.")
            #     return
            # La condizione originale `if not repo.index.diff("HEAD")` dopo `repo.index.add` è generalmente sufficiente.
            # `repo.is_dirty(untracked_files=False)` qui è ridondante se i file sono stati aggiunti.
            # Semplifichiamo: se dopo l'add, l'index è uguale a HEAD, non c'è nulla da committare.
            if not repo.index.diff(repo.head.commit):
                 logger.info("Nessuna modifica effettiva da committare dopo l'aggiunta dei file.")
                 return


        commit_time = now_timestamp_for_commit if now_timestamp_for_commit else datetime.datetime.now()
        commit_message = f'Aggiornamento misurazione acqua del {commit_time.strftime("%d-%m-%Y %H:%M")}'
        repo.index.commit(commit_message)
        origin = repo.remote(name='origin')
        origin.push()
        logger.info(f"File {existing_files_to_add} caricati su GITHUB PAGES!")
    except Exception as e:
        logger.exception(f'Errore durante il push del codice su GitHub Pages:')

def setup_logging():
    """Configura il logger per questo script."""
    if not os.path.exists(LOG_DIRECTORY):
        try:
            os.makedirs(LOG_DIRECTORY)
        except OSError as e:
            print(f"ATTENZIONE: Impossibile creare la directory di log {LOG_DIRECTORY}: {e}. Il logging su file sarà disabilitato.")
            logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
            return False

    logger.setLevel(logging.INFO)
    # logger.setLevel(logging.DEBUG) # Per debug più verboso

    # Rimosso TimedRotatingFileHandler. L'handler per il file SCRIPT_EVENT_LOG_FILE
    # verrà gestito da manage_script_event_log_rotation() e _setup_script_event_handler_for_month().

    # Handler per la console (mantiene i log visibili sulla console durante l'esecuzione)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(module)s - %(message)s')
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    logger.propagate = False
    # Il messaggio "Logging configurato" verrà ora loggato dopo che l'handler file è stato impostato da manage_script_event_log_rotation
    return True

def load_client_name_map(ini_file_path):
    """Carica la mappatura IP -> Nome Cliente da un file .ini."""
    config = configparser.ConfigParser()
    loaded_map = {}
    try:
        if not os.path.exists(ini_file_path):
            logger.warning(f"File di mappatura client '{ini_file_path}' non trovato. Verranno usati gli IP come nomi.")
            return loaded_map

        config.read(ini_file_path, encoding='utf-8') # Specifica encoding
        if 'ClientNames' in config:
            if config['ClientNames']:
                for ip, name in config['ClientNames'].items():
                    loaded_map[ip] = name
                    logger.debug(f"Mappato IP '{ip}' a Nome '{name}'")
                logger.info(f"Mappatura nomi client caricata da '{ini_file_path}'. {len(loaded_map)} voci trovate.")
            else:
                logger.warning(f"Sezione [ClientNames] trovata in '{ini_file_path}', ma è vuota.")
        else:
            logger.warning(f"Sezione [ClientNames] non trovata nel file '{ini_file_path}'.")
    except configparser.Error as e:
        logger.error(f"Errore durante la lettura del file di mappatura client '{ini_file_path}': {e}")
    return loaded_map

def addlabels(ax, x, y, width):
    """Aggiunge etichette di valore sopra ogni barra nel grafico."""
    for i in range(len(x)):
        ax.text(x[i] + width / 2,
                y[i] + 50, # Offset verticale per l'etichetta
                f"{y[i]:.0f}" if y[i] == int(y[i]) else f"{y[i]:.1f}",
                color='#FF0000',
                fontsize=20,
                fontweight='bold', 
                ha='center',
                va='bottom',
                rotation=90,
                path_effects=[path_effects.withStroke(linewidth=5, foreground='white')])
                        
def read_and_parse_log_file(log_file_path, current_month, current_year):
    """
    Legge un file di log delle misurazioni, esegue il parsing dei dati,
    filtra per mese/anno corrente e restituisce un dizionario di dati per client.
    Conserva l'ultima misurazione se ne esistono multiple per lo stesso client nello stesso giorno.
    Output: {client_id: {"days": [giorno1, giorno2,...], "values": [val1, val2,...]}}
    """
    raw_data_by_client_day = {} 

    if not os.path.exists(log_file_path):
        logger.warning(f"File di log '{log_file_path}' non trovato per mese {current_month}/{current_year}.")
        return {}

    try:
        with open(log_file_path, 'r', encoding='utf-8') as fo: # Specifica encoding
            for line_num, rec in enumerate(fo, 1):
                rec = rec.strip()
                if not rec:
                    continue
                
                parts = rec.split()
                # Formato atteso: GG/MM/AAAA    HH:MM    LIVELLO    (Client: IP)
                # o formato vecchio: GG/MM/AAAA    HH:MM    LIVELLO    (Client: IP:PORTA)
                
                if len(parts) >= 4: # Data, Ora, Livello, InfoClient (può essere >1 parte)
                    try:
                        date_str = parts[0]
                        time_str = parts[1]
                        level_str = parts[2]
                        
                        client_info_full = " ".join(parts[3:])
                        if client_info_full.startswith("(Client: ") and client_info_full.endswith(")"):
                            client_id_raw = client_info_full[len("(Client: "):-1]
                            client_ip = client_id_raw.split(':')[0] # Estrae solo l'IP
                            client_id = client_name_map.get(client_ip, client_ip) # Usa nome mappato o IP

                            datetime_str = f"{date_str} {time_str}"
                            try:
                                log_datetime = datetime.datetime.strptime(datetime_str, "%d/%m/%Y %H:%M")
                            except ValueError:
                                logger.warning(f"Riga {line_num}: Formato data/ora non valido '{datetime_str}' in '{log_file_path}'. Riga saltata: {rec}")
                                continue

                            if log_datetime.month != current_month or log_datetime.year != current_year:
                                continue # Salta dati non del mese/anno corrente

                            try:
                                level = float(level_str)
                            except ValueError:
                                logger.warning(f"Riga {line_num}: Valore livello non valido '{level_str}' in '{log_file_path}'. Riga saltata: {rec}")
                                continue

                            day_of_month = log_datetime.day
                            if client_id not in raw_data_by_client_day:
                                raw_data_by_client_day[client_id] = {}
                            
                            # Conserva solo l'ultima misurazione per un dato giorno
                            if day_of_month not in raw_data_by_client_day[client_id] or \
                               log_datetime > raw_data_by_client_day[client_id][day_of_month][0]:
                                raw_data_by_client_day[client_id][day_of_month] = (log_datetime, level)
                        else:
                            logger.warning(f"Riga {line_num}: Formato info client non riconosciuto '{client_info_full}' in '{log_file_path}'. Riga saltata: {rec}")
                    except IndexError:
                        logger.warning(f"Riga {line_num}: Formato riga non valido (parti insufficienti) in '{log_file_path}'. Riga saltata: {rec}")
                    except Exception as e:
                        logger.exception(f"Riga {line_num}: Errore imprevisto durante il parsing della riga '{rec}' in '{log_file_path}':")
                else:
                    logger.warning(f"Riga {line_num}: Formato riga non valido (parti insufficienti) in '{log_file_path}'. Riga saltata: {rec}")
    
    except FileNotFoundError:
        logger.error(f"File di log '{log_file_path}' non trovato durante il tentativo di apertura.")
        return {}
    except IOError as e:
        logger.error(f"Errore IO durante la lettura del file '{log_file_path}': {e}")
        return {}
    except Exception as e:
        logger.exception(f"Errore imprevisto durante l'elaborazione del file '{log_file_path}':")
        return {}

    # Trasforma i dati grezzi nel formato finale richiesto
    processed_data = {}
    for client_id, daily_data in raw_data_by_client_day.items():
        if not daily_data:
            continue
        
        sorted_days = sorted(daily_data.keys())
        days_list = []
        values_list = []
        for day in sorted_days:
            days_list.append(day)
            values_list.append(daily_data[day][1]) # [1] è il livello
            
        processed_data[client_id] = {"days": days_list, "values": values_list}
    
    if not processed_data and os.path.exists(log_file_path):
        logger.info(f"Nessun dato valido trovato per il mese {current_month}/{current_year} nel file '{log_file_path}', o il file era vuoto/conteneva solo dati non pertinenti.")
    elif processed_data:
        logger.info(f"Dati parsati con successo da '{log_file_path}' per {current_month}/{current_year}.")

    return processed_data

def create_and_save_graph(data_by_client, month_name, year, output_html_path, is_archive=False):
    """Crea un grafico a barre e lo salva come file HTML interattivo."""
    if not data_by_client:
        logger.warning(f"Nessun dato fornito per generare il grafico per {month_name} {year}.")
        # Crea un file HTML vuoto o con un messaggio
        html_content = f"<html><head><title>Grafico Consumi {month_name} {year}</title></head>"
        html_content += f"<body><h1>Grafico Consumi Acqua - {month_name} {year}</h1>"
        html_content += f"<p>Nessun dato disponibile per {month_name} {year}.</p>"
        if not is_archive: # Link agli archivi solo nella pagina principale
            html_content += "<h2>Archivi Mensili</h2><ul>"
            archive_files = sorted([f for f in os.listdir(REPO_ROOT_DIR) if f.startswith("grafico_") and f.endswith(".html")], reverse=True)
            for i, archive_file in enumerate(archive_files):
                if i < 12: # Mostra solo gli ultimi 12 archivi per brevità
                     archive_name = archive_file.replace("grafico_", "").replace(".html", "")
                     html_content += f'<li><a href="{archive_file}">{archive_name}</a></li>'
                else:
                    if i == 12: html_content += "<li>... (altri archivi disponibili nella cartella)</li>"
            html_content += "</ul>"
        html_content += "</body></html>"
        try:
            with open(output_html_path, 'w', encoding='utf-8') as f:
                f.write(html_content)
            logger.info(f"File HTML '{output_html_path}' creato con messaggio 'Nessun dato'.")
        except IOError as e:
            logger.error(f"Impossibile scrivere il file HTML '{output_html_path}': {e}")
        return

    num_clients = len(data_by_client)
    if num_clients == 0:
        logger.info(f"Nessun client con dati per {month_name} {year}, grafico non generato.")
        return # Stessa logica di sopra, ma già gestita dal check precedente

    fig, ax = plt.subplots(figsize=(20, 10)) # Dimensioni del grafico
    
    # Determina tutti i giorni unici presenti nei dati per l'asse X
    all_days_set = set()
    for client_id in data_by_client:
        all_days_set.update(data_by_client[client_id]["days"])
    
    if not all_days_set:
        logger.warning(f"Nessun giorno con dati trovato per {month_name} {year} nonostante ci fossero client.")
        # Richiama la logica per HTML vuoto
        create_and_save_graph({}, month_name, year, output_html_path, is_archive)
        return

    all_days_sorted = sorted(list(all_days_set))
    
    # Mappatura giorno -> indice per l'asse X
    day_to_x_index = {day: i for i, day in enumerate(all_days_sorted)}
    
    num_days_in_month = len(all_days_sorted)
    bar_width = 0.8 / num_clients # Larghezza barre dinamica
    
    client_colors = plt.cm.get_cmap('tab10', num_clients) # Colormap per i client

    for i, client_id in enumerate(data_by_client.keys()):
        client_data = data_by_client[client_id]
        
        # Crea un array di valori allineato con all_days_sorted, con 0 per i giorni mancanti
        values_for_plotting = np.zeros(num_days_in_month)
        for day_idx, day_val in enumerate(client_data["days"]):
            if day_val in day_to_x_index: # Assicura che il giorno sia tra quelli da plottare
                 plot_idx = day_to_x_index[day_val]
                 values_for_plotting[plot_idx] = client_data["values"][day_idx]
        
        # Calcola la posizione x per le barre di questo client
        x_positions = np.arange(num_days_in_month) + (i - (num_clients - 1) / 2) * bar_width
        
        bars = ax.bar(x_positions, values_for_plotting, width=bar_width, label=client_id, color=client_colors(i))
        addlabels(ax, x_positions, values_for_plotting, bar_width)

    ax.set_xlabel('Giorno del mese', fontsize=18, fontweight='bold', color='blue')
    ax.set_ylabel('Litri (L)', fontsize=18, fontweight='bold', color='blue')
    ax.set_title(f'Consumi Acqua - {month_name} {year}', fontsize=22, fontweight='bold', color='green')
    
    ax.set_xticks(np.arange(num_days_in_month))
    ax.set_xticklabels([str(d) for d in all_days_sorted], rotation=45, ha="right", fontsize=14)
    ax.tick_params(axis='y', labelsize=14)
    
    ax.legend(fontsize=12)
    ax.grid(True, linestyle='--', alpha=0.7)
    plt.tight_layout() # Aggiusta layout per evitare sovrapposizioni

    # Conversione in HTML con mpld3
    html_fig = mpld3.fig_to_html(fig)
    plt.close(fig) # Chiudi la figura per liberare memoria

    # Costruisci l'HTML completo
    html_content = f"<html><head><title>Grafico Consumi {month_name} {year}</title></head>"
    html_content += f"<body><h1>Grafico Consumi Acqua - {month_name} {year}</h1>"
    html_content += html_fig
    
    if not is_archive: # Aggiungi link agli archivi solo nella pagina principale (index.html)
        html_content += "<h2>Archivi Mensili</h2><ul>"
        # Trova i file di archivio nella REPO_ROOT_DIR
        archive_files = sorted(
            [f for f in os.listdir(REPO_ROOT_DIR) if f.startswith("grafico_") and f.endswith(".html")],
            reverse=True # Ordine decrescente (più recenti prima)
        )
        for i, archive_file in enumerate(archive_files):
            if i < 12: # Mostra solo gli ultimi N archivi per brevità
                 archive_name = archive_file.replace("grafico_", "").replace(".html", "") # Es. ANNO-MESE
                 html_content += f'<li><a href="{archive_file}">{archive_name}</a></li>'
            else:
                if i == 12: html_content += "<li>... (altri archivi disponibili nella cartella del repository)</li>"
        html_content += "</ul>"
        
    html_content += f"<p><em>Ultimo aggiornamento: {datetime.datetime.now().strftime('%d-%m-%Y %H:%M:%S')}</em></p>"
    html_content += "</body></html>"

    try:
        with open(output_html_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        logger.info(f"Grafico HTML salvato in '{output_html_path}'")
    except IOError as e:
        logger.error(f"Impossibile scrivere il file HTML '{output_html_path}': {e}")

def process_archived_logs():
    """Processa i file di log archiviati (es. measurements.log.ANNO-MESE)."""
    archived_files_generated = []
    log_files = [f for f in os.listdir(LOG_DIRECTORY) if f.startswith("measurements.log.")]
    
    for log_file_name in log_files:
        match = re.match(r"measurements\.log\.(\d{4})-(\d{2})", log_file_name)
        if match:
            log_year, log_month = int(match.group(1)), int(match.group(2))
            log_path = os.path.join(LOG_DIRECTORY, log_file_name)
            
            mese_str_archivio = mese(log_month)
            logger.info(f"Processando dati archiviati per {mese_str_archivio} {log_year} da {log_path}")
            
            archived_month_data = read_and_parse_log_file(log_path, log_month, log_year)
            
            if archived_month_data:
                archive_html_filename = f"grafico_{log_year}-{log_month:02d}.html"
                # Salva i file HTML degli archivi in REPO_ROOT_DIR
                archive_html_filepath = os.path.join(REPO_ROOT_DIR, archive_html_filename)
                create_and_save_graph(archived_month_data, mese_str_archivio, log_year, archive_html_filepath, is_archive=True)
                archived_files_generated.append(archive_html_filepath)
            else:
                logger.info(f"Nessun dato da processare per l'archivio {log_file_name}.")
    return archived_files_generated

if __name__ == "__main__":
    if not setup_logging():
        sys.exit("Avvio fallito a causa di errori di configurazione del logging.")

    # Gestisce la rotazione del log degli eventi dello script all'avvio.
    # Questo imposterà anche l'handler file per il logger.
    manage_script_event_log_rotation()

    logger.info("Avvio script generazione grafico...")
    now_timestamp_for_commit = datetime.datetime.now() # Imposta per il messaggio di commit
    
    current_month_num = now_timestamp_for_commit.month
    current_year_num = now_timestamp_for_commit.year
    current_month_name = mese(current_month_num)

    # Carica la mappatura IP -> Nome Cliente
    client_name_map = load_client_name_map(CLIENT_MAP_INI_FILE)

    # Leggi e parsa il file di log corrente
    logger.info(f"Lettura dati per il mese corrente: {current_month_name} {current_year_num} da {MEASUREMENT_LOG_FILE_PATH}")
    current_month_data = read_and_parse_log_file(MEASUREMENT_LOG_FILE_PATH, current_month_num, current_year_num)

    # Crea e salva il grafico per il mese corrente in HTML_OUTPUT_PATH (index.html)
    create_and_save_graph(current_month_data, current_month_name, current_year_num, HTML_OUTPUT_PATH, is_archive=False)
    
    # Lista dei file HTML generati da aggiungere a Git
    generated_html_files_for_git = [HTML_OUTPUT_PATH]

    # Processa i log archiviati e genera i relativi grafici HTML
    logger.info("Inizio processamento log archiviati...")
    archived_htmls = process_archived_logs()
    generated_html_files_for_git.extend(archived_htmls)
    logger.info(f"File HTML archiviati generati: {archived_htmls}")

    # Esegui git push se ci sono file generati
    if generated_html_files_for_git:
        # Filtra solo i file che esistono effettivamente prima di tentare il push
        existing_generated_files = [f for f in generated_html_files_for_git if os.path.exists(f)]
        if existing_generated_files:
            logger.info(f"Tentativo di push per i seguenti file: {existing_generated_files}")
            git_push(existing_generated_files) 
        else:
            logger.info("Nessun file HTML (corrente o archiviato) è stato effettivamente generato o trovato, push saltato.")
    else:
        logger.info("Nessun file HTML generato, push saltato.")

    logger.info("Script generazione grafico completato.")
