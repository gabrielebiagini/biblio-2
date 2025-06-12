import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import PyPDF2
from docx import Document
import re
import requests
import time
import json
from datetime import datetime
import io

# Configurazione pagina
st.set_page_config(
    page_title="Bibliography Checker",
    page_icon="📚",
    layout="wide"
)

# CSS per un look più bello
st.markdown("""
<style>
    .main-header {
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
        padding: 1rem;
        border-radius: 10px;
        color: white;
        text-align: center;
        margin-bottom: 2rem;
    }
    .metric-card {
        background: #f8f9fa;
        padding: 1rem;
        border-radius: 10px;
        border-left: 4px solid #667eea;
    }
    .error-card {
        background: #fff5f5;
        border-left: 4px solid #e53e3e;
        padding: 1rem;
        border-radius: 8px;
        margin: 0.5rem 0;
    }
    .success-card {
        background: #f0fff4;
        border-left: 4px solid #38a169;
        padding: 1rem;
        border-radius: 8px;
        margin: 0.5rem 0;
    }
</style>
""", unsafe_allow_html=True)

# Classe per rappresentare una citazione
class Citation:
    def __init__(self, original_text, authors=None, year=None, title=None, doi=None):
        self.original_text = original_text
        self.authors = authors or []
        self.year = year
        self.title = title
        self.doi = doi

# Funzione per estrarre testo da PDF
def extract_text_from_pdf(uploaded_file):
    try:
        pdf_reader = PyPDF2.PdfReader(uploaded_file)
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text() + "\n"
        return text
    except Exception as e:
        st.error(f"Errore nell'estrazione PDF: {str(e)}")
        return ""

# Funzione per estrarre testo da DOCX
def extract_text_from_docx(uploaded_file):
    try:
        doc = Document(uploaded_file)
        text = ""
        for paragraph in doc.paragraphs:
            text += paragraph.text + "\n"
        return text
    except Exception as e:
        st.error(f"Errore nell'estrazione DOCX: {str(e)}")
        return ""

