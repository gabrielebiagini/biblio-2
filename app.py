import streamlit as st
from habanero import Crossref
import requests

# --- Configurazione della Pagina ---
# Impostiamo il titolo che appare nella scheda del browser e l'icona
st.set_page_config(page_title="Verificatore Bibliografico", page_icon="📚")

# --- Funzione per Verificare una singola citazione ---
# Questa funzione prende una stringa (la citazione) e interroga Crossref
def check_reference(reference_text):
    """
    Verifica una singola citazione bibliografica usando l'API di Crossref.
    Restituisce un dizionario con lo stato e i dettagli trovati.
    """
    try:
        # Inizializziamo il client di Crossref
        cr = Crossref()
        
        # Eseguiamo la ricerca. Usiamo 'bibliographic' che è ottimo per cercare
        # a partire da una citazione completa. Chiediamo al massimo 1 risultato.
        result = cr.works(query_bibliographic=reference_text, limit=1)

        # Se la ricerca ha prodotto risultati e c'è almeno un item...
        if result['status'] == 'ok' and result['message']['total-results'] > 0:
            item = result['message']['items'][0]
            
            # Estraiamo le informazioni più utili
            title = item.get('title', ['N/A'])[0]
            author_list = item.get('author', [])
            authors = ', '.join([f"{author.get('given', '')} {author.get('family', '')}" for author in author_list])
            doi = item.get('DOI', 'N/A')
            
            # Restituiamo uno stato di successo e i dati trovati
            return {
                "status": "TROVATO",
                "title": title,
                "authors": authors,
                "doi": f"https://doi.org/{doi}" if doi != 'N/A' else 'N/A'
            }
        else:
            # Se non ci sono risultati, restituiamo uno stato di fallimento
            return {"status": "NON TROVATO"}
            
    except requests.exceptions.RequestException as e:
        # Gestiamo eventuali errori di rete o dell'API
        return {"status": "ERRORE API", "details": str(e)}
    except Exception as e:
        # Gestiamo altri errori imprevisti
        return {"status": "ERRORE SCONOSCIUTO", "details": str(e)}


# --- Interfaccia Utente di Streamlit ---

st.title("🔎 Verificatore di Bibliografia Accademica")
st.markdown("""
Questa applicazione ti aiuta a verificare le citazioni bibliografiche utilizzando la banca dati di **Crossref**.
Inserisci una o più citazioni nel campo di testo sottostante, una per riga, e clicca su "Verifica".
""")

# Creiamo un'area di testo per l'input dell'utente
# 'height=250' la rende abbastanza grande per più citazioni
# 'placeholder' mostra un testo di esempio
references_input = st.text_area(
    "Incolla qui la tua bibliografia (una citazione per riga):",
    height=250,
    placeholder="Es: Smith, J. (2020). A study on academic references. Journal of Knowledge, 15(2), 123-145.\n"
                "Doe, A. et al. (2021). The challenges of bibliography verification. Science Today."
)

# Aggiungiamo un bottone per avviare la verifica
if st.button("✅ Verifica Bibliografia"):
    # Controlliamo se l'utente ha inserito del testo
    if references_input.strip():
        # Dividiamo l'input in una lista di citazioni, una per ogni riga
        # 'strip()' rimuove spazi bianchi inutili all'inizio e alla fine di ogni riga
        references_list = [ref.strip() for ref in references_input.split('\n') if ref.strip()]
        
        # Liste per tenere traccia dei risultati
        found_references = []
        not_found_references = []
        
        # Mostriamo una barra di progresso mentre lavoriamo
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        # Iteriamo su ogni citazione inserita
        for i, ref in enumerate(references_list):
            status_text.text(f"Verifica in corso: {i+1}/{len(references_list)} - {ref[:50]}...")
            
            # Chiamiamo la nostra funzione di verifica
            result = check_reference(ref)
            
            if result['status'] == 'TROVATO':
                found_references.append((ref, result))
            else:
                not_found_references.append((ref, result))
            
            # Aggiorniamo la barra di progresso
            progress_bar.progress((i + 1) / len(references_list))
        
        status_text.text("Verifica completata!")
        
        # --- Mostriamo i Risultati ---
        st.header("📊 Risultati della Verifica")
        
        total_refs = len(references_list)
        found_count = len(found_references)
        not_found_count = len(not_found_references)
        
        # Calcoliamo la percentuale di errore
        error_percentage = (not_found_count / total_refs) * 100 if total_refs > 0 else 0
        
        # Mostriamo le statistiche principali con delle colonne
        col1, col2, col3 = st.columns(3)
        col1.metric("Totale Citazioni", total_refs)
        col2.metric("Trovate Correttamente", found_count, "✅")
        col3.metric("Non Trovate / Errate", not_found_count, f"-{error_percentage:.1f}%", help="Percentuale di fonti non trovate sul totale.")

        st.markdown("---") # Una linea di separazione

        # Mostriamo i dettagli delle fonti trovate
        if found_references:
            st.subheader("📚 Fonti Trovate Correttamente")
            for original_ref, result in found_references:
                with st.container():
                    st.success(f"**Citazione Originale:** {original_ref}")
                    st.info(f"""
                    **Titolo Trovato:** {result['title']}  
                    **Autori:** {result['authors']}  
                    **DOI:** [{result['doi']}]({result['doi']})
                    """)

        # Mostriamo i dettagli delle fonti non trovate
        if not_found_references:
            st.subheader("⚠️ Fonti non Trovate o con Errori")
            for original_ref, result in not_found_references:
                 st.error(f"**Citazione Originale:** {original_ref}")
                 st.warning(f"**Stato:** {result['status']}. Non è stato possibile trovare una corrispondenza univoca su Crossref. Controlla la formattazione, l'anno o il nome della rivista.")

    else:
        st.warning("Per favore, inserisci almeno una citazione da verificare.")
