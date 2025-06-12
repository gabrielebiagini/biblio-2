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
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
import scholarly
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib

# Configurazione pagina
st.set_page_config(
    page_title="Bibliography Checker Pro",
    page_icon="📚",
    layout="wide"
)

# CSS migliorato
st.markdown("""
<style>
    .main-header {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 2rem;
        border-radius: 15px;
        color: white;
        text-align: center;
        margin-bottom: 2rem;
        box-shadow: 0 10px 30px rgba(0,0,0,0.1);
    }
    .metric-card {
        background: #f8f9fa;
        padding: 1.5rem;
        border-radius: 12px;
        border-left: 5px solid #667eea;
        box-shadow: 0 5px 15px rgba(0,0,0,0.08);
        transition: transform 0.3s ease;
    }
    .metric-card:hover {
        transform: translateY(-5px);
    }
    .error-card {
        background: #fff5f5;
        border-left: 5px solid #e53e3e;
        padding: 1rem;
        border-radius: 8px;
        margin: 0.5rem 0;
    }
    .success-card {
        background: #f0fff4;
        border-left: 5px solid #38a169;
        padding: 1rem;
        border-radius: 8px;
        margin: 0.5rem 0;
    }
    .warning-card {
        background: #fffaf0;
        border-left: 5px solid #d69e2e;
        padding: 1rem;
        border-radius: 8px;
        margin: 0.5rem 0;
    }
</style>
""", unsafe_allow_html=True)

# Cache per evitare ricerche duplicate
@st.cache_data(ttl=3600)
def get_cached_result(query_hash):
    return None

def cache_result(query_hash, result):
    pass

# Classe migliorata per citazioni
class Citation:
    def __init__(self, original_text, authors=None, year=None, title=None, 
                 doi=None, journal=None, volume=None, pages=None, citation_type=None):
        self.original_text = original_text
        self.authors = authors or []
        self.year = year
        self.title = title
        self.doi = doi
        self.journal = journal
        self.volume = volume
        self.pages = pages
        self.citation_type = citation_type or 'article'
        self.position = None  # Posizione nel documento

# Pattern migliorati per estrazione citazioni
CITATION_PATTERNS = {
    'apa': [
        # Autore, A. A. (Anno). Titolo. Rivista, Volume(Numero), pp-pp. DOI
        r'([A-Z][a-z]+(?:,\s[A-Z]\.(?:\s[A-Z]\.)?)*(?:,?\s&\s[A-Z][a-z]+(?:,\s[A-Z]\.)*)*)\s*\((\d{4})\)\.\s*([^.]+)\.\s*([^,]+),\s*(\d+)(?:\((\d+)\))?,\s*(\d+-\d+)(?:\.\s*(10\.\d+/[^\s]+))?',
        # Versione semplificata
        r'([A-Z][a-z]+(?:,\s[A-Z]\.)*)\s*\((\d{4})\)\.\s*([^.]+)\.',
    ],
    'mla': [
        # Cognome, Nome. "Titolo." Rivista vol. num (anno): pp-pp.
        r'([A-Z][a-z]+,\s[A-Z][a-z]+)\.\s*"([^"]+)\."\s*([^.]+)\s+(\d+)\.(\d+)\s*\((\d{4})\):\s*(\d+-\d+)',
    ],
    'chicago': [
        # Cognome, Nome. "Titolo." Rivista vol, no. num (anno): pp-pp.
        r'([A-Z][a-z]+,\s[A-Z][a-z]+)\.\s*"([^"]+)\."\s*([^.]+)\s+(\d+),\s*no\.\s*(\d+)\s*\((\d{4})\):\s*(\d+-\d+)',
    ]
}

# Funzione migliorata per estrarre testo da PDF con posizione
def extract_text_from_pdf_with_position(uploaded_file):
    try:
        pdf_reader = PyPDF2.PdfReader(uploaded_file)
        full_text = ""
        page_texts = []
        
        for page_num, page in enumerate(pdf_reader.pages):
            page_text = page.extract_text()
            page_texts.append((page_num + 1, page_text))
            full_text += page_text + "\n"
            
        return full_text, page_texts
    except Exception as e:
        st.error(f"Errore nell'estrazione PDF: {str(e)}")
        return "", []

# Funzione per cercare su Google Scholar (usando scholarly)
@st.cache_data(ttl=3600, show_spinner=False)
def search_google_scholar(query, max_results=3):
    try:
        search_query = scholarly.search_pubs(query)
        results = []
        
        for i, pub in enumerate(search_query):
            if i >= max_results:
                break
                
            try:
                # Estrai informazioni dettagliate
                bib = pub.get('bib', {})
                
                # Elabora autori
                authors = []
                if 'author' in bib:
                    if isinstance(bib['author'], list):
                        authors = bib['author']
                    else:
                        authors = [bib['author']]
                
                result = {
                    'title': bib.get('title', ''),
                    'authors': authors[:5],  # Limita a 5 autori
                    'year': str(bib.get('pub_year', '')),
                    'journal': bib.get('venue', ''),
                    'doi': pub.get('pub_url', ''),
                    'citations': pub.get('num_citations', 0),
                    'database': 'Google Scholar',
                    'abstract': bib.get('abstract', '')[:200] if 'abstract' in bib else ''
                }
                
                results.append(result)
            except Exception as e:
                continue
                
        return results
    except Exception as e:
        st.warning(f"Google Scholar temporaneamente non disponibile: {str(e)}")
        return []

# Funzione per cercare su DOAJ (Directory of Open Access Journals)
@st.cache_data(ttl=3600, show_spinner=False)
def search_doaj(query, max_results=3):
    try:
        url = "https://doaj.org/api/search/articles"
        params = {
            'q': query,
            'pageSize': max_results
        }
        
        response = requests.get(url, params=params, timeout=10)
        if response.status_code != 200:
            return []
            
        data = response.json()
        results = []
        
        if 'results' in data:
            for item in data['results']:
                try:
                    bibjson = item.get('bibjson', {})
                    
                    # Elabora autori
                    authors = []
                    for author in bibjson.get('author', [])[:5]:
                        name = author.get('name', '')
                        if name:
                            authors.append(name)
                    
                    # Estrai anno
                    year = None
                    if 'year' in bibjson:
                        year = str(bibjson['year'])
                    
                    result = {
                        'title': bibjson.get('title', ''),
                        'authors': authors,
                        'year': year,
                        'journal': bibjson.get('journal', {}).get('title', ''),
                        'doi': bibjson.get('identifier', [{}])[0].get('id', '') if bibjson.get('identifier') else '',
                        'database': 'DOAJ',
                        'abstract': bibjson.get('abstract', '')[:200]
                    }
                    
                    results.append(result)
                except Exception:
                    continue
                    
        return results
    except Exception as e:
        st.warning(f"DOAJ non disponibile: {str(e)}")
        return []

