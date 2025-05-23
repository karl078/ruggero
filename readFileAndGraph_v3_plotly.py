#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import plotly.express as px
import plotly.io as pio
import pandas as pd # Utile per Plotly Express

import datetime
import calendar
from mese import mese # Assumendo che mese.py sia accessibile
from git import Repo
import logging
# from logging.handlers import TimedRotatingFileHandler # Non più usato direttamente qui per SCRIPT_EVENT_LOG_FILE
import configparser
import re
import os
import threading
import sys

# Ottiene il percorso assoluto della directory in cui si trova lo script!
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# --- Caricamento Configurazione ---
CONFIG_FILE_PATH = os.path.join(SCRIPT_DIR, 'config.ini')
config = configparser.ConfigParser()

if not os.path.exists(CONFIG_FILE_PATH):
    print(f"ERRORE CRITICO: File di configurazione '{CONFIG_FILE_PATH}' non trovato.")
    sys.exit(1)

try:
    config.read(CONFIG_FILE_PATH)

    # Percorsi Repository
    repo_root_dir_windows_conf = config.get('Paths', 'repo_root_dir_windows', fallback=None)
    repo_root_dir_raspberry_conf = config.get('Paths', 'repo_root_dir_raspberry', fallback=None)

    if sys.platform.startswith('win'):
        REPO_ROOT_DIR = repo_root_dir_windows_conf
        if not REPO_ROOT_DIR:
            raise ValueError("Chiave 'repo_root_dir_windows' non trovata o vuota in config.ini")
        print(f"Rilevato ambiente Windows. REPO_ROOT_DIR impostato a: {REPO_ROOT_DIR}")
    elif sys.platform.startswith('linux'):
        REPO_ROOT_DIR = repo_root_dir_raspberry_conf
        if not REPO_ROOT_DIR:
            raise ValueError("Chiave 'repo_root_dir_raspberry' non trovata o vuota in config.ini")
        print(f"Rilevato ambiente Linux/Raspberry Pi. REPO_ROOT_DIR impostato a: {REPO_ROOT_DIR}")
    else:
        error_message = f"ERRORE CRITICO: Sistema operativo non supportato: {sys.platform}"
        print(error_message, file=sys.stderr)
        sys.exit(1)

    if not os.path.isdir(REPO_ROOT_DIR):
        raise ValueError(f"La directory del repository '{REPO_ROOT_DIR}' specificata in config.ini non esiste o non è una directory.")

    # Percorsi Log e Client Map
    log_dir_name_conf = config.get('Paths', 'log_directory_name', fallback='logs')
    client_map_filename_conf = config.get('Paths', 'client_map_filename', fallback='client_map.ini')

    PARENT_OF_SCRIPT_DIR = os.path.dirname(SCRIPT_DIR) # Directory che contiene la cartella dello script

    LOG_DIRECTORY_PRIMARY = os.path.join(PARENT_OF_SCRIPT_DIR, log_dir_name_conf)
    LOG_DIRECTORY_FALLBACK = os.path.join(SCRIPT_DIR, log_dir_name_conf)
    if os.path.isdir(LOG_DIRECTORY_PRIMARY):
        LOG_DIRECTORY = LOG_DIRECTORY_PRIMARY
    else:
        LOG_DIRECTORY = LOG_DIRECTORY_FALLBACK
        print(f"INFO: Percorso primario dei log non trovato ({LOG_DIRECTORY_PRIMARY}). Uso fallback: {LOG_DIRECTORY}")

    CLIENT_MAP_INI_FILE_PRIMARY = os.path.join(PARENT_OF_SCRIPT_DIR, client_map_filename_conf)
    CLIENT_MAP_INI_FILE_FALLBACK = os.path.join(SCRIPT_DIR, client_map_filename_conf)
    if os.path.exists(CLIENT_MAP_INI_FILE_PRIMARY):
        CLIENT_MAP_INI_FILE = CLIENT_MAP_INI_FILE_PRIMARY
    else:
        CLIENT_MAP_INI_FILE = CLIENT_MAP_INI_FILE_FALLBACK
        print(f"INFO: File client_map.ini primario non trovato ({CLIENT_MAP_INI_FILE_PRIMARY}). Uso fallback: {CLIENT_MAP_INI_FILE}")

    # Percorsi Git e Output HTML
    git_repo_subdir_conf = config.get('Git', 'git_repo_subdir', fallback='.git')
    html_output_filename_conf = config.get('Output', 'html_output_filename', fallback='index.html')
    archive_subdir_name_conf = config.get('Output', 'archive_subdir_name', fallback='archivio')

    PATH_OF_GIT_REPO = os.path.join(REPO_ROOT_DIR, git_repo_subdir_conf)
    HTML_OUTPUT_PATH = os.path.join(REPO_ROOT_DIR, html_output_filename_conf)

    MEASUREMENT_LOG_FILE_PATH = os.path.join(LOG_DIRECTORY, 'measurements.log')
    SCRIPT_EVENT_LOG_FILE = os.path.join(LOG_DIRECTORY, f'graph_generator_events_plotly.log')

    ARCHIVE_DIR_PATH = os.path.join(REPO_ROOT_DIR, archive_subdir_name_conf)
