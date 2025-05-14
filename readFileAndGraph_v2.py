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
# OPZIONE 1: Se la cartella "ruggero" (root del repository) è una sottodirectory di dove si trova questo script.
# Esempio: SCRIPT_DIR = /home/utente/progetti/, REPO_ROOT_DIR = /home/utente/progetti/ruggero/
# REPO_ROOT_DIR = os.path.join(SCRIPT_DIR, "ruggero") # Commentare questa riga se si usa l'Opzione 2 o se lo script è nella root del repo.
#
# OPZIONE 2: Specifica un percorso assoluto.
# Se usi questa opzione, decommenta e modifica la riga seguente, e commenta quella dell'OPZIONE 1.
# Esempio Windows: REPO_ROOT_DIR = r"C:\Utenti\TuoNome\Documenti\ruggero"
# Esempio Linux:   REPO_ROOT_DIR = "/home/tuoutente/ruggero"
REPO_ROOT_DIR = r"C:\Users\Carlo\Documents\DEV\Rpi\Server raccolta dati misurazione acqua\ruggero" # Assicurati che questa sia la riga attiva e corretta.

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

# HTML_OUTPUT_PATH è dove verrà salvato index.html (solo se non ci sono dati per il mese corrente)
HTML_OUTPUT_PATH = os.path.join(REPO_ROOT_DIR, "index.html")

# Definizioni dei percorsi per i file di log (relativi a SCRIPT_DIR)
# Se SCRIPT_DIR è già dentro REPO_ROOT_DIR, e i log sono fuori da REPO_ROOT_DIR,
# allora SCRIPT_DIR deve essere il percorso dello script, non REPO_ROOT_DIR.
# Se lo script readFileAndGraph_v2.py è in '.../ruggero/', e i log sono in '.../ruggero/logs/',
# allora LOG_DIRECTORY = os.path.join(SCRIPT_DIR, 'logs') è corretto.
# Se i log sono in una cartella 'logs' parallela a 'ruggero', es:
# Server raccolta dati misurazione acqua/
#   ruggero/ (contiene readFileAndGraph_v2.py)
#   logs/
# Allora SCRIPT_DIR punterebbe a '.../ruggero/', e per accedere a '.../logs/' dovresti fare:
# PARENT_OF_SCRIPT_DIR = os.path.dirname(SCRIPT_DIR)
# LOG_DIRECTORY = os.path.join(PARENT_OF_SCRIPT_DIR, 'logs')
# Per ora, assumo che 'logs' sia una sottocartella di dove si trova lo script.
LOG_DIRECTORY = os.path.join(os.path.dirname(SCRIPT_DIR), 'logs') # Assumendo che 'logs' sia parallelo a 'ruggero'
if not os.path.isdir(LOG_DIRECTORY): # Fallback se 'logs' è dentro la cartella dello script
    LOG_DIRECTORY = os.path.join(SCRIPT_DIR, 'logs')


MEASUREMENT_LOG_FILE_PATH = os.path.join(LOG_DIRECTORY, 'measurements.log') # Log delle misurazioni corrente
SCRIPT_EVENT_LOG_FILE = os.path.join(LOG_DIRECTORY, 'graph_generator_events.log') # Log eventi di questo script
CLIENT_MAP_INI_FILE = os.path.join(os.path.dirname(SCRIPT_DIR), 'client_map.ini') # Assumendo parallelo a 'ruggero'
if not os.path.exists(CLIENT_MAP_INI_FILE): # Fallback
    CLIENT_MAP_INI_FILE = os.path.join(SCRIPT_DIR, 'client_map.ini')


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
                else: 
                    logger.warning(f"File {SCRIPT_EVENT_LOG_FILE} (atteso per {prev_year:04d}-{prev_month:02d}) non trovato per l'archiviazione.")
            
            elif os.path.exists(SCRIPT_EVENT_LOG_FILE): 
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
        
        if not repo.index.diff(repo.head.commit) and not repo.is_dirty(untracked_files=True): 
            logger.info("Nessuna modifica rilevata nei file HTML da committare rispetto all'ultimo commit.")
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
    # Verifica e crea LOG_DIRECTORY se non esiste
    # Questa directory è relativa a SCRIPT_DIR, non REPO_ROOT_DIR
    actual_log_dir_path = LOG_DIRECTORY # Usiamo la variabile globale già calcolata
    if not os.path.exists(actual_log_dir_path):
        try:
            os.makedirs(actual_log_dir_path)
            print(f"Directory di log creata: {actual_log_dir_path}")
        except OSError as e:
            print(f"ATTENZIONE: Impossibile creare la directory di log {actual_log_dir_path}: {e}. Il logging su file sarà disabilitato.")
            logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
            return False
            
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(module)s - %(message)s')
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    logger.propagate = False
    return True