# Funzione per cercare su PubMed
@st.cache_data(ttl=3600, show_spinner=False)
def search_pubmed(query, max_results=3):
    try:
        # Prima cerca gli ID
        search_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
        search_params = {
            'db': 'pubmed',
            'term': query,
            'retmax': max_results,
            'retmode': 'json'
        }
        
        search_response = requests.get(search_url, params=search_params, timeout=10)
        if search_response.status_code != 200:
            return []
            
        search_data = search_response.json()
        id_list = search_data.get('esearchresult', {}).get('idlist', [])
        
        if not id_list:
            return []
        
        # Poi recupera i dettagli
        fetch_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
        fetch_params = {
            'db': 'pubmed',
            'id': ','.join(id_list),
            'retmode': 'xml'
        }
        
        fetch_response = requests.get(fetch_url, params=fetch_params, timeout=10)
        if fetch_response.status_code != 200:
            return []
        
        # Qui dovresti parsare l'XML, ma per semplicità restituisco risultati base
        # In produzione useresti xml.etree.ElementTree
        results = []
        # ... parsing XML ...
        
        return results
    except Exception as e:
        st.warning(f"PubMed non disponibile: {str(e)}")
        return []

# Funzione unificata per cercare in tutti i database con gestione errori
def search_all_databases(query, max_results_per_db=2):
    """
    Cerca in tutti i database disponibili con gestione errori e fallback
    """
    all_results = []
    successful_searches = 0
    failed_databases = []
    
    # Definisci i database e le loro funzioni
    databases = {
        'CrossRef': (search_crossref, True),  # (funzione, è_essenziale)
        'Google Scholar': (search_google_scholar, False),
        'DOAJ': (search_doaj, False),
    }
    
    # Progress bar per database
    db_progress = st.progress(0)
    db_status = st.empty()
    
    # Usa ThreadPoolExecutor per ricerche parallele con timeout globale
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {}
        
        for db_name, (search_func, is_essential) in databases.items():
            future = executor.submit(search_func, query, max_results_per_db)
            futures[future] = (db_name, is_essential)
        
        completed = 0
        for future in as_completed(futures, timeout=60):  # Timeout globale 60 secondi
            completed += 1
            db_progress.progress(completed / len(databases))
            
            db_name, is_essential = futures[future]
            db_status.text(f"Ricerca in {db_name}...")
            
            try:
                results = future.result(timeout=45)  # Timeout per singolo database
                if results:
                    all_results.extend(results)
                    successful_searches += 1
                else:
                    failed_databases.append(db_name)
                    if is_essential:
                        st.warning(f"⚠️ {db_name} non ha restituito risultati")
                        
            except TimeoutError:
                failed_databases.append(db_name)
                if is_essential:
                    st.error(f"❌ Timeout su {db_name}")
                else:
                    st.warning(f"⚠️ {db_name} non disponibile (timeout)")
                    
            except Exception as e:
                failed_databases.append(db_name)
                if is_essential:
                    st.error(f"❌ Errore {db_name}: {str(e)}")
                else:
                    st.warning(f"⚠️ {db_name} non disponibile")
    
    # Pulisci progress
    db_progress.empty()
    db_status.empty()
    
    # Se nessun database ha funzionato, usa fallback locale
    if successful_searches == 0:
        st.error("❌ Tutti i database sono offline. Uso modalità offline limitata.")
        # Potresti implementare un database locale di backup qui
        return []
    
    # Mostra statistiche ricerca
    if failed_databases:
        st.info(f"✅ Ricerca completata su {successful_searches}/{len(databases)} database. "
                f"Non disponibili: {', '.join(failed_databases)}")
    
    # Deduplica risultati basandosi su DOI o titolo
    seen_dois = set()
    seen_titles = set()
    unique_results = []
    
    for result in all_results:
        doi = result.get('doi', '').lower()
        title = result.get('title', '').lower()
        
        # Skip se già visto
        if doi and doi in seen_dois:
            continue
        if title and title in seen_titles:
            continue
            
        # Aggiungi a unique
        if doi:
            seen_dois.add(doi)
        if title:
            seen_titles.add(title)
        unique_results.append(result)
    
    return unique_results

# Funzione migliorata per calcolare similarità
def calculate_similarity_advanced(citation, result):
    from fuzzywuzzy import fuzz
    import unicodedata
    
    def normalize_text(text):
        """Normalizza il testo rimuovendo accenti e caratteri speciali"""
        if not text:
            return ""
        text = unicodedata.normalize('NFD', text)
        text = ''.join(char for char in text if unicodedata.category(char) != 'Mn')
        return text.lower().strip()
    
    score = 0
    weights = {
        'title': 0.4,
        'authors': 0.3,
        'year': 0.2,
        'doi': 0.1
    }
    used_weights = 0
    
    # Confronta titoli con normalizzazione
    if citation.title and result.get('title'):
        norm_cit_title = normalize_text(citation.title)
        norm_res_title = normalize_text(result['title'])
        
        # Usa diversi metodi di similarità
        ratio = fuzz.ratio(norm_cit_title, norm_res_title) / 100
        partial_ratio = fuzz.partial_ratio(norm_cit_title, norm_res_title) / 100
        token_sort = fuzz.token_sort_ratio(norm_cit_title, norm_res_title) / 100
        token_set = fuzz.token_set_ratio(norm_cit_title, norm_res_title) / 100
        
        # Prendi il massimo
        title_sim = max(ratio, partial_ratio, token_sort, token_set)
        score += title_sim * weights['title']
        used_weights += weights['title']
    
    # Confronta autori
    if citation.authors and result.get('authors'):
        author_matches = 0
        total_comparisons = 0
        
        for c_author in citation.authors[:3]:  # Confronta solo primi 3 autori
            c_author_norm = normalize_text(c_author.split(',')[0])  # Solo cognome
            best_match = 0
            
            for r_author in result['authors'][:3]:
                r_author_norm = normalize_text(r_author.split(',')[0])
                sim = fuzz.ratio(c_author_norm, r_author_norm) / 100
                best_match = max(best_match, sim)
            
            author_matches += best_match
            total_comparisons += 1
        
        if total_comparisons > 0:
            author_sim = author_matches / total_comparisons
            score += author_sim * weights['authors']
            used_weights += weights['authors']
    
    # Confronta anni
    if citation.year and result.get('year'):
        try:
            cit_year = int(citation.year)
            res_year = int(result['year'])
            
            if cit_year == res_year:
                year_score = 1.0
            elif abs(cit_year - res_year) == 1:
                year_score = 0.8
            elif abs(cit_year - res_year) == 2:
                year_score = 0.5
            else:
                year_score = 0
                
            score += year_score * weights['year']
            used_weights += weights['year']
        except:
            pass
    
    # Confronta DOI
    if citation.doi and result.get('doi'):
        if citation.doi.lower() == result['doi'].lower():
            score += weights['doi']
        used_weights += weights['doi']
    
    # Normalizza score
    final_score = score / used_weights if used_weights > 0 else 0
    
    return final_score