# Funzione per trovare la sezione bibliografia
def find_bibliography_section(text):
    # Pattern per identificare inizio bibliografia
    patterns = [
        r'(?i)references?\s*\n',
        r'(?i)bibliography\s*\n', 
        r'(?i)works?\s+cited\s*\n',
        r'(?i)riferimenti\s+bibliografici?\s*\n',
        r'(?i)bibliografia\s*\n'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            # Restituisce dal punto trovato fino alla fine
            return text[match.start():]
    
    # Se non trova pattern specifici, prende ultima parte del documento (70%)
    return text[int(len(text) * 0.7):]

# Funzione per estrarre citazioni (semplificata per iniziare)
def extract_citations(text):
    bib_section = find_bibliography_section(text)
    citations = []
    
    # Dividi in righe e cerca quelle che sembrano citazioni
    lines = bib_section.split('\n')
    
    for line in lines:
        line = line.strip()
        # Criteri base per identificare una citazione:
        # - Lunghezza ragionevole
        # - Contiene numeri (anni)
        # - Contiene punto (fine frase)
        if len(line) > 30 and any(char.isdigit() for char in line) and '.' in line:
            # Estrai anno se presente
            year_match = re.search(r'\b(19|20)\d{2}\b', line)
            year = year_match.group() if year_match else None
            
            # Estrai DOI se presente  
            doi_match = re.search(r'10\.\d+/[^\s]+', line)
            doi = doi_match.group() if doi_match else None
            
            # Estrai autori (pattern semplificato)
            authors = []
            # Cerca pattern come "Cognome, N." all'inizio
            author_match = re.search(r'^([A-Z][a-z]+(?:,\s[A-Z]\.?)*)', line)
            if author_match:
                authors = [author_match.group().strip()]
            
            # Estrai titolo (tra virgolette o pattern comune)
            title = None
            title_patterns = [
                r'"([^"]+)"',  # Titolo tra virgolette
                r'\.?\s([A-Z][^.]+)\.',  # Titolo dopo punto iniziale
            ]
            
            for pattern in title_patterns:
                title_match = re.search(pattern, line)
                if title_match and len(title_match.group(1)) > 10:
                    title = title_match.group(1).strip()
                    break
            
            # Crea oggetto citazione
            citation = Citation(
                original_text=line,
                authors=authors,
                year=year,
                title=title,
                doi=doi
            )
            citations.append(citation)
    
    return citations

# Funzione per cercare su CrossRef (database gratuito)
def search_crossref(query, max_results=3):
    try:
        url = "https://api.crossref.org/works"
        params = {
            'query': query,
            'rows': max_results,
            'sort': 'relevance'
        }
        
        response = requests.get(url, params=params, timeout=10)
        if response.status_code != 200:
            return []
        
        data = response.json()
        results = []
        
        if 'message' in data and 'items' in data['message']:
            for item in data['message']['items']:
                try:
                    title = ' '.join(item.get('title', ['']))
                    
                    authors = []
                    for author in item.get('author', [])[:3]:
                        if 'family' in author:
                            name = author['family']
                            if 'given' in author:
                                name += f", {author['given']}"
                            authors.append(name)
                    
                    year = None
                    if 'published-print' in item:
                        year = str(item['published-print']['date-parts'][0][0])
                    elif 'published-online' in item:
                        year = str(item['published-online']['date-parts'][0][0])
                    
                    journal = item.get('container-title', [None])[0]
                    doi = item.get('DOI', '')
                    
                    results.append({
                        'title': title,
                        'authors': authors,
                        'year': year,
                        'journal': journal,
                        'doi': doi,
                        'database': 'CrossRef'
                    })
                except Exception:
                    continue
        
        return results
    except Exception as e:
        st.warning(f"Errore ricerca CrossRef: {str(e)}")
        return []

# Funzione per calcolare similarità (semplificata)
def calculate_similarity(citation, result):
    from fuzzywuzzy import fuzz
    
    score = 0
    factors = 0
    
    # Confronta titoli
    if citation.title and result['title']:
        title_sim = fuzz.token_set_ratio(citation.title.lower(), result['title'].lower()) / 100
        score += title_sim * 0.5
        factors += 0.5
    
    # Confronta anni
    if citation.year and result['year']:
        if citation.year == result['year']:
            score += 0.3
        elif abs(int(citation.year) - int(result['year'])) <= 1:
            score += 0.2
        factors += 0.3
    
    # Confronta autori
    if citation.authors and result['authors']:
        author_sim = 0
        for c_author in citation.authors:
            for r_author in result['authors']:
                sim = fuzz.ratio(c_author.lower(), r_author.lower()) / 100
                author_sim = max(author_sim, sim)
        score += author_sim * 0.2
        factors += 0.2
    
    return score / factors if factors > 0 else 0

# Funzione principale per verificare una citazione
def verify_citation(citation):
    # Prepara query di ricerca
    query_parts = []
    
    if citation.title and len(citation.title) > 5:
        query_parts.append(f'"{citation.title}"')
    
    if citation.authors:
        # Prendi primo autore
        first_author = citation.authors[0].split(',')[0]
        query_parts.append(first_author)
    
    if citation.year:
        query_parts.append(citation.year)
    
    query = ' '.join(query_parts)
    
    # Cerca nei database
    results = search_crossref(query)
    
    if not results:
        return {
            'status': 'not_found',
            'score': 0,
            'best_match': None,
            'errors': ['Citazione non trovata nei database accademici']
        }
    
    # Trova miglior match
    best_score = 0
    best_match = None
    
    for result in results:
        score = calculate_similarity(citation, result)
        if score > best_score:
            best_score = score
            best_match = result
    
    # Determina status
    errors = []
    if best_score >= 0.8:
        status = 'verified'
    elif best_score >= 0.6:
        status = 'uncertain'
        errors.append('Match incerto - verificare manualmente')
    else:
        status = 'error'
        errors.append('Nessun match affidabile trovato')
    
    return {
        'status': status,
        'score': best_score,
        'best_match': best_match,
        'errors': errors
    }

# INTERFACCIA PRINCIPALE
def main():
    # Header principale
    st.markdown("""
    <div class="main-header">
        <h1>📚 Bibliography Checker</h1>
        <p>Verifica automatica e accurata delle tue bibliografie accademiche</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Sidebar con informazioni
    with st.sidebar:
        st.header("ℹ️ Come funziona")
        st.markdown("""
        1. **Carica** il tuo PDF o DOCX
        2. **Estrazione** automatica citazioni  
        3. **Verifica** su database accademici
        4. **Report** dettagliato con errori
        
        **Database utilizzati:**
        - CrossRef (DOI e metadati)
        - Altri in arrivo...
        """)
        
        st.header("⚙️ Impostazioni")
        max_citations = st.slider("Max citazioni", 10, 50, 25)
        show_progress = st.checkbox("Mostra dettagli", True)
    
    # Area di upload
    st.header("📤 Carica Documento")
    
    uploaded_file = st.file_uploader(
        "Seleziona PDF o DOCX",
        type=['pdf', 'docx'],
        help="Carica il documento contenente la bibliografia"
    )
    
    # Bottone per esempio (opzionale)
    if st.button("🧪 Prova con Esempio"):
        st.info("Per ora carica un file vero. Esempi in arrivo!")
    
    # Processamento del file
    if uploaded_file is not None:
        st.success(f"✅ File caricato: {uploaded_file.name}")
        
        # Pulsante per avviare verifica
        if st.button("🚀 Avvia Verifica Bibliografia", type="primary"):
            
            # Estrai testo dal documento
            with st.spinner("📄 Estrazione testo dal documento..."):
                if uploaded_file.type == "application/pdf":
                    text = extract_text_from_pdf(uploaded_file)
                else:
                    text = extract_text_from_docx(uploaded_file)
            
            if not text.strip():
                st.error("❌ Impossibile estrarre testo dal documento")
                return
            
            # Estrai citazioni
            with st.spinner("🔍 Ricerca citazioni nel documento..."):
                citations = extract_citations(text)
            
            if not citations:
                st.error("❌ Nessuna citazione trovata. Verifica che il documento contenga una bibliografia.")
                return
            
            st.success(f"✅ Trovate {len(citations)} citazioni!")
            
            # Limita citazioni se necessario
            if len(citations) > max_citations:
                citations = citations[:max_citations]
                st.warning(f"⚠️ Analisi limitata alle prime {max_citations} citazioni")
            
            # Mostra anteprima citazioni
            with st.expander("👀 Anteprima Citazioni Estratte"):
                for i, citation in enumerate(citations[:5]):
                    st.markdown(f"**{i+1}.** {citation.original_text[:100]}...")
                if len(citations) > 5:
                    st.markdown(f"... e altre {len(citations)-5} citazioni")
            
            # Verifica citazioni
            st.header("🔍 Verifica in Corso...")
            
            # Progress bar
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            results = []
            
            for i, citation in enumerate(citations):
                # Aggiorna progress
                progress = (i + 1) / len(citations)
                progress_bar.progress(progress)
                status_text.text(f"Verifica citazione {i+1}/{len(citations)}...")
                
                if show_progress:
                    with st.expander(f"🔍 Citazione {i+1} in corso...", expanded=False):
                        st.text(citation.original_text[:100] + "...")
                
                # Verifica citazione
                result = verify_citation(citation)
                result['citation'] = citation
                results.append(result)
                
                # Pausa per evitare sovraccarico API
                time.sleep(1)
            
            # Completa progress
            progress_bar.progress(1.0)
            status_text.text("✅ Verifica completata!")
            
            # RISULTATI
            st.header("📊 Risultati")
            
            # Calcola statistiche
            total = len(results)
            verified = sum(1 for r in results if r['status'] == 'verified')
            errors = sum(1 for r in results if r['status'] == 'error')
            not_found = sum(1 for r in results if r['status'] == 'not_found')
            uncertain = sum(1 for r in results if r['status'] == 'uncertain')
            
            accuracy = (verified / total * 100) if total > 0 else 0
            
            # Metriche principali
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric("📚 Totali", total)
            with col2:
                st.metric("✅ Verificate", verified, f"{accuracy:.1f}%")
            with col3:
                st.metric("❌ Errori", errors)
            with col4:
                st.metric("❓ Non Trovate", not_found)
            
            # Grafico a torta
            if total > 0:
                fig_pie = px.pie(
                    values=[verified, errors, not_found, uncertain],
                    names=['Verificate', 'Errori', 'Non Trovate', 'Incerte'],
                    title="Distribuzione Status Citazioni",
                    color_discrete_map={
                        'Verificate': '#38a169',
                        'Errori': '#e53e3e', 
                        'Non Trovate': '#d69e2e',
                        'Incerte': '#805ad5'
                    }
                )
                st.plotly_chart(fig_pie, use_container_width=True)
            
            # Lista problemi
            problematic = [r for r in results if r['status'] != 'verified']
            
            if problematic:
                st.subheader("🚨 Citazioni Problematiche")
                
                for i, result in enumerate(problematic):
                    with st.expander(f"❌ Problema {i+1}: {result['citation'].original_text[:80]}..."):
                        st.markdown(f"**Status:** {result['status']}")
                        st.markdown(f"**Confidence Score:** {result['score']:.2f}")
                        
                        if result['errors']:
                            st.markdown("**Errori:**")
                            for error in result['errors']:
                                st.markdown(f"- {error}")
                        
                        if result['best_match']:
                            st.markdown("**Miglior match trovato:**")
                            match = result['best_match']
                            st.markdown(f"- **Titolo:** {match['title']}")
                            st.markdown(f"- **Autori:** {', '.join(match['authors'])}")
                            st.markdown(f"- **Anno:** {match['year']}")
            else:
                st.success("🎉 Tutte le citazioni sono state verificate correttamente!")
            
            # Download report
            st.header("📥 Report")
            
            report_data = {
                'metadata': {
                    'filename': uploaded_file.name,
                    'generated_at': datetime.now().isoformat(),
                    'total_citations': total,
                    'accuracy_percentage': accuracy
                },
                'summary': {
                    'verified': verified,
                    'errors': errors,
                    'not_found': not_found,
                    'uncertain': uncertain
                },
                'detailed_results': []
            }
            
            for i, result in enumerate(results):
                citation_data = {
                    'id': i + 1,
                    'original_text': result['citation'].original_text,
                    'status': result['status'],
                    'score': result['score'],
                    'errors': result['errors']
                }
                
                if result['best_match']:
                    citation_data['best_match'] = result['best_match']
                
                report_data['detailed_results'].append(citation_data)
            
            # Bottone download
            report_json = json.dumps(report_data, indent=2, ensure_ascii=False)
            
            st.download_button(
                label="📊 Scarica Report Completo",
                data=report_json,
                file_name=f"bibliography_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                mime="application/json"
            )

if __name__ == "__main__":
    main()
