def mese(meseNum):
    mesi_italiani = [
        # Elemento fittizio all'indice 0 per un facile accesso 1-based
        None, 
        'Gennaio', 'Febbraio', 'Marzo', 'Aprile', 'Maggio', 'Giugno',
        'Luglio', 'Agosto', 'Settembre', 'Ottobre', 'Novembre', 'Dicembre'
    ]
    if 1 <= meseNum <= 12:
        return mesi_italiani[meseNum]
    else:
        # Gestisce un numero di mese non valido, puoi adattare questo comportamento
        # ad esempio sollevando un'eccezione: raise ValueError("Numero mese non valido")
        return 'Mese Sconosciuto'