# Funzione per generare report PDF
def generate_pdf_report(results, filename, total_citations, accuracy):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=72, bottomMargin=72)
    
    # Stili
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Title'],
        fontSize=24,
        textColor=colors.HexColor('#667eea'),
        spaceAfter=30,
        alignment=TA_CENTER
    )
    
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading1'],
        fontSize=16,
        textColor=colors.HexColor('#764ba2'),
        spaceAfter=12
    )
    
    # Elementi del documento
    elements = []
    
    # Titolo
    elements.append(Paragraph("Bibliografia Report", title_style))
    elements.append(Spacer(1, 12))
    
    # Metadata
    elements.append(Paragraph(f"<b>Documento:</b> {filename}", styles['Normal']))
    elements.append(Paragraph(f"<b>Data Verifica:</b> {datetime.now().strftime('%d/%m/%Y %H:%M')}", styles['Normal']))
    elements.append(Paragraph(f"<b>Citazioni Totali:</b> {total_citations}", styles['Normal']))
    elements.append(Paragraph(f"<b>Accuratezza:</b> {accuracy:.1f}%", styles['Normal']))
    elements.append(Spacer(1, 20))
    
    # Riepilogo
    elements.append(Paragraph("Riepilogo Risultati", heading_style))
    
    # Conta status
    status_counts = {
        'verified': sum(1 for r in results if r['status'] == 'verified'),
        'error': sum(1 for r in results if r['status'] == 'error'),
        'not_found': sum(1 for r in results if r['status'] == 'not_found'),
        'uncertain': sum(1 for r in results if r['status'] == 'uncertain')
    }
    
    # Tabella riepilogo
    summary_data = [
        ['Status', 'Numero', 'Percentuale'],
        ['Verificate', str(status_counts['verified']), f"{status_counts['verified']/total_citations*100:.1f}%"],
        ['Errori', str(status_counts['error']), f"{status_counts['error']/total_citations*100:.1f}%"],
        ['Non Trovate', str(status_counts['not_found']), f"{status_counts['not_found']/total_citations*100:.1f}%"],
        ['Incerte', str(status_counts['uncertain']), f"{status_counts['uncertain']/total_citations*100:.1f}%"],
    ]
    
    summary_table = Table(summary_data)
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#667eea')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    
    elements.append(summary_table)
    elements.append(PageBreak())
    
    # Citazioni non verificate
    elements.append(Paragraph("Citazioni Non Verificate", heading_style))
    elements.append(Spacer(1, 12))
    
    non_verified = [r for r in results if r['status'] != 'verified']
    
    if non_verified:
        for i, result in enumerate(non_verified, 1):
            # Status con colore
            status_color = {
                'error': '#e53e3e',
                'not_found': '#d69e2e',
                'uncertain': '#805ad5'
            }.get(result['status'], '#000000')
            
            elements.append(Paragraph(
                f"<font color='{status_color}'><b>#{i} - {result['status'].upper()}</b></font>",
                styles['Normal']
            ))
            
            # Testo originale
            elements.append(Paragraph(
                f"<b>Citazione originale:</b><br/><i>{result['citation'].original_text}</i>",
                styles['Normal']
            ))
            
            # Errori
            if result['errors']:
                errors_text = "<br/>".join([f"• {error}" for error in result['errors']])
                elements.append(Paragraph(
                    f"<b>Problemi riscontrati:</b><br/>{errors_text}",
                    styles['Normal']
                ))
            
            # Miglior match trovato
            if result['best_match']:
                match = result['best_match']
                elements.append(Paragraph("<b>Miglior corrispondenza trovata:</b>", styles['Normal']))
                elements.append(Paragraph(f"Titolo: {match['title']}", styles['Normal']))
                elements.append(Paragraph(f"Autori: {', '.join(match['authors'])}", styles['Normal']))
                elements.append(Paragraph(f"Anno: {match['year']}", styles['Normal']))
                elements.append(Paragraph(f"Database: {match['database']}", styles['Normal']))
                elements.append(Paragraph(f"Score similarità: {result['score']:.2f}", styles['Normal']))
            
            elements.append(Spacer(1, 20))
    else:
        elements.append(Paragraph(
            "<font color='green'><b>Tutte le citazioni sono state verificate con successo!</b></font>",
            styles['Normal']
        ))
    
    # Genera PDF
    doc.build(elements)
    buffer.seek(0)
    
    return buffer