except (configparser.Error, ValueError) as e:
    print(f"ERRORE CRITICO durante la lettura del file di configurazione '{CONFIG_FILE_PATH}': {e}")
    sys.exit(1)


logger = logging.getLogger(__name__)
script_event_file_handler = None
current_script_event_log_year_month = None
script_event_log_rotation_lock = threading.Lock()
client_name_map = {}
now_timestamp_for_commit = None

# --- Funzioni di logging e gestione file (invariate da v2, tranne nome SCRIPT_EVENT_LOG_FILE) ---
def _setup_script_event_handler_for_month(year, month):
    global script_event_file_handler, current_script_event_log_year_month, logger
    if script_event_file_handler:
        logger.warning(f"_setup_script_event_handler_for_month chiamato con un handler esistente per {current_script_event_log_year_month}. Verrà sostituito.")
        logger.removeHandler(script_event_file_handler)
        script_event_file_handler.close()
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(module)s - %(message)s')
    new_handler = logging.FileHandler(SCRIPT_EVENT_LOG_FILE, mode='a', encoding='utf-8')
    new_handler.setFormatter(formatter)
    logger.addHandler(new_handler)
    script_event_file_handler = new_handler
    current_script_event_log_year_month = (year, month)
    logger.info(f"Handler per {SCRIPT_EVENT_LOG_FILE} configurato per il mese {year:04d}-{month:02d}.")

def manage_script_event_log_rotation():
    global script_event_file_handler, current_script_event_log_year_month, logger, script_event_log_rotation_lock
    now_dt = datetime.datetime.now()
    target_year, target_month = now_dt.year, now_dt.month
    with script_event_log_rotation_lock:
        if current_script_event_log_year_month is None or current_script_event_log_year_month != (target_year, target_month):
            if current_script_event_log_year_month is not None:
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

def setup_logging():
    actual_log_dir_path = LOG_DIRECTORY
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
                logger.info(f"Mappatura nomi client caricata da '{ini_file_path}'. {len(loaded_map)} voci trovate.")
            else:
                logger.warning(f"Sezione [ClientNames] trovata in '{ini_file_path}', ma è vuota.")
        else:
            logger.warning(f"Sezione [ClientNames] non trovata nel file '{ini_file_path}'.")
    except configparser.Error as e:
        logger.error(f"Errore durante la lettura del file di mappatura client '{ini_file_path}': {e}")
    return loaded_map

def read_and_parse_log_file(log_file_path, current_month, current_year):
    raw_data_by_client_day = {}
    if not os.path.exists(log_file_path):
        logger.warning(f"File di log '{log_file_path}' non trovato per mese {current_month}/{current_year}.")
        return {}
    try:
        with open(log_file_path, 'r', encoding='utf-8') as fo:
            for line_num, rec in enumerate(fo, 1):
                rec = rec.strip()
                if not rec: continue
                parts = rec.split()
                if len(parts) >= 4:
                    try:
                        date_str, time_str, level_str = parts[0], parts[1], parts[2]
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
    except Exception as e:
        logger.exception(f"Errore imprevisto durante l'elaborazione del file '{log_file_path}':")
        return {}
    processed_data = {}
    for client_id, daily_data in raw_data_by_client_day.items():
        if not daily_data: continue
        sorted_days = sorted(daily_data.keys())
        days_list = [day for day in sorted_days]
        values_list = [daily_data[day][1] for day in sorted_days]
        processed_data[client_id] = {"days": days_list, "values": values_list}
    if not processed_data and os.path.exists(log_file_path):
        logger.info(f"Nessun dato valido trovato per {current_month}/{current_year} in '{log_file_path}'.")
    elif processed_data:
        logger.info(f"Dati parsati con successo da '{log_file_path}' per {current_month}/{current_year}.")
    return processed_data

