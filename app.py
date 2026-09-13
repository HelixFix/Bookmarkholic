import os
import time
import sqlite3
import re
import io
import csv
from datetime import datetime
from html.parser import HTMLParser
from flask import Flask, render_template_string, request, redirect, url_for, Response, render_template
from database import get_db, init_db
from datetime import datetime
from collections import Counter
from datetime import datetime



app = Flask(__name__)
DB_NAME = 'bookmarks.sqlite3'

def init_db():
    conn = sqlite3.connect(DB_NAME)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute('''
        CREATE TABLE IF NOT EXISTS bookmarks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT UNIQUE NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            tags TEXT,
            add_date INTEGER NOT NULL DEFAULT 0,
            private INTEGER NOT NULL DEFAULT 0
        )
    ''')
    try:
        conn.execute("ALTER TABLE bookmarks ADD COLUMN add_date INTEGER NOT NULL DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE bookmarks ADD COLUMN private INTEGER NOT NULL DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    conn.commit()
    conn.close()

@app.route('/')
def index():

    search = request.args.get('q', '').strip()
    tag_filter = request.args.get('tag', '').strip()
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    if per_page not in [15, 20, 50, 100]:
        per_page = 20
        
    offset = (page - 1) * per_page
    
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    
    total_items = conn.execute("SELECT COUNT(*) FROM bookmarks").fetchone()[0]
    
    query_conditions = []
    query_params = []
    
    if tag_filter:
        # On découpe le filtre par tag pour traiter chaque mot-clé indépendamment (sans ordre strict)
        tag_words = tag_filter.split()
        for tw in tag_words:
            query_conditions.append("(' ' || LOWER(tags) || ' ') LIKE ?")
            query_params.append(f'% {tw.lower()} %')
        
    if search:
        words = search.split()
        for word in words:
            query_conditions.append("(LOWER(title) LIKE ? OR LOWER(tags) LIKE ? OR LOWER(description) LIKE ? OR LOWER(url) LIKE ?)")
            w_param = f'%{word.lower()}%'
            query_params.extend([w_param, w_param, w_param, w_param])
            
    where_clause = "WHERE " + " AND ".join(query_conditions) if query_conditions else ""
    
    count_sql = f"SELECT COUNT(*) FROM bookmarks {where_clause}"
    filtered_total = conn.execute(count_sql, query_params).fetchone()[0]
    total_pages = max(1, (filtered_total + per_page - 1) // per_page)
    
    select_sql = f"SELECT * FROM bookmarks {where_clause} ORDER BY add_date DESC LIMIT ? OFFSET ?"
    cursor = conn.execute(select_sql, query_params + [per_page, offset])
        
    bookmarks = cursor.fetchall()
    conn.close()

# On réutilise exactement la même logique de formatage pour les dates
    formatted_bookmarks = []
    for b in bookmarks:
        b_dict = dict(b)
        dt = datetime.fromtimestamp(b_dict['add_date'] if b_dict['add_date'] else time.time())
        b_dict['formatted_date'] = dt.strftime('%B %d, %Y %I:%M:%S %p GMT+02:00')
        b_dict['date_str'] = dt.strftime('%Y-%m-%d')
        formatted_bookmarks.append(b_dict)

    # On réutilise ton template principal avec un filtre global ou un titre adapté si besoin
    return render_template_string(
        HTML_TEMPLATE, 
        bookmarks=formatted_bookmarks, 
        search="", 
        tag_filter="", 
        page=1, 
        total_pages=1,
        total_items=len(formatted_bookmarks),
        filtered_total=len(formatted_bookmarks),
        per_page=len(formatted_bookmarks) if formatted_bookmarks else 20
    )
    
    formatted_bookmarks = []
    for b in bookmarks:
        b_dict = dict(b)
        dt = datetime.fromtimestamp(b_dict['add_date'] if b_dict['add_date'] else time.time())
        b_dict['formatted_date'] = dt.strftime('%B %d, %Y %I:%M:%S %p GMT+02:00')
        b_dict['date_str'] = dt.strftime('%Y-%m-%d')  # <--- Ajoute cette ligne ici !
        formatted_bookmarks.append(b_dict)
    
    return render_template_string(
        HTML_TEMPLATE, 
        bookmarks=formatted_bookmarks, 
        search=search, 
        tag_filter=tag_filter, 
        page=page, 
        total_pages=total_pages,
        total_items=total_items,
        filtered_total=filtered_total,
        per_page=per_page
    )

@app.route('/tools')
def tools():
    return render_template_string(TOOLS_TEMPLATE, message=request.args.get('message'))

@app.route('/export/tags-csv')
def export_tags_csv():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.execute("SELECT tags FROM bookmarks WHERE tags IS NOT NULL AND tags != ''")
    rows = cursor.fetchall()
    conn.close()

    tag_counter = Counter()
    for row in rows:
        tags_raw = row[0]
        tags_list = [t.strip().lower() for t in tags_raw.split() if t.strip()]
        tag_counter.update(tags_list)

    # Génération du CSV en mémoire vive (pas de fichier encombrant sur le disque)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Tag", "Occurrences"])

    for tag, count in tag_counter.most_common():
        writer.writerow([tag, count])

    output.seek(0)

    # Retourne le fichier sous forme de téléchargement HTTP
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=tags_occurrences.csv"}
    )

@app.route('/import', methods=['POST'])
def import_bookmarks():
    file = request.files.get('file')
    message = ""
    if file and file.filename.endswith('.html'):
        content = file.read().decode('utf-8', errors='ignore')
        pattern = r'<DT><A\s+HREF="([^"]+)"(?:\s+ADD_DATE="([^"]*)")?(?:\s+LAST_MODIFIED="[^"]*")?(?:\s+PRIVATE="([^"]*)")?(?:\s+TAGS="([^"]*)")?[^>]*>(.*?)</A>(?:\s*<DD>([^<]*(?:<(?!/?DT)[^<]*)*))?'
        matches = re.findall(pattern, content, re.IGNORECASE | re.DOTALL)
        
        imported_count = 0
        conn = sqlite3.connect(DB_NAME)
        
        for match in matches:
            url, add_date_str, private_str, tags_str, title_html, desc_html = match
            if not url:
                continue
                
            title = re.sub(r'<[^>]+>', '', title_html).strip() or url
            description = re.sub(r'<[^>]+>', '', desc_html).strip() if desc_html else ''
            
            try:
                add_date = int(add_date_str) if add_date_str and add_date_str.isdigit() else int(time.time())
            except ValueError:
                add_date = int(time.time())
                
            try:
                private = int(private_str) if private_str and private_str.isdigit() else 0
            except ValueError:
                private = 0
                
            tags_cleaned = " ".join([t.strip() for t in re.split(r'[\s,]+', tags_str) if t.strip()]) if tags_str else ''
            
            try:
                conn.execute(
                    "INSERT INTO bookmarks (url, title, description, tags, add_date, private) VALUES (?, ?, ?, ?, ?, ?)",
                    (url, title, description, tags_cleaned, add_date, private)
                )
                imported_count += 1
            except sqlite3.IntegrityError:
                conn.execute(
                    "UPDATE bookmarks SET title = ?, description = ?, tags = ?, private = ? WHERE url = ?",
                    (title, description, tags_cleaned, private, url)
                )
                imported_count += 1
                
        conn.commit()
        conn.close()
        message = f"Importation réussie : {imported_count} favoris traités."
    else:
        message = "Veuillez fournir un fichier HTML valide."
    return redirect(url_for('tools', message=message))

@app.route('/export')
def export_bookmarks():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    bookmarks = conn.execute("SELECT * FROM bookmarks ORDER BY add_date DESC").fetchall()
    conn.close()
    
    html_out = ['<!DOCTYPE NETSCAPE-Bookmark-file-1>']
    html_out.append('<META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=UTF-8">')
    html_out.append('<TITLE>Bookmarks</TITLE>')
    html_out.append('<H1>Bookmarks</H1>')
    html_out.append('<DL><p>')
    
    for b in bookmarks:
        add_date = b['add_date'] or int(time.time())
        private = b['private'] or 0
        tags = b['tags'] or ''
        title = b['title'] or b['url']
        url = b['url']
        desc = b['description'] or ''
        
        html_out.append(f'    <DT><A HREF="{url}" ADD_DATE="{add_date}" PRIVATE="{private}" TAGS="{tags}">{title}</A>')
        if desc:
            html_out.append(f'    <DD>{desc}')
            
    html_out.append('</DL><p>')
    
    return Response(
        "\n".join(html_out),
        mimetype="text/html",
        headers={"Content-disposition": "attachment; filename=bookmarks_export.html"}
    )

# Nouvelles routes pour les pages utilitaires demandées
@app.route('/rss-recommendations')
def rss_recommendations():
    return render_template_string(RSS_TEMPLATE)

@app.route('/optimize-tags')
def optimize_tags():
    return render_template_string(OPTIMIZE_TAGS_TEMPLATE)

@app.route('/tags-by-year')
def tags_by_year():
    conn = get_db()
    selected_year = request.args.get('year', type=int)
    
    # 1. On récupère tous les add_date pour extraire les années en Python (évite les soucis de version SQLite)
    cursor = conn.execute("SELECT add_date, tags FROM bookmarks WHERE add_date IS NOT NULL")
    rows = cursor.fetchall()
    
    years_set = set()
    tag_counter = Counter()
    
    for row in rows:
        try:
            timestamp = int(row['add_date'])
            dt = datetime.fromtimestamp(timestamp)
            yr = str(dt.year)
            years_set.add(yr)
            
            # 2. Si une année est sélectionnée, on calcule les tags correspondants à la volée
            if selected_year and dt.year == selected_year and row['tags']:
                for t in row['tags'].split():
                    clean_t = t.strip()
                    if clean_t:
                        tag_counter[clean_t] += 1
                        
        except (ValueError, TypeError):
            continue
            
    available_years = sorted(list(years_set), reverse=True)
    tag_cloud = tag_counter.most_common() if selected_year else []
    
    conn.close()
    
    return render_template(
        'tags_by_year.html',
        available_years=available_years,
        selected_year=selected_year,
        tag_cloud=tag_cloud
    )

@app.route('/rename-tags', methods=['GET', 'POST'])
def rename_tags():
    message = None
    if request.method == 'POST':
        old_tag = request.form.get('old_tag', '').strip().lower()
        new_tag = request.form.get('new_tag', '').strip()
        if old_tag and new_tag:
            conn = sqlite3.connect(DB_NAME)
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT id, tags FROM bookmarks").fetchall()
            updated_count = 0
            for r in rows:
                tags = r['tags'] or ''
                tag_list = [t.strip() for t in tags.split() if t.strip()]
                if old_tag in [t.lower() for t in tag_list]:
                    new_list = [new_tag if t.lower() == old_tag else t for t in tag_list]
                    new_tags_str = " ".join(new_list)
                    conn.execute("UPDATE bookmarks SET tags = ? WHERE id = ?", (new_tags_str, r['id']))
                    updated_count += 1
            conn.commit()
            conn.close()
            message = f"Tag renommé avec succès sur {updated_count} favoris."
    return render_template_string(RENAME_TAGS_TEMPLATE, message=message)

# Fonction pour charger la blacklist depuis le fichier txt
def load_blacklist():
    blacklist = set()
    if os.path.exists('blacklist.txt'):
        with open('blacklist.txt', 'r', encoding='utf-8') as f:
            for line in f:
                domain = line.strip().lower()
                if domain and not domain.startswith('#'):
                    blacklist.add(domain)
    return blacklist

@app.route('/top-domains')
def top_domains():
    blacklist = load_blacklist()

    conn = sqlite3.connect(DB_NAME)
    rows = conn.execute("SELECT url, tags FROM bookmarks").fetchall()
    conn.close()

    domains = {}
    tag_domain_counts = {}
    domain_to_tags = {}

    for row in rows:
        url = row[0]
        raw_tags = row[1]

        domain = None
        if url:
            match = re.findall(r'https?://([^/]+)', url)
            if match:
                domain = match[0].lower()
                if domain not in blacklist:
                    domains[domain] = domains.get(domain, 0) + 1

        if raw_tags and domain:
            tags_list = [t.strip().lower() for t in re.split(r'[,;\s]+', str(raw_tags)) if t.strip()]

            for t in tags_list:
                # On ignore purement et simplement le tag no_tag
                if t == 'no_tag':
                    continue

                if domain not in blacklist:
                    if domain not in domain_to_tags:
                        domain_to_tags[domain] = set()
                    domain_to_tags[domain].add(t)

                if t not in tag_domain_counts:
                    tag_domain_counts[t] = {}
                tag_domain_counts[t][domain] = tag_domain_counts[t].get(domain, 0) + 1

    # Top 20 Global des domaines (filtré)
    sorted_domains = sorted(domains.items(), key=lambda x: x[1], reverse=True)[:20]

    # Analyse de tous les tags valides
    all_tag_top_domains = []
    for tag, dom_dict in tag_domain_counts.items():
        sorted_doms_for_tag = sorted(dom_dict.items(), key=lambda x: x[1], reverse=True)

        valid_dom = None
        valid_count = 0
        for dom, count in sorted_doms_for_tag:
            if dom not in blacklist:
                valid_dom = dom
                valid_count = count
                break

        if not valid_dom and sorted_doms_for_tag:
            valid_dom, valid_count = sorted_doms_for_tag[0]

        if valid_dom:
            total_tag_occurrences = sum(dom_dict.values())
            all_tag_top_domains.append((tag, valid_dom, valid_count, total_tag_occurrences))

    # Top 20 des tags (sans no_tag)
    tag_top_domains = sorted(all_tag_top_domains, key=lambda x: x[3], reverse=True)[:20]

    # Domaines leaders (Top 5)
    primary_domain_freq = {}
    for tag, valid_dom, dom_count, total_count in all_tag_top_domains:
        if valid_dom not in blacklist:
            primary_domain_freq[valid_dom] = primary_domain_freq.get(valid_dom, 0) + 1

    sorted_primary_domains = sorted(primary_domain_freq.items(), key=lambda x: x[1], reverse=True)[:5]

    # Domaines les plus polyvalents (Top 5)
    domain_distinct_tags_count = {}
    for dom, tags_set in domain_to_tags.items():
        if dom not in blacklist:
            domain_distinct_tags_count[dom] = len(tags_set)
    sorted_domains_by_tags = sorted(domain_distinct_tags_count.items(), key=lambda x: x[1], reverse=True)[:5]

    return render_template_string(
        TOP_DOMAINS_TEMPLATE,
        domains=sorted_domains,
        tag_top_domains=tag_top_domains,
        sorted_primary_domains=sorted_primary_domains,
        sorted_domains_by_tags=sorted_domains_by_tags
    )

@app.route('/add', methods=['GET', 'POST'])
def add_bookmark():
    conn = get_db()
    
    if request.method == 'POST':
        # Récupération et insertion en base de données
        url = request.form.get('url')
        title = request.form.get('title')
        description = request.form.get('description')
        tags = request.form.get('tags')
        private = 1 if request.form.get('private') else 0
        add_date = int(time.time())
        
        conn.execute('''
            INSERT INTO bookmarks (url, title, description, tags, add_date, private)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET
                title = excluded.title,
                description = excluded.description,
                tags = excluded.tags
        ''', (url, title, description, tags, add_date, private))
        conn.commit()
        conn.close()
        
        # Fermeture automatique de la pop-up du bookmarklet après soumission
        return render_template_string('<script>window.close();</script>')

    # 1. Extraction de tous les tags uniques pour l'autocomplétion (<datalist>)
    cursor = conn.execute("SELECT tags FROM bookmarks WHERE tags IS NOT NULL")
    all_tags = set()
    for row in cursor:
        if row['tags']:
            for t in row['tags'].split():
                if t.strip():
                    all_tags.add(t.strip())
    unique_tags = sorted(list(all_tags))

    # 2. Pré-remplissage via les paramètres GET de l'URL du bookmarklet
    bookmark = {
        'url': request.args.get('url', ''),
        'title': request.args.get('title', ''),
        'description': request.args.get('selection', ''), # Récupère aussi le texte surligné si présent
        'tags': '',
        'private': 0
    }
    
    conn.close()
    return render_template('add.html', bookmark=bookmark, unique_tags=unique_tags)
@app.route('/edit/<int:id>', methods=['GET', 'POST'])
def edit(id):
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    
    if request.method == 'POST':
        url = request.form.get('url')
        title = request.form.get('title') or url
        description = request.form.get('description', '')
        tags = request.form.get('tags', '')
        private = 1 if request.form.get('private') else 0
        tags_cleaned = " ".join([t.strip() for t in re.split(r'[\s,]+', tags) if t.strip()])
        
        conn.execute(
            "UPDATE bookmarks SET url = ?, title = ?, description = ?, tags = ?, private = ? WHERE id = ?",
            (url, title, description, tags_cleaned, private, id)
        )
        conn.commit()
        conn.close()
        return redirect(url_for('index'))
        
    bookmark = conn.execute("SELECT * FROM bookmarks WHERE id = ?", (id,)).fetchone()
    conn.close()
    
    if not bookmark:
        return redirect(url_for('index'))
        
    b_dict = dict(bookmark)
    dt = datetime.fromtimestamp(b_dict['add_date'] if b_dict['add_date'] else time.time())
    b_dict['formatted_date'] = dt.strftime('%B %d, %Y %I:%M:%S %p GMT+01:00')
    
    return render_template_string(EDIT_TEMPLATE, bookmark=b_dict)

@app.route('/delete/<int:id>')
def delete(id):
    conn = sqlite3.connect(DB_NAME)
    conn.execute("DELETE FROM bookmarks WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('index'))

@app.route('/date/<date_str>')
def bookmarks_by_date(date_str):
    try:
        start_dt = datetime.strptime(date_str, '%Y-%m-%d')
        start_timestamp = int(start_dt.timestamp())
        end_timestamp = start_timestamp + 86400  # + 24 heures
    except ValueError:
        return "Format de date invalide", 400

    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row

    # 1. Récupération des favoris de cette journée
    cursor = conn.execute('''
        SELECT * FROM bookmarks 
        WHERE add_date >= ? AND add_date < ?
        ORDER BY add_date DESC
    ''', (start_timestamp, end_timestamp))
    
    bookmarks = cursor.fetchall()

    # 2. Récupérer aussi tous les tags globaux (au cas où le template en a besoin pour la sidebar/les menus)
    all_tags_cursor = conn.execute("SELECT DISTINCT tags FROM bookmarks WHERE tags IS NOT NULL")
    # (Adapte cette ligne selon la façon dont tu récupères tes tags dans index())
    
    conn.close()

    # Formatage des favoris
    formatted_bookmarks = []
    for b in bookmarks:
        b_dict = dict(b)
        dt = datetime.fromtimestamp(b_dict['add_date'] if b_dict['add_date'] else time.time())
        b_dict['formatted_date'] = dt.strftime('%B %d, %Y %I:%M:%S %p GMT+02:00')
        b_dict['date_str'] = dt.strftime('%Y-%m-%d')
        formatted_bookmarks.append(b_dict)

    # 3. On passe TOUTES les variables qu'attend HTML_TEMPLATE (comme dans index())
    return render_template_string(
        HTML_TEMPLATE, 
        bookmarks=formatted_bookmarks, 
        search="", 
        tag_filter="", 
        page=1, 
        total_pages=1,
        total_items=len(formatted_bookmarks),
        filtered_total=len(formatted_bookmarks),
        per_page=20
    )
# Templates HTML

HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <title>Shared Bookmarks</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #dcdfdc; margin: 0; padding: 0; color: #333; }
        header { background: #1b7a43; color: white; padding: 10px 20px; display: flex; justify-content: space-between; align-items: center; font-size: 0.95em; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .header-left, .header-right { display: flex; align-items: center; gap: 20px; }
        header a { color: white; text-decoration: none; font-weight: 500; }
        header a:hover { text-decoration: underline; }
        .stats-block { text-align: right; font-size: 0.85em; line-height: 1.2; font-weight: bold; }
        .container { max-width: 1100px; margin: 20px auto; padding: 0 15px; }
        .card-form { background: white; padding: 20px; margin-bottom: 20px; border-radius: 4px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); border: 1px solid #ccc; display: none; }
        .card-form.active { display: block; }
        .search-bar-container { display: flex; gap: 10px; margin-bottom: 15px; align-items: center; }
        .search-input-wrapper { flex: 1; position: relative; }
        .search-input-wrapper input { width: 100%; padding: 8px 12px; box-sizing: border-box; border: 1px solid #ccc; border-radius: 3px; font-size: 0.95em; background: white; }
        .search-btn { background: #1b7a43; border: none; color: white; padding: 8px 15px; border-radius: 3px; cursor: pointer; font-weight: bold; }
        .search-btn:hover { background: #155d34; }
        .top-nav-bar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; font-size: 0.9em; background: #d2d6d2; padding: 8px 12px; border-radius: 3px; border: 1px solid #bbb; }
        .per-page-links a { margin-left: 5px; text-decoration: none; padding: 2px 6px; border-radius: 3px; color: #333; font-weight: bold; }
        .per-page-links a.active, .per-page-links a:hover { background: #1b7a43; color: white; }
        .results-banner { background: #1b7a43; color: white; padding: 10px 15px; font-weight: bold; font-size: 1.05em; margin-bottom: 15px; border-radius: 3px; }
        .bookmark-card { background: white; border: 1px solid #bbb; border-radius: 3px; margin-bottom: 15px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); padding: 12px 15px; overflow: hidden; position: relative; }
        .bookmark-header { display: flex; align-items: flex-start; gap: 8px; margin-bottom: 6px; }
        .bookmark-link { font-weight: bold; font-size: 1.1em; text-decoration: none; color: #1b7a43; }
        .bookmark-link:hover { text-decoration: underline; }
        .bookmark-desc { margin: 8px 0 12px 0; font-size: 0.9em; color: #2d3748; line-height: 1.4; white-space: pre-wrap; background: #f7fafc; padding: 8px 12px; border-radius: 4px; border: 1px solid #edf2f7; }
        .tag-badge { font-size: 0.8em; background: #e2e8f0; padding: 2px 8px; border-radius: 10px; display: inline-block; margin-right: 5px; text-decoration: none; color: #4a5568; font-weight: 500; }
        .tag-badge:hover { background: #1b7a43; color: white; }
        .private-badge { position: absolute; top: 12px; right: 15px; font-size: 0.75em; background: #fff5f5; color: #c53030; border: 1px solid #feb2b2; padding: 2px 6px; border-radius: 3px; font-weight: bold; }
        .bookmark-footer { display: flex; justify-content: space-between; align-items: center; margin-top: 10px; padding-top: 8px; border-top: 1px solid #eee; font-size: 0.85em; color: #666; gap: 10px; }
        .bookmark-actions { display: flex; align-items: center; gap: 10px; white-space: nowrap; flex-shrink: 0; }
        .bookmark-actions a { text-decoration: none; color: #555; }
        .bookmark-actions a:hover { color: #1b7a43; }
        .bookmark-url-display { color: #444; font-size: 0.9em; display: flex; align-items: center; gap: 4px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 50%; }
        .bookmark-url-display a { color: #1b7a43; text-decoration: none; overflow: hidden; text-overflow: ellipsis; }
        .bookmark-url-display a:hover { text-decoration: underline; }
        .pagination-footer { display: flex; justify-content: center; gap: 15px; margin: 25px 0; font-size: 0.95em; font-weight: bold; }
        .pagination-footer a { background: #1b7a43; color: white; padding: 6px 14px; border-radius: 3px; text-decoration: none; }
    </style>
    <script>
        function toggleAddForm() {
            var form = document.getElementById('add-form-card');
            form.classList.toggle('active');
        }
    </script>
</head>
<body>
    <header>
        <div class="header-left">
            <a href="/" style="font-size: 1.15em; font-weight: bold;">⭐ Shared Bookmarks</a>
            <a href="#" onclick="toggleAddForm(); return false;">➕ Shaare</a>
            <a href="/tools">Outils</a>
        </div>
        <div class="header-right">
            <div class="stats-block">
                <div>{{ total_items }} shaares</div>
            </div>
        </div>
    </header>

    <div class="container">
        <div id="add-form-card" class="card-form">
            <h3 style="color: #1b7a43; margin-top: 0; text-align: center;">Nouveau Shaare</h3>
            <form action="/add" method="POST">
                <label style="font-weight:600; font-size:0.9em; display:block; margin-bottom:4px;">URL</label>
                <input type="text" name="url" required style="width:100%; padding:8px; margin-bottom:12px; border:1px solid #ccc; border-radius:3px;">
                <label style="font-weight:600; font-size:0.9em; display:block; margin-bottom:4px;">Titre</label>
                <input type="text" name="title" style="width:100%; padding:8px; margin-bottom:12px; border:1px solid #ccc; border-radius:3px;">
                <label style="font-weight:600; font-size:0.9em; display:block; margin-bottom:4px;">Description</label>
                <textarea name="description" style="width:100%; height:80px; padding:8px; margin-bottom:12px; border:1px solid #ccc; border-radius:3px;"></textarea>
                <label style="font-weight:600; font-size:0.9em; display:block; margin-bottom:4px;">Tags</label>
                <input type="text" name="tags" placeholder="espaces ou virgules" style="width:100%; padding:8px; margin-bottom:10px; border:1px solid #ccc; border-radius:3px;">
                <div style="margin-bottom: 15px; font-size: 0.9em;"><label><input type="checkbox" name="private" value="1"> Privé</label></div>
                <button type="submit" style="background:#1b7a43; color:white; border:none; padding:10px; width:100%; font-weight:bold; border-radius:3px; cursor:pointer;">Enregistrer</button>
            </form>
        </div>

        <form method="GET" class="search-bar-container">
            <div class="search-input-wrapper"><input type="text" name="q" placeholder="Recherche texte" value="{{ search }}"></div>
            <div class="search-input-wrapper"><input type="text" name="tag" placeholder="Filtrer par tag" value="{{ tag_filter }}"></div>
            <button type="submit" class="search-btn">🔍</button>
            <input type="hidden" name="per_page" value="{{ per_page }}">
        </form>

        <div class="top-nav-bar">
            <div>
                {% if tag_filter or search %}
                <a href="/" style="color: #1b7a43; text-decoration: underline; font-weight:bold;">Réinitialiser les filtres</a>
                {% else %}
                <span>Affichage global</span>
                {% endif %}
            </div>
            <div style="font-weight: bold;">Page {{ page }} / {{ total_pages }}</div>
            <div class="per-page-links">
                Liens par page : 
                <a href="/?per_page=15{% if search %}&q={{ search }}{% endif %}{% if tag_filter %}&tag={{ tag_filter }}{% endif %}" class="{% if per_page == 15 %}active{% endif %}">15</a>
                <a href="/?per_page=20{% if search %}&q={{ search }}{% endif %}{% if tag_filter %}&tag={{ tag_filter }}{% endif %}" class="{% if per_page == 20 %}active{% endif %}">20</a>
                <a href="/?per_page=50{% if search %}&q={{ search }}{% endif %}{% if tag_filter %}&tag={{ tag_filter }}{% endif %}" class="{% if per_page == 50 %}active{% endif %}">50</a>
            </div>
        </div>

        {% for b in bookmarks %}
        <div class="bookmark-card">
            {% if b.private == 1 %}<div class="private-badge">Privé</div>{% endif %}
            <div class="bookmark-header">
                <span style="font-size: 1.1em;">📝</span>
                <a href="{{ b.url }}" target="_blank" class="bookmark-link">{{ b.title }}</a>
            </div>
            {% if b.description %}<div class="bookmark-desc">{{ b.description }}</div>{% endif %}
            {% if b.tags %}
            <div style="margin-bottom: 8px;">
                <span style="font-size: 0.8em;">🏷️</span>
                {% for t in b.tags.replace(',', ' ').split() %}
                    {% if t.strip() %}<a href="/?tag={{ t.strip() }}&per_page={{ per_page }}" class="tag-badge">{{ t.strip() }}</a>{% endif %}
                {% endfor %}
            </div>
            {% endif %}
            <div class="bookmark-footer">
                <div class="bookmark-actions">
                    <input type="checkbox">
                    <a href="/edit/{{ b.id }}" title="Éditer">📝</a>
                    <a href="/delete/{{ b.id }}" title="Supprimer" onclick="return confirm('Confirmer la suppression ?');">🗑️</a>
                    <span>🕒 <a href="/date/{{ b.date_str }}" title="Voir les favoris de ce jour" style="color: inherit; text-decoration: none;">{{ b.formatted_date }}</a></span>
                </div>
                <div class="bookmark-url-display">🔗 <a href="{{ b.url }}" target="_blank">{{ b.url }}</a></div>
            </div>
        </div>
        {% else %}
        <div class="bookmark-card" style="text-align: center; color: #718096; padding: 30px;">Aucun favori trouvé.</div>
        {% endfor %}

        {% if total_pages > 1 %}
        <div class="pagination-footer">
            {% if page > 1 %}<a href="/?page={{ page - 1 }}&per_page={{ per_page }}{% if search %}&q={{ search }}{% endif %}{% if tag_filter %}&tag={{ tag_filter }}{% endif %}">« Précédent</a>{% endif %}
            <span style="background: white; padding: 6px 12px; border: 1px solid #bbb; border-radius: 3px;">Page {{ page }} sur {{ total_pages }}</span>
            {% if page < total_pages %}<a href="/?page={{ page + 1 }}&per_page={{ per_page }}{% if search %}&q={{ search }}{% endif %}{% if tag_filter %}&tag={{ tag_filter }}{% endif %}">Suivant »</a>{% endif %}
        </div>
        {% endif %}
    </div>
</body>
</html>
'''

TOOLS_TEMPLATE = '''
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8"><title>Outils - Shared Bookmarks</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #dcdfdc; margin: 0; padding: 0; color: #333; }
        header { background: #1b7a43; color: white; padding: 10px 20px; display: flex; justify-content: space-between; align-items: center; font-size: 0.95em; }
        header a { color: white; text-decoration: none; font-weight: 500; }
        .container { max-width: 800px; margin: 30px auto; padding: 0 15px; }
        .card { background: white; padding: 25px; border-radius: 4px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); border: 1px solid #ccc; margin-bottom: 20px; }
        h2 { color: #1b7a43; margin-top: 0; font-size: 1.3em; }
        .alert { background: #e6fffa; border: 1px solid #b2f5ea; color: #234e52; padding: 12px; border-radius: 4px; margin-bottom: 20px; text-align: center; }
        .btn-green { background: #1b7a43; color: white; border: none; padding: 8px 15px; font-weight: bold; border-radius: 3px; cursor: pointer; text-decoration: none; display: inline-block; font-size: 0.95em; }
        .btn-green:hover { background: #155d34; }
        ul.tool-links { list-style: none; padding: 0; margin: 0; display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
        ul.tool-links li a { display: block; padding: 10px 12px; background: #f0f2f5; border: 1px solid #ccd9e0; border-radius: 4px; color: #1b7a43; font-weight: bold; text-decoration: none; }
        ul.tool-links li a:hover { background: #1b7a43; color: white; }
    </style>
</head>
<body>
    <header>
        <div><a href="/" style="font-size: 1.15em; font-weight: bold;">⭐ Shared Bookmarks</a> | <a href="/tools">Outils</a></div>
    </header>
    <div class="container">
        {% if message %}<div class="alert">{{ message }}</div>{% endif %}
        
        <div class="card">
            <h2>Pages utilitaires & Analyses</h2>
            <ul class="tool-links">
                <li><a href="/rss-recommendations">📡 rss_recommendations.html</a></li>
                <li><a href="/optimize-tags">🏷️ optimize_tags.html</a></li>
                <li><a href="/tags-by-year">📊 tags_by_year.html</a></li>
                <li><a href="/rename-tags">✏️ rename_tags.html</a></li>
                <li><a href="/top-domains">🌐 top_domains.html</a></li>
            </ul>
        </div>

        <div class="card">
            <h2>Importer des favoris</h2>
            <form action="/import" method="POST" enctype="multipart/form-data">
                <input type="file" name="file" accept=".html" required style="margin-bottom: 15px; display: block;">
                <button type="submit" class="btn-green">Lancer l'importation</button>
            </form>
        </div>

        <div class="card">
            <h2>Exporter les favoris</h2>
            <p style="font-size: 0.9em; color: #555; margin-bottom: 15px;">Téléchargez l'intégralité de vos favoris au format Netscape/Shaarli.</p>
            <a href="/export" class="btn-green">Télécharger l'export HTML</a>
        </div>
        <div class="tool-card">
    <h3>Gestion des Tags</h3>
    <p>Téléchargez la liste de tous vos tags ainsi que leur nombre d'utilisations au format CSV.</p>
    <a href="/export/tags-csv" class="btn-export">
        📥 Exporter les tags (CSV)
    </a>
</div>
    </div>
</body>
</html>
'''

# Templates minimaux pour les nouvelles pages reliées
RSS_TEMPLATE = '''<!DOCTYPE html><html lang="fr"><head><meta charset="UTF-8"><title>Recommandations RSS</title><style>body{font-family:sans-serif;background:#dcdfdc;padding:30px;}.box{background:white;padding:20px;max-width:600px;margin:auto;border-radius:4px;}</style></head><body><div class="box"><h2 style="color:#1b7a43;">📡 Recommandations RSS</h2><p>Flux et suggestions basés sur vos favoris.</p><p><a href="/tools">← Retour aux outils</a></p></div></body></html>'''

OPTIMIZE_TAGS_TEMPLATE = '''<!DOCTYPE html><html lang="fr"><head><meta charset="UTF-8"><title>Optimiser les tags</title><style>body{font-family:sans-serif;background:#dcdfdc;padding:30px;}.box{background:white;padding:20px;max-width:600px;margin:auto;border-radius:4px;}</style></head><body><div class="box"><h2 style="color:#1b7a43;">🏷️ Optimiser les tags</h2><p>Outils de nettoyage et fusion de tags orphelins ou mal orthographiés.</p><p><a href="/tools">← Retour aux outils</a></p></div></body></html>'''

TAGS_BY_YEAR_TEMPLATE = '''<!DOCTYPE html><html lang="fr"><head><meta charset="UTF-8"><title>Tags par année</title><style>body{font-family:sans-serif;background:#dcdfdc;padding:30px;}.box{background:white;padding:20px;max-width:600px;margin:auto;border-radius:4px;}</style></head><body><div class="box"><h2 style="color:#1b7a43;">📊 Historique par année</h2><ul>{% for yr, count in years_data.items() %}<li><b>{{ yr }}</b> : {{ count }} favoris</li>{% endfor %}</ul><p><a href="/tools">← Retour aux outils</a></p></div></body></html>'''

RENAME_TAGS_TEMPLATE = '''<!DOCTYPE html><html lang="fr"><head><meta charset="UTF-8"><title>Renommer un tag</title><style>body{font-family:sans-serif;background:#dcdfdc;padding:30px;}.box{background:white;padding:20px;max-width:600px;margin:auto;border-radius:4px;}</style></head><body><div class="box"><h2 style="color:#1b7a43;">✏️ Renommer un tag</h2>{% if message %}<p style="color:green;font-weight:bold;">{{ message }}</p>{% endif %}<form method="POST"><label>Ancien nom :</label><input type="text" name="old_tag" required style="width:100%;padding:8px;margin-bottom:10px;"><label>Nouveau nom :</label><input type="text" name="new_tag" required style="width:100%;padding:8px;margin-bottom:15px;"><button type="submit" style="background:#1b7a43;color:white;border:none;padding:10px;width:100%;font-weight:bold;cursor:pointer;">Renommer</button></form><p style="margin-top:15px;"><a href="/tools">← Retour aux outils</a></p></div></body></html>'''

TOP_DOMAINS_TEMPLATE = """
<!doctype html>
<html>
<head><title>Top Domaines & Analyses</title></head>
<body style="font-family: sans-serif; background: #e2e8f0; display: flex; justify-content: center; padding: 40px;">
  <div style="background: white; padding: 30px; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); width: 700px;">

    <!-- 1. Top Domaines Global -->
    <h2 style="color: #2f855a;">🌐 Top Domaines (Volume de liens)</h2>
    <ul>
      {% for domain, count in domains %}
        <li><strong>{{ domain }}</strong> : {{ count }} liens</li>
      {% endfor %}
    </ul>

    <!-- 2. Top Tags & Domaine Principal -->
    <h2 style="color: #2b6cb0; margin-top: 30px;">🏷️ Top Tags & Domaine Principal Associé</h2>
    {% if tag_top_domains %}
      <ul>
        {% for tag, top_dom, dom_count, total_count in tag_top_domains %}
          <li>
            <strong>{{ tag }}</strong> ({{ total_count }} occ.)
            ➔ <span style="color: #2c5282; font-weight: bold;">{{ top_dom }}</span>
            <span style="color: #718096; font-size: 0.9em;">({{ dom_count }} fois)</span>
          </li>
        {% endfor %}
      </ul>
    {% endif %}

    <!-- 3. NOUVEAU : Domaines qui structurent le plus de tags (Leaders principaux) -->
    <h2 style="color: #d69e2e; margin-top: 30px;">🏆 Domaines leaders (fréquence en tant que "Top Domaine")</h2>
    <ul>
      {% for domain, count in sorted_primary_domains %}
        <li><strong>{{ domain }}</strong> : leader sur <strong>{{ count }}</strong> tags différents</li>
      {% endfor %}
    </ul>

    <!-- 4. NOUVEAU : Domaines les plus polyvalents (diversité de tags) -->
    <h2 style="color: #805ad5; margin-top: 30px;">🔀 Domaines les plus polyvalents (Diversité de tags)</h2>
    <ul>
      {% for domain, distinct_count in sorted_domains_by_tags %}
        <li><strong>{{ domain }}</strong> : associé à <strong>{{ distinct_count }}</strong> tags uniques différents</li>
      {% endfor %}
    </ul>

    <p style="margin-top: 30px;"><a href="{{ url_for('index') }}" style="color: #553c9a; text-decoration: none;">← Retour aux outils</a></p>
  </div>
</body>
</html>
"""

EDIT_TEMPLATE = '''
<!DOCTYPE html>
<html lang="fr">
<head><meta charset="UTF-8"><title>Modifier le Shaare</title>
<style>
body { font-family: sans-serif; background: #dcdfdc; margin: 0; padding: 20px; }
.card { background: white; padding: 30px; max-width: 600px; margin: auto; border-radius: 4px; border: 1px solid #ccc; }
h2 { color: #1b7a43; text-align: center; margin-top: 0; }
label { display: block; font-weight: 600; margin-bottom: 5px; font-size: 0.9em; }
input[type="text"], textarea { width: 100%; padding: 8px; box-sizing: border-box; border: 1px solid #ccc; border-radius: 3px; margin-bottom: 15px; }
textarea { height: 120px; }
.buttons-row { display: flex; gap: 15px; }
.btn-green { background: #1b7a43; color: white; border: none; padding: 10px; font-weight: bold; border-radius: 3px; cursor: pointer; flex: 1; text-align: center; text-decoration: none; }
.btn-red { background: #a52a2a; color: white; border: none; padding: 10px; font-weight: bold; border-radius: 3px; cursor: pointer; flex: 1; text-align: center; text-decoration: none; }
</style>
</head>
<body>
    <div class="card">
        <h2>Modifier le Shaare</h2>
        <form method="POST">
            <label>URL</label><input type="text" name="url" value="{{ bookmark.url }}" required>
            <label>Titre</label><input type="text" name="title" value="{{ bookmark.title }}">
            <label>Description</label><textarea name="description">{{ bookmark.description or '' }}</textarea>
            <label>Tags</label><input type="text" name="tags" value="{{ bookmark.tags or '' }}">
            <div style="margin-bottom: 15px;"><label><input type="checkbox" name="private" value="1" {% if bookmark.private == 1 %}checked{% endif %}> Privé</label></div>
            <div class="buttons-row">
                <button type="submit" class="btn-green">Enregistrer</button>
                <a href="/delete/{{ bookmark.id }}" class="btn-red" onclick="return confirm('Confirmer la suppression ?');">Supprimer</a>
            </div>
        </form>
        <p style="text-align:center; margin-top:15px;"><a href="/">← Retour à l'accueil</a></p>
    </div>
</body>
</html>
'''

if __name__ == '__main__':
    init_db()
    app.run(debug=True, port=5000)