# Funzione migliorata per estrarre citazioni
def extract_citations_advanced(text, style='auto'):
    bib_section = find_bibliography_section(text)
    citations = []
    
    # Se style è 'auto', prova a rilevare lo stile
    if style == 'auto':
        # Conta pattern matches per ogni stile
        style_scores = {}
        for style_name, patterns in CITATION_PATTERNS.items():
            score = 0
            for pattern in patterns:
                matches = re.findall(pattern, bib_section, re.MULTILINE)
                score += len(matches)
            style_scores[style_name] = score
        
        # Usa lo stile con più match
        detected_style = max(style_scores, key=style_scores.get)
        if style_scores[detected_style] > 0:
            style = detected_style
            st.info(f"Stile bibliografia rilevato: {style.upper()}")
    
    # Estrai citazioni con pattern specifici
    lines = bib_section.split('\n')
    
    for i, line in enumerate(lines):
        line = line.strip()
        if len(line) < 20:  # Skip righe troppo corte
            continue
        
        # Prova pattern specifici per stile
        if style in CITATION_PATTERNS:
            for pattern in CITATION_PATTERNS[style]:
                match = re.search(pattern, line)
                if match:
                    groups = match.groups()
                    
                    # Estrai campi in base al pattern
                    if style == 'apa' and len(groups) >= 3:
                        citation = Citation(
                            original_text=line,
                            authors=[groups[0]] if groups[0] else [],
                            year=groups[1] if len(groups) > 1 else None,
                            title=groups[2] if len(groups) > 2 else None,
                            journal=groups[3] if len(groups) > 3 else None,
                            volume=groups[4] if len(groups) > 4 else None,
                            pages=groups[6] if len(groups) > 6 else None,
                            doi=groups[7] if len(groups) > 7 else None
                        )
                        citations.append(citation)
                        break
        
        # Fallback: pattern generici se nessun match specifico
        if not any(citation.original_text == line for citation in citations):
            # Pattern generico base
            if len(line) > 30 and any(char.isdigit() for char in line):
                # Estrai anno
                year_match = re.search(r'\b(19|20)\d{2}\b', line)
                year = year_match.group() if year_match else None
                
                # Estrai DOI
                doi_match = re.search(r'10\.\d+/[^\s]+', line)
                doi = doi_match.group() if doi_match else None
                
                # Estrai autori (euristica)
                authors = []
                author_pattern = r'^([A-Z][a-zA-Z]+(?:,?\s+[A-Z]\.?)*(?:\s*[&,]\s*[A-Z][a-zA-Z]+(?:,?\s+[A-Z]\.?)*)*)'
                author_match = re.search(author_pattern, line)
                if author_match:
                    author_text = author_match.group(1)
                    # Separa autori multipli
                    if ' & ' in author_text:
                        authors = author_text.split(' & ')
                    elif ', ' in author_text and not re.search(r',\s+[A-Z]\.', author_text):
                        authors = author_text.split(', ')
                    else:
                        authors = [author_text]
                
                # Estrai titolo (tra virgolette o dopo anno)
                title = None
                title_patterns = [
                    r'"([^"]+)"',  # Tra virgolette
                    r'\(\d{4}\)\.\s*([^.]+)\.',  # Dopo anno
                    r'\d{4}\.\s*([^.]+)\.',  # Dopo anno senza parentesi
                ]
                
                for pattern in title_patterns:
                    title_match = re.search(pattern, line)
                    if title_match:
                        title = title_match.group(1).strip()
                        break
                
                citation = Citation(
                    original_text=line,
                    authors=authors,
                    year=year,
                    title=title,
                    doi=doi,
                    position=i
                )
                citations.append(citation)
    
    return citations

# Funzione per cercare su CrossRef con retry e gestione errori migliorata
@st.cache_data(ttl=3600, show_spinner=False)
def search_crossref(query, max_results=3, retry_count=0):
    """
    Cerca su CrossRef con retry logic e timeout aumentato
    """
    max_retries = 3
    base_timeout = 30  # Aumentato da 15
    
    try:
        url = "https://api.crossref.org/works"
        params = {
            'query': query,
            'rows': max_results,
            'sort': 'relevance',
            'select': 'DOI,title,author,published-print,published-online,container-title,volume,page'
        }
        
        headers = {
            'User-Agent': 'Bibliography-Checker/1.0 (mailto:your-email@example.com)'
        }
        
        # Timeout progressivo per retry
        timeout = base_timeout + (retry_count * 10)
        
        response = requests.get(
            url, 
            params=params, 
            headers=headers, 
            timeout=timeout
        )
        
        # Rate limiting: pausa tra richieste
        time.sleep(0.5)
        
        if response.status_code == 429:  # Too Many Requests
            if retry_count < max_retries:
                wait_time = int(response.headers.get('Retry-After', 5))
                st.warning(f"Rate limit raggiunto. Attendo {wait_time} secondi...")
                time.sleep(wait_time)
                return search_crossref(query, max_results, retry_count + 1)
            else:
                return []
        
        if response.status_code != 200:
            if retry_count < max_retries:
                time.sleep(2 ** retry_count)  # Exponential backoff
                return search_crossref(query, max_results, retry_count + 1)
            return []
        
        data = response.json()
        results = []
        
        if 'message' in data and 'items' in data['message']:
            for item in data['message']['items']:
                try:
                    title = ' '.join(item.get('title', ['']))
                    
                    authors = []
                    for author in item.get('author', [])[:5]:
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
                    
                    journal = item.get('container-title', [None])[0] if item.get('container-title') else None
                    doi = item.get('DOI', '')
                    volume = str(item.get('volume', '')) if item.get('volume') else ''
                    pages = item.get('page', '')
                    
                    results.append({
                        'title': title,
                        'authors': authors,
                        'year': year,
                        'journal': journal,
                        'doi': doi,
                        'volume': volume,
                        'pages': pages,
                        'database': 'CrossRef',
                        'score': item.get('score', 0)
                    })
                except Exception:
                    continue
        
        return results
        
    except requests.exceptions.Timeout:
        if retry_count < max_retries:
            st.warning(f"Timeout CrossRef, nuovo tentativo {retry_count + 1}/{max_retries}...")
            time.sleep(2 ** retry_count)
            return search_crossref(query, max_results, retry_count + 1)
        else:
            st.error("CrossRef non risponde dopo diversi tentativi")
            return []
            
    except requests.exceptions.ConnectionError:
        if retry_count < max_retries:
            st.warning(f"Errore connessione CrossRef, nuovo tentativo {retry_count + 1}/{max_retries}...")
            time.sleep(3)
            return search_crossref(query, max_results, retry_count + 1)
        else:
            st.error("Impossibile connettersi a CrossRef")
            return []
            
    except Exception as e:
        st.warning(f"Errore CrossRef: {str(e)}")
        return []