def git_push(files_to_add):
    try:
        repo = Repo(PATH_OF_GIT_REPO)
        existing_files_to_add = [f for f in files_to_add if os.path.exists(f)]
        if not existing_files_to_add:
            logger.info("Nessun file HTML nuovo o modificato da committare.")
            return
        repo.index.add(existing_files_to_add)
        if not repo.index.diff(repo.head.commit) and not repo.is_dirty(untracked_files=True):
            logger.info("Nessuna modifica rilevata nei file HTML da committare.")
            return
        commit_time = now_timestamp_for_commit if now_timestamp_for_commit else datetime.datetime.now()
        commit_message = f'Aggiornamento misurazione acqua del {commit_time.strftime("%d-%m-%Y %H:%M")}'
        repo.index.commit(commit_message)
        origin = repo.remote(name='origin')
        origin.push()
        logger.info(f"File {existing_files_to_add} caricati su GITHUB PAGES!")
    except Exception as e:
        logger.exception(f'Errore durante il push del codice su GitHub Pages:')

# --- Funzione di creazione grafico con Plotly ---
def create_and_save_graph_plotly(data_input, page_main_title, year, month_num, output_html_path, is_main_index_page=False, is_archive_file=False):
    html_body_content = ""
    plotly_js_included = False # Per includere Plotly.js solo una volta per pagina

    if not data_input:
        logger.warning(f"Nessun dato fornito per generare grafici Plotly per: {page_main_title} in {output_html_path}.")
        html_body_content = f"<p>Nessun dato disponibile per {page_main_title}.</p>"
    else:
        clients_to_graph = data_input.items()
        num_clients_with_data = 0

        for client_id, client_specific_data in clients_to_graph:
            if not client_specific_data or not client_specific_data.get("days"):
                logger.info(f"Nessun giorno con dati per il client '{client_id}' per {page_main_title}. Grafico Plotly per questo client saltato.")
                if is_main_index_page:
                    html_body_content += f"<h2>Livello acqua {client_id}</h2><p>Nessun dato disponibile per questo client nel periodo.</p><hr/>\n"
                # else: per file archivio singolo, questo caso è gestito da data_input vuoto
                continue
            
            num_clients_with_data += 1
            
            # Ottieni il numero di giorni nel mese
            num_days_in_month = calendar.monthrange(year, month_num)[1]
            all_days_in_month = list(range(1, num_days_in_month + 1))
            
            # Crea un dizionario Giorno -> Valore solo per i giorni con dati
            client_data_dict = dict(zip(client_specific_data["days"], client_specific_data["values"]))
            
            # Crea la lista di valori per tutti i giorni del mese (None per i giorni senza dati)
            df_client = pd.DataFrame({
                'Giorno': all_days_in_month,
                'Altezza acqua (cm)': [client_data_dict.get(day, None) for day in all_days_in_month]
            })

            graph_specific_title = f"{page_main_title} (Client: {client_id})" if is_main_index_page else page_main_title
            
            fig = px.bar(df_client, 
                         x='Giorno', 
                         y='Altezza acqua (cm)', 
                         title=f'Livello acqua - {graph_specific_title}',
                         text='Altezza acqua (cm)') # Mostra valori sulle barre
            
            # Imposta l'asse X come categorico prima di definire il range specifico
            fig.update_xaxes(type='category')

            initial_xaxis_range = None

            # Calcola l'intervallo per l'asse X basato sugli ultimi 10 *dati* solo per la pagina principale
            if is_main_index_page:
                # Filtra il DataFrame per includere solo i giorni con dati
                df_with_data = df_client.dropna(subset=['Altezza acqua (cm)'])

                if not df_with_data.empty:
                    # Prendi gli ultimi 10 giorni *con dati*
                    last_10_data_points = df_with_data.tail(10)

                    # Ottieni il primo e l'ultimo giorno da questo subset
                    first_day_in_range = last_10_data_points['Giorno'].min()
                    last_day_in_range = last_10_data_points['Giorno'].max()

                    # Per un migliore controllo dello zoom su asse categorico, usiamo gli indici delle categorie.
                    # Le categorie sull'asse saranno stringhe dei giorni del mese.
                    # 'all_days_in_month' contiene i giorni numerici (es. 1, 2, ..., 31)
                    categories_on_axis_str = [str(d) for d in all_days_in_month] # Lista di tutti i giorni del mese come stringhe

                    first_day_str_for_index = str(first_day_in_range)
                    last_day_str_for_index = str(last_day_in_range)
                    try:
                        start_index = categories_on_axis_str.index(first_day_str_for_index)
                        end_index = categories_on_axis_str.index(last_day_str_for_index)
                        # Applica un padding (-0.5 e +0.5) agli indici per assicurare che le barre estreme siano completamente visibili
                        initial_xaxis_range = [start_index - 0.5, end_index + 0.5]
                        logger.info(f"Impostato range asse X per '{client_id}' su indici [{initial_xaxis_range[0]:.1f}, {initial_xaxis_range[1]:.1f}] (corrispondenti ai giorni '{first_day_in_range}' - '{last_day_in_range}').")
                    except ValueError:
                        # Questo non dovrebbe accadere se first/last_day_in_range provengono da all_days_in_month
                        logger.warning(f"Uno dei giorni '{first_day_in_range}' o '{last_day_in_range}' non trovato in categories_on_axis_str per '{client_id}'. Fallback a range stringhe: [{first_day_str_for_index}, {last_day_str_for_index}]")
                        initial_xaxis_range = [first_day_str_for_index, last_day_str_for_index] # Fallback al metodo precedente
                else:
                    logger.info(f"Nessun dato disponibile per il client '{client_id}' per impostare un range iniziale sull'asse X.")


            fig.update_traces(texttemplate='%{text:.0f}', textposition='outside')
            fig.update_layout(
                yaxis_range=[0, 400],
                xaxis_title=f'Giorno del mese ({mese(month_num)} {year})', # Titolo asse X più descrittivo
                yaxis_title='Altezza acqua (cm)', # Etichetta asse Y
                bargap=0.2 # Spazio tra le barre di giorni diversi
            )
            if initial_xaxis_range: # Applica il range solo se calcolato
                fig.update_layout(xaxis_range=initial_xaxis_range)

            include_js = 'cdn' if not plotly_js_included else False
            html_fig_for_client = pio.to_html(fig, full_html=False, include_plotlyjs=include_js)
            if include_js == 'cdn':
                plotly_js_included = True

            if is_main_index_page:
                html_body_content += f"<h2>Livello acqua {client_id}</h2>\n{html_fig_for_client}\n<hr/>\n"
            else: # Pagina di archivio per singolo client
                html_body_content = html_fig_for_client
                break # Per i file di archivio, c'è un solo client per file

        if num_clients_with_data == 0 and is_main_index_page: # Se nessun client aveva dati graficabili
             html_body_content = f"<p>Nessun dato graficabile disponibile per i client nel periodo {page_main_title}.</p>"

    # Costruzione HTML finale
    html_content = f"<html><head>\n"
    html_content += f"    <meta charset=\"utf-8\" />\n"
    html_content += f"    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />\n" # <-- VIEWPORT META TAG AGGIUNTO
    html_content += f"    <title>Grafico Livello acqua {page_main_title}</title>\n</head>\n"
    html_content += f"<body><h1>Grafico Livello acqua - {page_main_title}</h1>\n"
    html_content += html_body_content

    # Aggiungi link ad altri grafici e archivi
    html_content += "\n<h2>Altri Grafici e Archivi</h2>\n"
    
    # Colleziona tutti i file HTML nel repository (root e archivio), escludendo quello corrente
    all_other_html_files_in_repo = []
    
    # Cerca nella directory root del repository
    if os.path.exists(REPO_ROOT_DIR):
        for f in os.listdir(REPO_ROOT_DIR):
            full_path = os.path.join(REPO_ROOT_DIR, f)
            if f.endswith(".html") and full_path != output_html_path and full_path != ARCHIVE_DIR_PATH: # Escludi la cartella archivio stessa
                 all_other_html_files_in_repo.append({"full_path": full_path, "relative_path": f})

    # Cerca nella sottodirectory di archivio
    if os.path.exists(ARCHIVE_DIR_PATH):
        for f in os.listdir(ARCHIVE_DIR_PATH):
            full_path = os.path.join(ARCHIVE_DIR_PATH, f)
            if f.endswith(".html") and full_path != output_html_path:
                 all_other_html_files_in_repo.append({"full_path": full_path, "relative_path": os.path.join(os.path.basename(ARCHIVE_DIR_PATH), f)})

    # Struttura per raggruppare i link degli archivi: {anno: [info_link, ...]}
    archived_links_by_year = {}
    link_to_index_page_info = None # Per le pagine di archivio che linkano a index.html
    for file_item in all_other_html_files_in_repo: # file_item è un dizionario {"full_path": ..., "relative_path": ...}
        # Controlla se il file corrente è la pagina principale (index.html) e non stiamo generando la pagina principale stessa
        if file_item["full_path"] == HTML_OUTPUT_PATH and HTML_OUTPUT_PATH != output_html_path :
            # Determina il mese/anno corrente per il display name di index.html
            # Se stiamo generando un archivio, month_num e year sono del periodo dell'archivio.
            # Per il link a index.html, vogliamo il mese/anno corrente effettivo.
            now_dt_for_index_link = datetime.datetime.now()
            link_to_index_page_info = {
                "filename": file_item["relative_path"], # Usa il percorso relativo per il link href
                "display_name": f"Grafici Mese Corrente ({mese(now_dt_for_index_link.month)} {now_dt_for_index_link.year})",
            }
        elif file_item["relative_path"].startswith(os.path.basename(ARCHIVE_DIR_PATH) + os.sep + "grafico_"): # Se è un file di archivio nella sottocartella
            match_archive = re.match(r"grafico_(\d{4})-(\d{2})_(.+)\.html", os.path.basename(file_item["relative_path"]))
            if match_archive:
                year_str, month_str, client_part = match_archive.groups()
                year_val = int(year_str)
                month_val = int(month_str)
                display_name = f"{mese(month_val)} {year_str} (Client: {client_part.replace('_', ' ')})"

                if year_val not in archived_links_by_year:
                    archived_links_by_year[year_val] = []
                archived_links_by_year[year_val].append({
                    "filename": file_item["relative_path"], # Usa il percorso relativo per il link href
                    "display_name": display_name,
                    "month": month_val,
                    "client": client_part
                })

    # Genera l'HTML per i link
    links_html_generated = False
    if link_to_index_page_info and output_html_path != HTML_OUTPUT_PATH: # Questo sarà vero solo per le pagine di archivio
        html_content += f"<ul><li><a href=\"{link_to_index_page_info['filename']}\">{link_to_index_page_info['display_name']}</a></li></ul>\n"
        links_html_generated = True
    
    if archived_links_by_year:
        # Ordina gli anni degli archivi in modo decrescente
        sorted_archive_years = sorted(archived_links_by_year.keys(), reverse=True)
        for archive_year_val in sorted_archive_years:
            html_content += f"<h3>Archivi Anno {archive_year_val}</h3>\n<ul>\n"
            # Ordina i link per mese (decrescente) e poi per nome client (crescente)
            links_in_year = sorted(archived_links_by_year[archive_year_val], key=lambda x: (x.get("month", 0), x.get("client", "")), reverse=False)
            links_in_year.sort(key=lambda x: x.get("month",0), reverse=True) # Ordinamento primario per mese decrescente
            
            for link_info in links_in_year:
                html_content += f"    <li><a href=\"{link_info['filename']}\">{link_info['display_name']}</a></li>\n"
            html_content += "</ul>\n"
        links_html_generated = True

    if not links_html_generated:
        html_content += "<ul><li>Nessun altro grafico o archivio disponibile.</li></ul>\n"
            
    html_content += f"<p><em>Ultimo aggiornamento: {datetime.datetime.now().strftime('%d-%m-%Y %H:%M:%S')}</em></p>\n"
    html_content += "</body></html>\n"

    try:
        with open(output_html_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        logger.info(f"Grafico Plotly HTML salvato in '{output_html_path}'")
    except IOError as e:
        logger.error(f"Impossibile scrivere il file HTML Plotly '{output_html_path}': {e}")

def process_archived_logs_plotly():
    archived_files_generated = []
    if not os.path.exists(LOG_DIRECTORY):
        logger.error(f"La directory dei log '{LOG_DIRECTORY}' non esiste. Impossibile processare gli archivi.")
        return archived_files_generated
        
    # Assicura che la directory di archivio esista
    if not os.path.exists(ARCHIVE_DIR_PATH):
        try:
            os.makedirs(ARCHIVE_DIR_PATH)
            logger.info(f"Directory di archivio creata: {ARCHIVE_DIR_PATH}")
        except OSError as e:
            logger.error(f"Impossibile creare la directory di archivio {ARCHIVE_DIR_PATH}: {e}. L'archiviazione fallirà.")
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
                    if not client_specific_data.get("days"):
                        logger.info(f"Nessun giorno con dati per il client '{client_id}' nell'archivio {log_file_name}.")
                        continue
                    data_for_graph = {client_id: client_specific_data}
                    safe_client_id = re.sub(r'[^\w\-\.]', '_', client_id)
                    archive_html_filename = f"grafico_{log_year}-{log_month:02d}_{safe_client_id}.html" # Nome file senza percorso
                    archive_html_filepath = os.path.join(REPO_ROOT_DIR, archive_html_filename)
                    archive_page_title = f"{mese_str_archivio} {log_year} (Client: {client_id})"
                    create_and_save_graph_plotly(
                        data_for_graph,
                        archive_page_title,
                        log_year,
                        log_month, # Passa il numero del mese
                        archive_html_filepath,
                        is_main_index_page=False,
                        is_archive_file=True
                    )
                    archived_files_generated.append(archive_html_filepath)
            else:
                logger.info(f"Nessun dato da processare per l'archivio {log_file_name}.")
    return archived_files_generated

if __name__ == "__main__":
    if not setup_logging():
        sys.exit("Avvio fallito a causa di errori di configurazione del logging.")
    manage_script_event_log_rotation()
    logger.info("Avvio script generazione grafico con Plotly...")
    now_timestamp_for_commit = datetime.datetime.now()
    current_month_num = now_timestamp_for_commit.month
    current_year_num = now_timestamp_for_commit.year
    current_month_name = mese(current_month_num)
    client_name_map = load_client_name_map(CLIENT_MAP_INI_FILE)
    logger.info(f"Lettura dati per il mese corrente: {current_month_name} {current_year_num} da {MEASUREMENT_LOG_FILE_PATH}")
    current_month_data_all_clients = read_and_parse_log_file(MEASUREMENT_LOG_FILE_PATH, current_month_num, current_year_num)
    
    logger.info(f"Generazione di {HTML_OUTPUT_PATH} per il mese corrente con Plotly: {current_month_name} {current_year_num}")
    create_and_save_graph_plotly(
        current_month_data_all_clients,
        f"{current_month_name} {current_year_num}",
        current_year_num,
        current_month_num, # Passa il numero del mese corrente
        HTML_OUTPUT_PATH,
        is_main_index_page=True,
        is_archive_file=False
    )
    generated_html_files_for_git = []
    if os.path.exists(HTML_OUTPUT_PATH):
        generated_html_files_for_git.append(HTML_OUTPUT_PATH)
            
    logger.info("Inizio processamento log archiviati con Plotly...")
    archived_htmls = process_archived_logs_plotly()
    generated_html_files_for_git.extend(archived_htmls)
    logger.info(f"File HTML Plotly archiviati generati: {archived_htmls}")

    if generated_html_files_for_git:
        existing_generated_files = [f for f in generated_html_files_for_git if os.path.exists(f)]
        if existing_generated_files:
            logger.info(f"Tentativo di push per i seguenti file Plotly: {existing_generated_files}")
            git_push(existing_generated_files) # Commentato per test
        else:
            logger.info("Nessun file HTML Plotly (corrente o archiviato) è stato effettivamente generato o trovato, push saltato.")
    else:
        logger.info("Nessun file HTML Plotly generato, push saltato.")
    logger.info("Script generazione grafico Plotly completato.")