def load_client_name_map(ini_file_path):
    """Carica la mappatura IP -> Nome Cliente da un file .ini."""
    config = configparser.ConfigParser()
    loaded_map = {}
    try:
        if not os.path.exists(ini_file_path):
            logger.warning(f"File di mappatura client '{ini_file_path}' non trovato. Verranno usati gli IP come nomi.")
            return loaded_map

        config.read(ini_file_path, encoding='utf-8') 
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
                y[i] + 50, 
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
        with open(log_file_path, 'r', encoding='utf-8') as fo: 
            for line_num, rec in enumerate(fo, 1):
                rec = rec.strip()
                if not rec:
                    continue
                
                parts = rec.split()
                if len(parts) >= 4: 
                    try:
                        date_str = parts[0]
                        time_str = parts[1]
                        level_str = parts[2]
                        
                        client_info_full = " ".join(parts[3:])
                        if client_info_full.startswith("(Client: ") and client_info_full.endswith(")"):
                            client_id_raw = client_info_full[len("(Client: "):-1]
                            client_ip = client_id_raw.split(':')[0] 
                            client_id = client_name_map.get(client_ip, client_ip) 

                            datetime_str = f"{date_str} {time_str}"
                            try:
                                log_datetime = datetime.datetime.strptime(datetime_str, "%d/%m/%Y %H:%M")
                            except ValueError:
                                logger.warning(f"Riga {line_num}: Formato data/ora non valido '{datetime_str}' in '{log_file_path}'. Riga saltata: {rec}")
                                continue

                            if log_datetime.month != current_month or log_datetime.year != current_year:
                                continue 

                            try:
                                level = float(level_str)
                            except ValueError:
                                logger.warning(f"Riga {line_num}: Valore livello non valido '{level_str}' in '{log_file_path}'. Riga saltata: {rec}")
                                continue

                            day_of_month = log_datetime.day
                            if client_id not in raw_data_by_client_day:
                                raw_data_by_client_day[client_id] = {}
                            
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

    processed_data = {}
    for client_id, daily_data in raw_data_by_client_day.items():
        if not daily_data:
            continue
        
        sorted_days = sorted(daily_data.keys())
        days_list = []
        values_list = []
        for day in sorted_days:
            days_list.append(day)
            values_list.append(daily_data[day][1]) 
            
        processed_data[client_id] = {"days": days_list, "values": values_list}
    
    if not processed_data and os.path.exists(log_file_path):
        logger.info(f"Nessun dato valido trovato per il mese {current_month}/{current_year} nel file '{log_file_path}', o il file era vuoto/conteneva solo dati non pertinenti.")
    elif processed_data:
        logger.info(f"Dati parsati con successo da '{log_file_path}' per {current_month}/{current_year}.")

    return processed_data