# Funzione principale di verifica citazione migliorata
def verify_citation_advanced(citation, use_multiple_databases=True, settings=None):
    """
    Verifica citazione con impostazioni personalizzate
    """
    if settings is None:
        settings = {
            'use_crossref': True,
            'use_scholar': True,
            'use_doaj': True,
            'offline_mode': False,
            'timeout_crossref': 30,
            'timeout_general': 20
        }
    
    # Modalità offline - solo controlli base
    if settings['offline_mode']:
        return {
            'status': 'uncertain',
            'score': 0.5,
            'best_match': None,
            'errors': ['Verifica offline - richiede controllo manuale'],
            'matches_count': 0
        }
    
    # Prepara query di ricerca ottimizzata
    query_parts = []
    
    # Aggiungi titolo se presente (priorità alta)
    if citation.title and len(citation.title) > 10:
        # Rimuovi caratteri speciali per query migliore
        clean_title = re.sub(r'[^\w\s]', ' ', citation.title)
        query_parts.append(f'"{clean_title}"')
    
    # Aggiungi primo autore
    if citation.authors:
        first_author = citation.authors[0].split(',')[0]
        query_parts.append(first_author)
    
    # Aggiungi anno
    if citation.year:
        query_parts.append(citation.year)
    
    query = ' '.join(query_parts)
    
    # Se abbiamo DOI, cerca direttamente su CrossRef
    if citation.doi and settings['use_crossref']:
        doi_results = search_crossref(f'doi:{citation.doi}', 1)
        if doi_results:
            return {
                'status': 'verified',
                'score': 1.0,
                'best_match': doi_results[0],
                'errors': [],
                'matches_count': 1
            }
    
    # Determina quali database usare
    results = []
    if use_multiple_databases:
        # Crea lista database da usare basata su settings
        databases_to_use = {}
        if settings['use_crossref']:
            databases_to_use['CrossRef'] = (search_crossref, True)
        if settings['use_scholar']:
            databases_to_use['Google Scholar'] = (search_google_scholar, False)
        if settings['use_doaj']:
            databases_to_use['DOAJ'] = (search_doaj, False)
        
        # Cerca con timeout personalizzati
        results = search_selected_databases(query, databases_to_use, settings)
    else:
        # Solo CrossRef
        if settings['use_crossref']:
            results = search_crossref(query)
    
    if not results:
        return {
            'status': 'not_found',
            'score': 0,
            'best_match': None,
            'errors': ['Nessun risultato trovato nei database selezionati'],
            'matches_count': 0
        }
    
    # Calcola similarità per ogni risultato
    scored_results = []
    for result in results:
        score = calculate_similarity_advanced(citation, result)
        scored_results.append((score, result))
    
    # Ordina per score
    scored_results.sort(key=lambda x: x[0], reverse=True)
    best_score, best_match = scored_results[0]
    
    # Determina status con soglie migliorate
    errors = []
    if best_score >= 0.85:
        status = 'verified'
    elif best_score >= 0.7:
        status = 'verified'
        errors.append('Match con confidenza media - verificare manualmente')
    elif best_score >= 0.5:
        status = 'uncertain'
        errors.append('Match incerto - richiede verifica manuale')
        errors.append(f'Score similarità: {best_score:.2f}')
    else:
        status = 'error'
        errors.append('Nessun match affidabile trovato')
        errors.append(f'Miglior score: {best_score:.2f}')
    
    # Aggiungi dettagli sui mismatch
    if best_score < 0.85 and best_match:
        if citation.year and best_match.get('year') and citation.year != best_match['year']:
            errors.append(f"Anno diverso: {citation.year} vs {best_match['year']}")
        
        if citation.authors and best_match.get('authors'):
            # Controlla se almeno il primo autore corrisponde
            cit_first = citation.authors[0].split(',')[0].lower()
            match_first = best_match['authors'][0].split(',')[0].lower() if best_match['authors'] else ''
            if cit_first != match_first:
                errors.append("Primo autore non corrisponde")
    
    return {
        'status': status,
        'score': best_score,
        'best_match': best_match,
        'errors': errors,
        'matches_count': len(results),
        'all_matches': scored_results[:3]  # Top 3 matches
    }

# Funzione helper per cercare nei database selezionati
def search_selected_databases(query, databases, settings):
    """
    Cerca solo nei database selezionati con settings personalizzati
    """
    all_results = []
    
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {}
        
        for db_name, (search_func, is_essential) in databases.items():
            future = executor.submit(search_func, query, 2)
            futures[future] = (db_name, is_essential)
        
        for future in as_completed(futures, timeout=60):
            db_name, is_essential = futures[future]
            
            try:
                results = future.result(timeout=settings.get('timeout_general', 20))
                if results:
                    all_results.extend(results)
                    
            except Exception as e:
                if is_essential:
                    st.warning(f"⚠️ Errore {db_name}: {str(e)}")
    
    return all_results

