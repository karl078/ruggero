#!/usr/bin/env python3

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

# Global Configuration (move these to a config file later)
PATH_OF_GIT_REPO = '/home/pi/python-scripts/.git'

# Function to push to GitHub Pages
def git_push():
    try:
        repo = Repo(PATH_OF_GIT_REPO)
        repo.git.add(update=True)
        repo.index.add(['/home/pi/python-scripts/index.html'])
        repo.index.commit('Aggiornamento misurazione acqua del ' + str(now.day) + '-' + str(now.month) + '-' + str(now.year)+'-'+str(now.hour)+':'+str(now.minute))
        origin = repo.remote(name='origin')
        origin.push()
        print("File caricato su GITHUB PAGES!\n")
    except Exception as e:
        print(f'Some error occurred while pushing the code: {e}')

# Function to add labels to the bars
def addlabels(ax, x, y, width):
    """Adds value labels above each bar in the chart.

    Args:
        ax: the axis where labels will be added.
        x: A list of x-coordinates of the bars.
        y: A list of bar heights (values).
        width: width of each bar.
    """
    for i in range(len(x)):
        # Center the label horizontally above the bar
        ax.text(x[i] + width / 2, y[i] + 5, y[i], color='white', fontsize=11, fontweight='bold', ha='center', va='bottom', rotation=90, path_effects=[path_effects.withStroke(linewidth=3, foreground='#333333')])

# Function to read and parse a log file
def read_and_parse_log_file(log_file_path):
    """Reads a log file, parses the data, and returns days and values."""
    righe = []
    giorniMeseInt = []
    altezze = []

    try:
        with open(log_file_path, 'r') as fo:
            for rec in fo:
                righe.append(rec)
    except FileNotFoundError:
        print(f"Error: Log file not found at {log_file_path}")
        return [], []  # Return empty lists on error

    for i in righe:
        try:
            temp = i.split()
            giorniMese = temp[0]
            giorniMeseInt.append(int(giorniMese[0:2]))
            altezze.append(float(temp[2]))
        except (ValueError, IndexError):
            print(f"Warning: Invalid data format in log file: {i}")
            # You could choose to handle this differently, e.g., log the error, skip the line, etc.

    return giorniMeseInt, altezze

# Get current date and month
dataOggi = time.strftime("%d/%m/%Y")
meseOggi = dataOggi[3:5]
print("Ricavo mese in lettere..\n")
meseNum = int(meseOggi)
meseStr = mese(meseNum)
print(meseStr)

print("Ricavo numero di giorni del mese..\n")
now = datetime.datetime.now()
numGiorni = calendar.monthrange(now.year, now.month)[1]
print(numGiorni)

# Read data for well water and municipal water
giorniMeseInt, altezze = read_and_parse_log_file('/home/pi/python-scripts/acqua.log')
giorniMeseIntJ, altezzeJ = read_and_parse_log_file('/home/pi/python-scripts/acquaComune.log')

# Create the plots
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 7))  # Create figure and axes (increase size)
fig.tight_layout(pad=5.0) #add more space between subplots

# Chart 1 (Well Water)
ax1.bar(giorniMeseInt, altezze, width=0.6, color='#66b3ff', edgecolor='#003366')  # Use a better color and border
addlabels(ax1, giorniMeseInt, altezze, 0.6) #change width
ax1.yaxis.grid(True, color='lightgray', linestyle='--')  # Lighter gridlines
ax1.set_ylabel("ALTEZZA [cm]", fontsize=14) #reduce font size
ax1.set_ylim([0, 425])
ax1.set_xlim([0, numGiorni + 0.5])
ax1.set_xticks(np.arange(1, numGiorni + 1, 1.0))
ax1.tick_params(axis='both', which='major', labelsize=12)  # Increase tick label size #reduce font size
ax1.set_title("Cisterna Pozzo - " + meseStr + " " + str(now.year), fontsize=16)  # Title for Well Water subplot (with month)

# Chart 2 (Municipal Water)
ax2.bar(giorniMeseIntJ, altezzeJ, width=0.6, color='#90ee90', edgecolor='#006400')  # Use a different color and border
addlabels(ax2, giorniMeseIntJ, altezzeJ, 0.6) #change width
ax2.yaxis.grid(True, color='lightgray', linestyle='--')  # Lighter gridlines
ax2.set_xlabel("GIORNO", fontsize=14) #reduce font size
ax2.set_ylabel("ALTEZZA [cm]", fontsize=14) #reduce font size
ax2.set_ylim([0, 425])
ax2.set_xlim([0, numGiorni + 0.5])
ax2.set_xticks(np.arange(1, numGiorni + 1, 1.0))
ax2.tick_params(axis='both', which='major', labelsize=12)  # Increase tick label size #reduce font size
ax2.set_title("Cisterna Comunale - " + meseStr + " " + str(now.year), fontsize=16)  # Title for Municipal Water subplot (with month)

# Common Title
TITOLO = meseStr + ' ' + str(now.year) + ": SOPRA cisterna pozzo - SOTTO cisterna comunale"
fig.suptitle(TITOLO, fontsize=18, fontweight='bold')  # Make main title bold

# Style for the whole page
plt.rcParams['axes.facecolor'] = '#f5f5f5' #change background color
plt.rcParams['axes.edgecolor'] = '#000000' #add border to plot

plt_html = mpld3.fig_to_html(fig) #Generate html code
Html_file = open("/home/pi/python-scripts/index.html", "w")
Html_file.write('<meta name="viewport" content="width=device-width, initial-scale=1.0">')
Html_file.write(plt_html)
print("File acqua.html creato!\n")

# Upload on Github Pages
git_push()
