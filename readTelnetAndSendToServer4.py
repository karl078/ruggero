import socket

HOST = '192.168.178.28'   #server con Influx e Grafana
PORT = 50008             #deve coincidere con quella del server in ascolto

#per lettura da Telnet
s1 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s1.connect(("localhost",6571))
distanceOK =""
i=0
while (1):
    distance = str(s1.recv(1)).encode("utf-8")
    if ((i == 0) and distance != '\n'):
        print("Leggo: " + distance)
        continue
    elif (i==0 and distance == '\n'):
        print("primoN\n")
        i = i + 1
        continue
    elif (i == 1 and distance != '\n'):
        distanceOK = distanceOK + distance
        print distanceOK
    elif (i == 1 and distance == '\n'):
        print("\nInvio la distanza: " + distanceOK)
        break
s1.close()

#per invio al server
s2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s2.connect((HOST, PORT))
s2.send(distanceOK)
dataFromServer = s2.recv(1024)
s2.close()
#print 'Conferma ricezione e ritrasmissione dal server: ', dataFromServer, '\n'