def create_and_save_graph(data_input, page_main_title, year, output_html_path, is_main_index_page=False, is_archive_file=False):
    """
    Crea grafici a barre e li salva come file HTML interattivo.
    Se is_main_index_page è True, data_input contiene dati per tutti i client del mese corrente
    e genera un grafico per client all'interno di output_html_path (index.html).
    Altrimenti (per archivi), data_input contiene dati per un singolo client.

    data_input: Dati dei client.
    page_main_title: Titolo principale della pagina HTML (es. "Novembre 2023").
    is_archive_file: Boolean, True se è un grafico di un mese archiviato.
    is_main_index_page: Boolean, True se si sta generando la pagina index.html principale.
    """
    html_body_content = ""

    if not data_input:
        logger.warning(f"Nessun dato fornito per generare grafici per: {page_main_title} in {output_html_path}.")
        html_body_content = f"<p>Nessun dato disponibile per {page_main_title}.</p>"
    else:
        clients_to_graph = data_input.items()

        for client_id, client_specific_data in clients_to_graph:
            if not client_specific_data or not client_specific_data.get("days"):
                logger.info(f"Nessun giorno con dati per il client '{client_id}' per {page_main_title}. Grafico per questo client saltato.")
                if is_main_index_page:
                    html_body_content += f"<h2>Consumi {client_id}</h2><p>Nessun dato disponibile per questo client nel periodo.</p>"
                else: # Caso archivio singolo client senza dati (non dovrebbe succedere se filtrato prima)
                    html_body_content = f"<p>Nessun dato disponibile per {client_id} nel periodo {page_main_title}.</p>"
                continue

            fig, ax = plt.subplots(figsize=(20, 10))
            all_days_sorted = sorted(list(set(client_specific_data["days"])))
            
            day_to_x_index = {day: i for i, day in enumerate(all_days_sorted)}
            num_days_with_data = len(all_days_sorted)
            bar_width = 0.8 
            
            values_for_plotting = np.zeros(num_days_with_data)
            for day_idx, day_val in enumerate(client_specific_data["days"]):
                if day_val in day_to_x_index:
                     plot_idx = day_to_x_index[day_val]
                     values_for_plotting[plot_idx] = client_specific_data["values"][day_idx]
            
            x_positions = np.arange(num_days_with_data)
            
            bars = ax.bar(x_positions, values_for_plotting, width=bar_width, label=client_id, color='skyblue')
            addlabels(ax, x_positions, values_for_plotting, bar_width)

            ax.set_xlabel('Giorno del mese', fontsize=18, fontweight='bold', color='blue')
            ax.set_ylabel('Litri (L)', fontsize=18, fontweight='bold', color='blue')
            
            # Titolo del singolo grafico
            graph_specific_title = f"{page_main_title} (Client: {client_id})" if is_main_index_page else page_main_title
            ax.set_title(f'Consumi Acqua - {graph_specific_title}', fontsize=22, fontweight='bold', color='green')
            
            ax.set_xticks(np.arange(num_days_with_data))
            ax.set_xticklabels([str(d) for d in all_days_sorted], rotation=45, ha="right", fontsize=14)
            # Imposta il limite massimo dell'asse Y a 400 e il minimo a 0
            ax.set_ylim(bottom=0, top=400)
            ax.tick_params(axis='y', labelsize=14)
            
            ax.legend(fontsize=12)
            ax.grid(True, linestyle='--', alpha=0.7)
            plt.tight_layout()

            html_fig_for_client = mpld3.fig_to_html(fig)
            plt.close(fig)

            if is_main_index_page:
                html_body_content += f"<h2>Consumi {client_id}</h2>\n{html_fig_for_client}\n<hr/>\n"
            else: # Pagina di archivio per singolo client
                html_body_content = html_fig_for_client
                break # Per i file di archivio, c'è un solo client per file

        if not html_body_content and is_main_index_page: # Se nessun client aveva dati graficabili
            html_body_content = f"<p>Nessun dato graficabile disponibile per i client nel periodo {page_main_title}.</p>"


    # Costruzione HTML finale
    html_content = f"<html><head><title>Grafico Consumi {page_main_title}</title></head>\n"
    html_content += f"<body><h1>Grafico Consumi Acqua - {page_main_title}</h1>\n"
    html_content += html_body_content

    # Aggiungi link ad altri grafici e archivi
    html_content += "<h2>Altri Grafici e Archivi</h2><ul>\n"
    other_linkable_files = []
    if os.path.exists(REPO_ROOT_DIR):
        all_repo_html_files = sorted(
            [f for f in os.listdir(REPO_ROOT_DIR) if f.endswith(".html") and os.path.join(REPO_ROOT_DIR, f) != output_html_path],
            reverse=True
        )

        if is_main_index_page: # index.html linka solo agli archivi effettivi
            other_linkable_files = [f for f in all_repo_html_files if f.startswith("grafico_") and not f == os.path.basename(HTML_OUTPUT_PATH)]
        else:
            # Le pagine di archivio linkano a index.html e ad altri archivi
            other_linkable_files = all_repo_html_files
            if os.path.exists(HTML_OUTPUT_PATH) and os.path.basename(HTML_OUTPUT_PATH) not in other_linkable_files and HTML_OUTPUT_PATH != output_html_path :
                other_linkable_files.insert(0, os.path.basename(HTML_OUTPUT_PATH)) # Metti index.html per primo se non è già lì

    if not other_linkable_files:
         html_content += "<li>Nessun altro grafico o archivio disponibile.</li>"

    for i, other_file_name in enumerate(other_linkable_files):
        if i < 24: 
             link_display_name = other_file_name.replace(".html", "").replace("grafico_", "").replace("_", " ")
             if other_file_name == "index.html":
                 link_display_name = "Grafici Mese Corrente (index.html)"
             else:
                match_link = re.match(r"grafico_(\d{4}-\d{2})_(.+)", other_file_name.replace(".html",""))
                if match_link:
                    period, client_part = match_link.groups()
                    link_display_name = f"{period} (Client: {client_part})"
             html_content += f'<li><a href="{other_file_name}">{link_display_name}</a></li>'
        else:
            if i == 24: html_content += "<li>... (altri grafici disponibili nella cartella del repository)</li>"
            break
    html_content += "</ul>\n"
        
    html_content += f"<p><em>Ultimo aggiornamento: {datetime.datetime.now().strftime('%d-%m-%Y %H:%M:%S')}</em></p>\n"
    html_content += "</body></html>\n"

    try:
        with open(output_html_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        logger.info(f"Grafico HTML salvato in '{output_html_path}'")
    except IOError as e:
        logger.error(f"Impossibile scrivere il file HTML '{output_html_path}': {e}")

def process_archived_logs():
    """Processa i file di log archiviati (es. measurements.log.ANNO-MESE)."""
    archived_files_generated = []
    # Assicurati che LOG_DIRECTORY esista prima di listdir
    if not os.path.exists(LOG_DIRECTORY):
        logger.error(f"La directory dei log '{LOG_DIRECTORY}' non esiste. Impossibile processare gli archivi.")
        return archived_files_generated
        
    log_files = [f for f in os.listdir(LOG_DIRECTORY) if f.startswith("measurements.log.")]
    
    for log_file_name in log_files:
        match = re.match(r"measurements\.log\.(\d{4})-(\d{2})", log_file_name)
        if match:
            log_year, log_month = int(match.group(1)), int(match.group(2))
            log_path = os.path.join(LOG_DIRECTORY, log_file_name)
            
            mese_str_archivio = mese(log_month)
            logger.info(f"Processando dati archiviati per {mese_str_archivio} {log_year} da {log_path}")
            
            archived_month_data_all_clients = read_and_parse_log_file(log_path, log_month, log_year)
            
            if archived_month_data_all_clients:
                for client_id, client_specific_data in archived_month_data_all_clients.items():
                    if not client_specific_data.get("days"): # Salta se il client non ha giorni con dati
                        logger.info(f"Nessun giorno con dati per il client '{client_id}' nell'archivio {log_file_name}.")
                        continue

                    data_for_graph = {client_id: client_specific_data}
                    safe_client_id = re.sub(r'[^\w\-\.]', '_', client_id) 
                    
                    archive_html_filename = f"grafico_{log_year}-{log_month:02d}_{safe_client_id}.html"
                    archive_html_filepath = os.path.join(REPO_ROOT_DIR, archive_html_filename)                    
                    archive_page_title = f"{mese_str_archivio} {log_year} (Client: {client_id})"
                    
                    create_and_save_graph(
                        data_for_graph,
                        archive_page_title, # Questo sarà il titolo del grafico e della pagina
                        log_year,
                        archive_html_filepath,
                        is_main_index_page=False, # Non è la pagina index principale
                        is_archive_file=True      # È un file di archivio
                    )
                    archived_files_generated.append(archive_html_filepath)
            else:
                logger.info(f"Nessun dato da processare per l'archivio {log_file_name}.")
    return archived_files_generated

if __name__ == "__main__":
    if not setup_logging():
        sys.exit("Avvio fallito a causa di errori di configurazione del logging.")

    manage_script_event_log_rotation()

    logger.info("Avvio script generazione grafico...")
    now_timestamp_for_commit = datetime.datetime.now() 
    
    current_month_num = now_timestamp_for_commit.month
    current_year_num = now_timestamp_for_commit.year
    current_month_name = mese(current_month_num)

    client_name_map = load_client_name_map(CLIENT_MAP_INI_FILE)

    logger.info(f"Lettura dati per il mese corrente: {current_month_name} {current_year_num} da {MEASUREMENT_LOG_FILE_PATH}")
    current_month_data_all_clients = read_and_parse_log_file(MEASUREMENT_LOG_FILE_PATH, current_month_num, current_year_num)
    
    # Genera sempre index.html per il mese corrente
    # Conterrà grafici per ogni client se ci sono dati, o un messaggio "Nessun dato"
    logger.info(f"Generazione di {HTML_OUTPUT_PATH} per il mese corrente: {current_month_name} {current_year_num}")
    create_and_save_graph(
        current_month_data_all_clients, # Passa tutti i dati dei client
        f"{current_month_name} {current_year_num}", # Titolo principale della pagina
        current_year_num,
        HTML_OUTPUT_PATH, # Salva come index.html
        is_main_index_page=True, # Indica che è la pagina index principale
        is_archive_file=False    # Non è un file di archivio
    )
    generated_html_files_for_git = []
    if os.path.exists(HTML_OUTPUT_PATH): # Aggiungi index.html se è stato creato
        generated_html_files_for_git.append(HTML_OUTPUT_PATH)
            
    logger.info("Inizio processamento log archiviati...")
    archived_htmls = process_archived_logs()
    generated_html_files_for_git.extend(archived_htmls)
    logger.info(f"File HTML archiviati generati: {archived_htmls}")
    if generated_html_files_for_git:
        existing_generated_files = [f for f in generated_html_files_for_git if os.path.exists(f)]
        if existing_generated_files:
            logger.info(f"Tentativo di push per i seguenti file: {existing_generated_files}")
            #git_push(existing_generated_files) 
        else:
            logger.info("Nessun file HTML (corrente o archiviato) è stato effettivamente generato o trovato, push saltato.")
    else:
        logger.info("Nessun file HTML generato, push saltato.")

    logger.info("Script generazione grafico completato.")
