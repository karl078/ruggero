#!/usr/bin/env python3

# date: 2019.08.04
# https://stackoverflow.com/questions/57341566/my-bar-chart-does-not-appear-on-screen-how-can-i-fix-that
#
# https://mpld3.github.io/index.html
#

#from flask import Flask
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import mpld3
import numpy as np
import ftplib
import time
import datetime
import calendar
from mese import mese
from git import Repo
#app = Flask(__name__)

#@app.route('/')
PATH_OF_GIT_REPO = '/home/pi/python-scripts/.git'  # make sure .git folder is properly configured

righe = [] #definisco il vettore per accumulare le righe del file
righeJ = [] #definisco il vettore per accumulare le righe del file dell'acqua comunale
date = []
giorniMese = []
giorniMeseJ = []
giorniMeseInt = []
giorniMeseIntJ = []
temp = []
ore = []
altezze = []
altezzeJ = []

#FUNZIONE per aggiornare la pagina html statica su Github Pages
# source tutorials:
#  https://blog.balasundar.com/automate-git-operations-using-python
#  https://stackoverflow.com/questions/41836988/git-push-via-gitpython
# FIX errore credenziali: https://levelup.gitconnected.com/fix-password-authentication-github-3395e579ce74
# aggiornare token ogni 90 giorni https://techglimpse.com/git-push-github-token-based-passwordless/
# rigenerare il token (se necessario, anche se ad oggi ho scelto quello never-expire, e inviare da riga di comando quanto sotto:
# RICORDARSI di selezionare l'opzione REPO quando si rigenera il token. fonte: https://github.com/orgs/community/discussions/23475
# RICORDARSI di dare il comando sotto riportato nella cartella python-scripts
# git remote set-url origin https://<GITHUB_ACCESS_TOKEN>@github.com/<GITHUB_USERNAME>/<REPOSITORY_NAME>.git
# git remote set-url origin https://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@github.com/karl078/ruggero.git

def git_push():
    try:
        repo = Repo(PATH_OF_GIT_REPO)
        repo.git.add(update=True)
        repo.index.add(['/home/pi/python-scripts/index.html'])
        repo.index.commit('Aggiornamento misurazione acqua del ' + str(now.day) + '-' + str(now.month) + '-' + str(now.year))
        origin = repo.remote(name='origin')
        origin.push()
        print("File caricato su GITHUB PAGES!\n")
    except:
        print('Some error occured while pushing the code')

# funzione per aggiungere il valore misurazioni sul grafico
def addlabels(x,y):
    for i in range(len(x)):
        plt.text(x[i]+0.25,y[i]+2,y[i], color='red', fontsize=14, rotation=90)


dataOggi = time.strftime("%d/%m/%Y")
meseOggi=dataOggi[3:5]
print("Ricavo mese in lettere..\n")
meseNum=int(meseOggi)
#meseNum=4 #per forzare il mese
meseStr=mese(meseNum)
print(meseStr)

print("Ricavo numero di giorni del mese..\n")
now = datetime.datetime.now()
numGiorni = calendar.monthrange(now.year, now.month)[1]
#numGiorni=31 #per forzare i giorni
print(numGiorni)


######## LEGGO DATI CISTERNA POZZO ##########
#accumulo i dati delle righe del file
with open('/home/pi/python-scripts/acqua.log') as fo:
    for rec in fo:
        righe.append(rec)

# splitto i dati ricavando le informazioni per il grafico:
# giorni nelle ascisse
# altezze nelle ordinate
for i in righe:
    temp=i.split()
    giorniMese=temp[0]
    giorniMeseInt.append(int(giorniMese[0:2])) #verificare se necessaria questa forzatura di conversione in INT
    altezze.append(float(temp[2]))
#    date.append(i[0:8])
#print(giorniMeseInt)

######## LEGGO DATI CISTERNA COMUNALE ##########
with open('/home/pi/python-scripts/acquaComune.log') as foJ:
    for recJ in foJ:
        righeJ.append(recJ)
#print(righeJ)

# splitto i dati ricavando le informazioni per il grafico:
# giorni nelle ascisse
# altezze nelle ordinate
for j in righeJ:
    temp=j.split()
    giorniMeseJ=temp[0]
    giorniMeseIntJ.append(int(giorniMeseJ[0:2])) 
    altezzeJ.append(float(temp[2]))
#    date.append(i[0:8])
#print([min(giorniMeseIntJ),max(giorniMeseIntJ)])

#plots = plt.bar(giorniMeseInt, altezze, width=0.5) #creo il grafico
#fig = plt.figure()
fig, ax = plt.subplots()

#PRIMO SUBPLOT
plt.subplot(2, 1, 1)    #GRAFICO ACQUA POZZO
plt.bar(giorniMeseInt, altezze, width=0.5)
addlabels(giorniMeseInt, altezze)
#for p in pps:
#    height = p.get_height()
#    ax.annotate('{}'.format(height), xy=p.get_x() + p.get_width() / 2, height), xytext=(0, 3), textcoords="offset points", ha='center', va='bottom')

axes = plt.gca()
axes.yaxis.grid()   #assi orizzontali
#plt.xlabel("GIORNO")
plt.ylabel("ALTEZZA [cm]")
TITOLO = meseStr + ' ' + str(now.year) + ": SOPRA cisterna pozzo - SOTTO cisterna comunale"
plt.title(TITOLO) # modifica automatica a seconda del mese
plt.ylim([0,425])
plt.xlim([0,numGiorni+0.5])
#plt.yticks(np.arange(0, 400, 20.0)) #modificare secondo cm altezza
plt.xticks(np.arange(1, numGiorni+1, 1.0)) #modificare secondo numero a seconda dei giorni del mese

#SECONDO SUBPLOT
plt.subplot(2, 1, 2)    #GRAFICO ACQUA COMUNALE
plt.bar(giorniMeseIntJ, altezzeJ, width=0.5)
addlabels(giorniMeseIntJ, altezzeJ)
axes = plt.gca()
axes.yaxis.grid()   #assi orizzontali
plt.xlabel("GIORNO")
plt.ylabel("ALTEZZA [cm]")
#plt.title(TITOLO) # modifica automatica a seconda del mese
plt.ylim([0,425])
plt.xlim([0,numGiorni+0.5])
#plt.yticks(np.arange(0, 400, 20.0)) #modificare secondo cm altezza
plt.xticks(np.arange(1, numGiorni+1, 1.0)) #modificare secondo numero a seconda dei giorni del mese
#plt.legend()

#fig = plots[0].figure  #sostituito da "fig = plt.figure()" vedi sopra
#ax = plots[0].axis

# mpld3.save_html(fig, "/var/www/html/acqua2.html") #salva solo se vado sul sito localhost ma gli mancano i permessi di root per salvare nella cartella
plt_html = mpld3.fig_to_html(fig)
Html_file = open("/home/pi/python-scripts/index.html", "w")
Html_file.write('<meta name="viewport" content="width=device-width, initial-scale=1.0">')
Html_file.write(plt_html)
print("File acqua.html creato!\n")
#CARICAMENTO FILE SU GITHUB PAGES
git_push()