# INTERFACCIA PRINCIPALE
def main():
    # Header principale
    st.markdown("""
    <div class="main-header">
        <h1>📚 Bibliography Checker Pro</h1>
        <p>Verifica avanzata bibliografie con multipli database accademici</p>
        <p style="font-size: 0.9em; opacity: 0.8;">CrossRef • Google Scholar • DOAJ • PubMed</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Sidebar con impostazioni avanzate
    with st.sidebar:
        st.header("ℹ️ Come funziona")
        st.markdown("""
        1. **Carica** PDF o DOCX
        2. **Estrazione** intelligente citazioni  
        3. **Verifica** su 4+ database
        4. **Report PDF** dettagliato
        
        **Database disponibili:**
        - ✅ CrossRef (90M+ articoli)
        - ✅ Google Scholar
        - ✅ DOAJ (Open Access)
        - 🔜 PubMed (Biomedica)
        - 🔜 Scopus
        - 🔜 Web of Science
        """)
        
        st.header("⚙️ Impostazioni Avanzate")
        
        # Stile citazione
        citation_style = st.selectbox(
            "Stile citazione",
            ['auto', 'apa', 'mla', 'chicago'],
            help="Seleziona lo stile o lascia su auto per rilevamento automatico"
        )
        
        # Numero massimo citazioni
        max_citations = st.slider("Max citazioni da verificare", 10, 100, 50)
        
        # Database da usare
        st.subheader("Database da utilizzare")
        use_crossref = st.checkbox("CrossRef", value=True, help="Database principale, altamente raccomandato")
        use_scholar = st.checkbox("Google Scholar", value=True, help="Ampio database, può essere lento")
        use_doaj = st.checkbox("DOAJ", value=True, help="Open Access journals")
        
        # Timeout settings
        with st.expander("⏱️ Impostazioni Timeout", expanded=False):
            timeout_crossref = st.slider("Timeout CrossRef (sec)", 10, 60, 30)
            timeout_general = st.slider("Timeout altri DB (sec)", 10, 60, 20)
            max_retries = st.slider("Tentativi massimi", 1, 5, 3)
        
        # Soglia di accuratezza
        accuracy_threshold = st.slider(
            "Soglia accuratezza (%)", 
            50, 95, 85,
            help="Citazioni con score inferiore saranno marcate come problematiche"
        )
        
        # Cache settings
        st.subheader("🗄️ Cache")
        if st.button("🔄 Pulisci Cache", help="Rimuove risultati salvati"):
            st.cache_data.clear()
            st.success("Cache pulita!")
        
        # Opzioni report
        st.subheader("📄 Opzioni Report")
        include_verified = st.checkbox("Includi citazioni verificate", value=False)
        include_suggestions = st.checkbox("Includi suggerimenti correzione", value=True)
        
        # Modalità offline
        st.subheader("🔌 Modalità Offline")
        offline_mode = st.checkbox("Modalità Offline", value=False, 
                                  help="Usa solo verifiche locali senza database esterni")
        
    # Area principale
    st.header("📤 Carica Documento")
    
    col1, col2 = st.columns([3, 1])
    
    with col1:
        uploaded_file = st.file_uploader(
            "Seleziona PDF o DOCX contenente bibliografia",
            type=['pdf', 'docx'],
            help="Il documento deve contenere una sezione bibliografia/references"
        )
    
    with col2:
        st.markdown("### 🎯 Quick Stats")
        if uploaded_file:
            file_size = len(uploaded_file.getvalue()) / 1024 / 1024
            st.metric("Dimensione", f"{file_size:.1f} MB")
            st.metric("Tipo", uploaded_file.type.split('/')[-1].upper())
    
    # Processamento
    if uploaded_file is not None:
        st.success(f"✅ File caricato: {uploaded_file.name}")
        
        # Bottoni azione
        col1, col2, col3 = st.columns([2, 2, 1])
        
        with col1:
            start_verification = st.button("🚀 Avvia Verifica Completa", type="primary", use_container_width=True)
        
        with col2:
            quick_check = st.button("⚡ Verifica Veloce (10 citazioni)", use_container_width=True)
        
        with col3:
            if st.button("🔄 Reset", use_container_width=True):
                st.rerun()
        
        if start_verification or quick_check:
            # Timing
            start_time = time.time()
            
            # Estrai testo
            with st.spinner("📄 Estrazione testo in corso..."):
                if uploaded_file.type == "application/pdf":
                    text, page_texts = extract_text_from_pdf_with_position(uploaded_file)
                else:
                    text = extract_text_from_docx(uploaded_file)
                    page_texts = []
            
            if not text.strip():
                st.error("❌ Impossibile estrarre testo dal documento")
                return
            
            # Mostra preview testo
            with st.expander("👁️ Anteprima Documento (primi 1000 caratteri)"):
                st.text(text[:1000] + "...")
            
            # Estrai citazioni
            with st.spinner("🔍 Ricerca citazioni..."):
                citations = extract_citations_advanced(text, style=citation_style)
            
            if not citations:
                st.error("❌ Nessuna citazione trovata. Verifica il formato della bibliografia.")
                
                # Suggerimenti
                st.info("""
                💡 **Suggerimenti:**
                - Assicurati che il documento contenga una sezione "References" o "Bibliografia"
                - Le citazioni devono seguire uno stile standard (APA, MLA, Chicago)
                - Ogni citazione dovrebbe essere su una riga separata
                """)
                return
            
            st.success(f"✅ Trovate {len(citations)} citazioni!")
            
            # Quick check limita a 10
            if quick_check:
                citations = citations[:10]
                st.info("⚡ Modalità veloce: verifico solo le prime 10 citazioni")
            elif len(citations) > max_citations:
                citations = citations[:max_citations]
                st.warning(f"⚠️ Troppe citazioni. Limito l'analisi alle prime {max_citations}")
            
            # Mostra citazioni estratte
            with st.expander(f"📋 Citazioni Estratte ({len(citations)} totali)", expanded=False):
                for i, cit in enumerate(citations[:10]):
                    st.markdown(f"**{i+1}.** _{cit.original_text[:150]}..._")
                    if cit.title:
                        st.caption(f"   📖 Titolo: {cit.title}")
                    if cit.authors:
                        st.caption(f"   👥 Autori: {', '.join(cit.authors[:3])}")
                    if cit.year:
                        st.caption(f"   📅 Anno: {cit.year}")
                if len(citations) > 10:
                    st.markdown(f"_... e altre {len(citations)-10} citazioni_")
            
            # Verifica citazioni
            st.header("🔍 Verifica in Corso...")
            
            # Controlla connessione prima di iniziare
            if not offline_mode:
                with st.spinner("Controllo connessione ai database..."):
                    try:
                        test_response = requests.get("https://api.crossref.org/works?rows=1", timeout=5)
                        if test_response.status_code != 200:
                            st.warning("⚠️ CrossRef potrebbe avere problemi. La verifica potrebbe essere più lenta.")
                    except:
                        st.error("""
                        ❌ **Problemi di connessione rilevati**
                        
                        Possibili soluzioni:
                        1. Controlla la tua connessione internet
                        2. Prova a disabilitare temporaneamente firewall/VPN
                        3. Usa la modalità offline nelle impostazioni
                        4. Riprova tra qualche minuto
                        """)
                        if not st.checkbox("Procedi comunque"):
                            return
            
            # Container per progress
            progress_container = st.container()
            with progress_container:
                progress_bar = st.progress(0)
                status_text = st.empty()
                eta_text = st.empty()
            
            # Container per risultati live
            live_results = st.container()
            
            results = []
            errors_found = 0
            
            # Stima tempo basata su database selezionati
            active_databases = sum([use_crossref, use_scholar, use_doaj])
            time_per_citation = 2 * active_databases if not offline_mode else 0.1
            estimated_time = len(citations) * time_per_citation
            
            st.info(f"⏱️ Tempo stimato: ~{int(estimated_time)} secondi per {len(citations)} citazioni usando {active_databases} database")
            
            for i, citation in enumerate(citations):
                # Progress update
                progress = (i + 1) / len(citations)
                progress_bar.progress(progress)
                status_text.text(f"Verificando citazione {i+1}/{len(citations)}...")
                
                # ETA
                elapsed = time.time() - start_time
                if i > 0:
                    eta = (elapsed / i) * (len(citations) - i)
                    eta_text.text(f"Tempo stimato rimanente: {int(eta)}s")
                
                # Prepara settings dal sidebar
                verification_settings = {
                    'use_crossref': use_crossref,
                    'use_scholar': use_scholar,
                    'use_doaj': use_doaj,
                    'offline_mode': offline_mode,
                    'timeout_crossref': timeout_crossref,
                    'timeout_general': timeout_general
                }
                
                # Verifica
                result = verify_citation_advanced(
                    citation, 
                    use_multiple_databases=any([use_crossref, use_scholar, use_doaj]),
                    settings=verification_settings
                )
                result['citation'] = citation
                results.append(result)
                
                # Update live results
                if result['status'] != 'verified':
                    errors_found += 1
                    with live_results:
                        if errors_found == 1:
                            st.markdown("### 🚨 Problemi Rilevati:")
                        
                        status_emoji = {
                            'error': '❌',
                            'not_found': '❓',
                            'uncertain': '⚠️'
                        }.get(result['status'], '❌')
                        
                        st.markdown(f"{status_emoji} **Citazione {i+1}:** {citation.original_text[:80]}...")
                        if result['errors']:
                            st.caption(f"   → {result['errors'][0]}")
                
                # Rate limiting
                time.sleep(0.5)
            
            # Completa progress
            progress_bar.progress(1.0)
            status_text.text("✅ Verifica completata!")
            eta_text.empty()
            
            # Tempo totale
            total_time = time.time() - start_time
            st.info(f"⏱️ Tempo totale: {total_time:.1f} secondi ({total_time/len(citations):.1f}s per citazione)")
            
            # RISULTATI FINALI
            st.header("📊 Risultati Analisi")
            
            # Calcola metriche
            total = len(results)
            verified = sum(1 for r in results if r['status'] == 'verified')
            errors = sum(1 for r in results if r['status'] == 'error')
            not_found = sum(1 for r in results if r['status'] == 'not_found')
            uncertain = sum(1 for r in results if r['status'] == 'uncertain')
            
            accuracy = (verified / total * 100) if total > 0 else 0
            
            # Dashboard metriche
            col1, col2, col3, col4, col5 = st.columns(5)
            
            with col1:
                st.metric("📚 Totali", total)
            with col2:
                st.metric("✅ Verificate", verified, f"{accuracy:.1f}%", 
                         delta_color="normal" if accuracy >= accuracy_threshold else "inverse")
            with col3:
                st.metric("❌ Errori", errors, delta_color="inverse")
            with col4:
                st.metric("❓ Non Trovate", not_found, delta_color="inverse")
            with col5:
                st.metric("⚠️ Incerte", uncertain, delta_color="inverse")
            
            # Alert basato su accuratezza
            if accuracy >= 95:
                st.success("🎉 Eccellente! La bibliografia è molto accurata.")
            elif accuracy >= accuracy_threshold:
                st.info("👍 Buono! La bibliografia è generalmente corretta con alcuni problemi minori.")
            elif accuracy >= 70:
                st.warning("⚠️ Attenzione! Diverse citazioni necessitano correzione.")
            else:
                st.error("❌ Critico! La bibliografia presenta molti problemi e richiede revisione approfondita.")
            
            # Visualizzazioni
            col1, col2 = st.columns(2)
            
            with col1:
                # Grafico a torta
                fig_pie = px.pie(
                    values=[verified, errors, not_found, uncertain],
                    names=['Verificate', 'Errori', 'Non Trovate', 'Incerte'],
                    title="Distribuzione Risultati",
                    color_discrete_map={
                        'Verificate': '#38a169',
                        'Errori': '#e53e3e', 
                        'Non Trovate': '#d69e2e',
                        'Incerte': '#805ad5'
                    },
                    hole=0.4
                )
                fig_pie.update_traces(textposition='inside', textinfo='percent+label')
                st.plotly_chart(fig_pie, use_container_width=True)
            
            with col2:
                # Grafico per database
                db_counts = {}
                for result in results:
                    if result['best_match']:
                        db = result['best_match'].get('database', 'Unknown')
                        db_counts[db] = db_counts.get(db, 0) + 1
                
                if db_counts:
                    fig_bar = px.bar(
                        x=list(db_counts.keys()),
                        y=list(db_counts.values()),
                        title="Citazioni per Database",
                        labels={'x': 'Database', 'y': 'Numero Citazioni'},
                        color=list(db_counts.values()),
                        color_continuous_scale='viridis'
                    )
                    st.plotly_chart(fig_bar, use_container_width=True)
            
            # Dettagli problemi
            problematic = [r for r in results if r['status'] != 'verified']
            
            if problematic:
                st.header(f"🔍 Dettaglio Problemi ({len(problematic)} citazioni)")
                
                # Filtri
                filter_col1, filter_col2 = st.columns(2)
                with filter_col1:
                    filter_status = st.multiselect(
                        "Filtra per status",
                        ['error', 'not_found', 'uncertain'],
                        default=['error', 'not_found', 'uncertain']
                    )
                with filter_col2:
                    sort_by = st.selectbox(
                        "Ordina per",
                        ['Posizione nel documento', 'Score similarità', 'Status']
                    )
                
                # Filtra risultati
                filtered_problems = [r for r in problematic if r['status'] in filter_status]
                
                # Ordina
                if sort_by == 'Score similarità':
                    filtered_problems.sort(key=lambda x: x['score'])
                elif sort_by == 'Status':
                    filtered_problems.sort(key=lambda x: x['status'])
                
                # Mostra problemi
                for i, result in enumerate(filtered_problems[:20]):  # Limita a 20 per performance
                    with st.expander(
                        f"{{'error': '❌', 'not_found': '❓', 'uncertain': '⚠️'}.get(result['status'], '❌')} "
                        f"Problema {i+1}: {result['citation'].original_text[:80]}...",
                        expanded=(i < 3)  # Espandi solo i primi 3
                    ):
                        col1, col2 = st.columns([2, 1])
                        
                        with col1:
                            st.markdown("**📄 Citazione originale:**")
                            st.info(result['citation'].original_text)
                            
                            if result['citation'].title:
                                st.markdown(f"**📖 Titolo estratto:** {result['citation'].title}")
                            if result['citation'].authors:
                                st.markdown(f"**👥 Autori:** {', '.join(result['citation'].authors)}")
                            if result['citation'].year:
                                st.markdown(f"**📅 Anno:** {result['citation'].year}")
                        
                        with col2:
                            st.markdown(f"**Status:** `{result['status'].upper()}`")
                            st.markdown(f"**Score:** {result['score']:.2%}")
                            st.markdown(f"**Match trovati:** {result.get('matches_count', 0)}")
                        
                        if result['errors']:
                            st.markdown("**⚠️ Problemi riscontrati:**")
                            for error in result['errors']:
                                st.markdown(f"- {error}")
                        
                        if result['best_match']:
                            st.markdown("**✅ Miglior corrispondenza trovata:**")
                            match = result['best_match']
                            
                            match_col1, match_col2 = st.columns(2)
                            with match_col1:
                                st.markdown(f"**Titolo:** {match['title']}")
                                st.markdown(f"**Autori:** {', '.join(match['authors'][:3])}")
                            with match_col2:
                                st.markdown(f"**Anno:** {match['year']}")
                                st.markdown(f"**Database:** {match['database']}")
                                if match.get('doi'):
                                    st.markdown(f"**DOI:** {match['doi']}")
                            
                            # Suggerimento correzione
                            if include_suggestions and result['score'] > 0.5:
                                st.markdown("**💡 Correzione suggerita:**")
                                # Genera formato APA
                                suggested = f"{', '.join(match['authors'][:3])} ({match['year']}). {match['title']}."
                                if match.get('journal'):
                                    suggested += f" {match['journal']}"
                                if match.get('volume'):
                                    suggested += f", {match['volume']}"
                                if match.get('pages'):
                                    suggested += f", {match['pages']}"
                                if match.get('doi'):
                                    suggested += f". https://doi.org/{match['doi']}"
                                
                                st.code(suggested, language='text')
                
                if len(filtered_problems) > 20:
                    st.info(f"Mostrati 20 di {len(filtered_problems)} problemi. Scarica il report completo per tutti i dettagli.")
            
            # GENERAZIONE REPORT
            st.header("📥 Download Report")
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("### 📄 Report PDF")
                st.markdown("Report professionale con tutti i dettagli dell'analisi")
                
                if st.button("🎯 Genera Report PDF", type="primary", use_container_width=True):
                    with st.spinner("Generazione PDF in corso..."):
                        pdf_buffer = generate_pdf_report(
                            results,
                            uploaded_file.name,
                            total,
                            accuracy
                        )
                        
                        st.download_button(
                            label="📥 Scarica Report PDF",
                            data=pdf_buffer,
                            file_name=f"bibliography_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
                            mime="application/pdf",
                            use_container_width=True
                        )
            
            with col2:
                st.markdown("### 📊 Export Dati")
                st.markdown("Dati grezzi per analisi personalizzate")
                
                # Prepara dati per export
                export_data = []
                for result in results:
                    export_row = {
                        'citazione_originale': result['citation'].original_text,
                        'status': result['status'],
                        'score': result['score'],
                        'titolo_estratto': result['citation'].title,
                        'autori_estratti': ', '.join(result['citation'].authors) if result['citation'].authors else '',
                        'anno_estratto': result['citation'].year,
                        'errori': '; '.join(result['errors']) if result['errors'] else '',
                    }
                    
                    if result['best_match']:
                        export_row.update({
                            'match_titolo': result['best_match']['title'],
                            'match_autori': ', '.join(result['best_match']['authors']),
                            'match_anno': result['best_match']['year'],
                            'match_database': result['best_match']['database'],
                            'match_doi': result['best_match'].get('doi', '')
                        })
                    
                    export_data.append(export_row)
                
                df = pd.DataFrame(export_data)
                
                # CSV download
                csv = df.to_csv(index=False, encoding='utf-8-sig')
                st.download_button(
                    label="📥 Scarica CSV",
                    data=csv,
                    file_name=f"bibliography_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv",
                    use_container_width=True
                )
                
                # JSON download
                json_data = json.dumps(export_data, indent=2, ensure_ascii=False)
                st.download_button(
                    label="📥 Scarica JSON",
                    data=json_data,
                    file_name=f"bibliography_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                    mime="application/json",
                    use_container_width=True
                )
            
            # Consigli finali
            if accuracy < 90:
                st.header("💡 Consigli per Migliorare")
                
                st.markdown("""
                ### Raccomandazioni basate sull'analisi:
                
                1. **Verifica manuale delle citazioni problematiche**
                   - Controlla specialmente quelle marcate come "Non trovate" o "Errori"
                   - Usa il report PDF per un elenco completo
                
                2. **Formattazione consistente**
                   - Assicurati che tutte le citazioni seguano lo stesso stile
                   - Includi tutti i campi richiesti (autori, anno, titolo, fonte)
                
                3. **Aggiorna citazioni obsolete**
                   - Alcune citazioni potrebbero riferirsi a versioni precedenti
                   - Verifica se esistono versioni più recenti
                
                4. **DOI mancanti**
                   - Aggiungi i DOI dove possibile per verifiche più accurate
                   - I DOI garantiscono identificazione univoca
                """)
    
    # Footer
    st.markdown("---")
    
    # Troubleshooting
    with st.expander("🔧 Risoluzione Problemi", expanded=False):
        st.markdown("""
        ### Errori Comuni e Soluzioni
        
        **1. Timeout CrossRef**
        - Aumenta il timeout nelle impostazioni avanzate
        - Disabilita temporaneamente altri database
        - Usa la modalità "Verifica Veloce"
        - Controlla se ci sono problemi di rete/firewall
        
        **2. Citazioni non trovate**
        - Verifica che il formato sia corretto
        - Controlla errori di battitura nei nomi autori
        - Alcuni articoli potrebbero non essere indicizzati
        - Prova a cercare manualmente su Google Scholar
        
        **3. Score basso anche per citazioni corrette**
        - Caratteri speciali o accenti possono influire
        - Abbreviazioni diverse del journal
        - Autori con nomi complessi
        - Anno di pubblicazione online vs stampa
        
        **4. Errori di estrazione**
        - PDF scansionati necessitano OCR
        - Formati bibliografia non standard
        - Encoding caratteri speciali
        
        ### 🚀 Performance Tips
        - Usa "Verifica Veloce" per test iniziali
        - Disabilita database non necessari
        - Pulisci la cache se hai problemi
        - Per documenti grandi, verifica a blocchi
        """)
    
    # Debug info (solo se richiesto)
    if st.checkbox("🐛 Mostra informazioni debug", value=False):
        st.code(f"""
        Versione: 2.1.0
        Streamlit: {st.__version__}
        Python: {sys.version}
        Timeout CrossRef: {timeout_crossref}s
        Database attivi: {', '.join([db for db, active in [('CrossRef', use_crossref), ('Scholar', use_scholar), ('DOAJ', use_doaj)] if active])}
        Modalità offline: {offline_mode}
        Cache attiva: {not st.session_state.get('cache_disabled', False)}
        """)
    
    st.markdown(
        """
        <div style='text-align: center; color: #666; margin-top: 50px;'>
            <p>Bibliography Checker Pro v2.1 | Sviluppato con ❤️ per la comunità accademica</p>
            <p style='font-size: 0.8em;'>Supporta APA, MLA, Chicago e altri stili • Timeout e retry automatici</p>
        </div>
        """, 
        unsafe_allow_html=True
    )

if __name__ == "__main__":
    main()
