import socket
import time

# --- Configurazione ---
# Server Telnet locale da cui leggere i dati
TELNET_HOST = 'localhost'
TELNET_PORT = 6571

# Server TCP remoto a cui inviare i dati
SERVER_HOST = '192.168.178.28' # Indirizzo IP del server (es. Raspberry Pi con acquaServer.py)
SERVER_PORT = 50008            # Porta del server (deve coincidere con quella del server in ascolto)

def read_line_from_socket(sock):
    """Legge una singola linea (terminata da \n) da una socket."""
    line_buffer = ""
    while True:
        try:
            char = sock.recv(1)
            if not char:  # Connessione chiusa
                print "Errore: Connessione Telnet chiusa prematuramente durante la lettura."
                return None
            if char == '\n':
                break
            line_buffer += char
        except socket.error as e:
            print "Errore socket durante la lettura da Telnet: " + str(e)
            return None
    return line_buffer

def read_data_from_telnet(host, port):
    """
    Si connette al server Telnet, scarta la prima linea e legge la seconda.
    Restituisce la seconda linea letta come stringa (byte string in Python 2)
    o None in caso di errore.
    """
    print "Tentativo di connessione a Telnet " + host + ":" + str(port)
    s1 = None
    try:
        s1 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s1.settimeout(10) # Timeout per la connessione e per recv
        s1.connect((host, port))
        print "Connesso a Telnet " + host + ":" + str(port)

        # Leggi e scarta la prima linea (es. un banner o una linea vuota)
        print "Lettura e scarto della prima linea da Telnet..."
        discarded_line = read_line_from_socket(s1)
        if discarded_line is None:
            # Errore già stampato da read_line_from_socket
            return None
        print "Prima linea scartata: '" + discarded_line + "'"

        # Leggi la seconda linea (i dati effettivi)
        print "Lettura della seconda linea (dati effettivi) da Telnet..."
        data_line = read_line_from_socket(s1)
        if data_line is None:
            # Errore già stampato da read_line_from_socket
            return None
        
        print "Dati letti da Telnet: '" + data_line + "'"
        return data_line

    except socket.timeout:
        print "Errore: Timeout durante la connessione o la lettura da Telnet " + host + ":" + str(port)
        return None
    except socket.error as e:
        print "Errore socket Telnet: " + str(e)
        return None
    finally:
        if s1:
            s1.close()
            print "Connessione Telnet chiusa."

def send_data_to_server(host, port, data):
    """
    Si connette al server TCP e invia i dati.
    Stampa la risposta del server.
    """
    if data is None:
        print "Nessun dato da inviare al server."
        return

    print "Tentativo di connessione al server TCP " + host + ":" + str(port)
    s2 = None
    try:
        s2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s2.settimeout(10) # Timeout per la connessione e per recv
        s2.connect((host, port))
        print "Connesso al server TCP " + host + ":" + str(port)

        print "Invio dati al server: '" + data + "' (" + str(len(data)) + " bytes)"
        s2.sendall(data) # In Python 2, 'data' è già una byte string se letta da socket

        # Riceve la risposta (echo)
        print "Attesa risposta dal server..."
        data_received = s2.recv(1024)

        if data_received:
            print "Ricevuto dal server: '" + data_received + "'"
        else:
            print "Nessuna risposta ricevuta dal server."

    except socket.timeout:
        print "Errore: Timeout durante la connessione o la ricezione dal server TCP " + host + ":" + str(port)
    except socket.error as e:
        print "Errore socket server TCP: " + str(e)
    finally:
        if s2:
            s2.close()
            print "Connessione server TCP chiusa."

# --- Esecuzione principale ---
if __name__ == "__main__":
    # 1. Leggi dati dal servizio Telnet locale
    distance_data = read_data_from_telnet(TELNET_HOST, TELNET_PORT)

    # 2. Se i dati sono stati letti con successo, inviali al server TCP remoto
    if distance_data is not None:
        send_data_to_server(SERVER_HOST, SERVER_PORT, distance_data)
    else:
        print "Lettura dati da Telnet fallita. Invio al server saltato."

    print "Script completato."
