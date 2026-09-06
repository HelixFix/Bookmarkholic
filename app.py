import os
import time
import sqlite3
import re
from datetime import datetime
from html.parser import HTMLParser
from flask import Flask, render_template_string, request, redirect, url_for, Response

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

# Parseur HTML pour importer les fichiers de bookmarks Netscape / Shaarli
class NetscapeBookmarkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.bookmarks = []
        self.current_bookmark = None
        self.in_a = False
        self.in_dd = False
        self.current_title = []
        self.current_desc = []

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        attrs_dict = {k.lower(): v for k, v in attrs}
        
        if tag == 'a':
            if self.current_bookmark:
                self.save_current()
            
            self.current_bookmark = {
                'url': attrs_dict.get('href', ''),
                'add_date': int(attrs_dict.get('add_date', time.time())),
                'private': int(attrs_dict.get('private', 0)),
                'tags': attrs_dict.get('tags', '')
            }
            self.in_a = True
            self.current_title = []
        elif tag == 'dd':
            # On commence à lire la description
            self.in_dd = True
            self.current_desc = []
        elif tag in ['dt', 'dl', 'p'] and self.in_dd:
            # Si on rencontre un nouveau bloc alors qu'on était dans un <DD> sans balise </DD> fermante, on clot la description
            self.in_dd = False
            if self.current_bookmark:
                self.current_bookmark['description'] = "".join(self.current_desc).strip()

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag == 'a':
            self.in_a = False
            if self.current_bookmark:
                self.current_bookmark['title'] = "".join(self.current_title).strip()
        elif tag == 'dd':
            self.in_dd = False
            if self.current_bookmark:
                self.current_bookmark['description'] = "".join(self.current_desc).strip()
        elif tag == 'dt':
            if self.current_bookmark and not self.in_dd:
                self.save_current()

    def handle_data(self, data):
        if self.in_a:
            self.current_title.append(data)
        elif self.in_dd:
            self.current_desc.append(data)

    def save_current(self):
        if self.current_bookmark:
            if self.in_dd:
                self.current_bookmark['description'] = "".join(self.current_desc).strip()
                self.in_dd = False
            if 'title' not in self.current_bookmark or not self.current_bookmark['title']:
                self.current_bookmark['title'] = self.current_bookmark.get('url', '')
            if 'description' not in self.current_bookmark:
                self.current_bookmark['description'] = ''
            self.bookmarks.append(self.current_bookmark)
            self.current_bookmark = None
            self.current_desc = []

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
        query_conditions.append("(' ' || LOWER(tags) || ' ') LIKE ?")
        query_params.append(f'% {tag_filter.lower()} %')
        
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
    
    formatted_bookmarks = []
    for b in bookmarks:
        b_dict = dict(b)
        dt = datetime.fromtimestamp(b_dict['add_date'] if b_dict['add_date'] else time.time())
        b_dict['formatted_date'] = dt.strftime('%B %d, %Y %I:%M:%S %p GMT+02:00')
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

@app.route('/tools', methods=['GET', 'POST'])
def tools():
    message = None
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'import':
            file = request.files.get('file')
            if file and file.filename.endswith('.html'):
                content = file.read().decode('utf-8', errors='ignore')
                
                # Expression régulière pour capturer chaque bloc de favori Shaarli/Netscape
                # Elle extrait l'URL, add_date, private, tags, titre et la description optionnelle (<DD>)
                pattern = r'<DT><A\s+HREF="([^"]+)"(?:\s+ADD_DATE="([^"]*)")?(?:\s+LAST_MODIFIED="[^"]*")?(?:\s+PRIVATE="([^"]*)")?(?:\s+TAGS="([^"]*)")?[^>]*>(.*?)</A>(?:\s*<DD>([^<]*(?:<(?!/?DT)[^<]*)*))?'
                
                matches = re.findall(pattern, content, re.IGNORECASE | re.DOTALL)
                
                imported_count = 0
                conn = sqlite3.connect(DB_NAME)
                
                for match in matches:
                    url, add_date_str, private_str, tags_str, title_html, desc_html = match
                    if not url:
                        continue
                        
                    # Nettoyage des balises HTML internes potentielles dans le titre ou la description
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

    return render_template_string(TOOLS_TEMPLATE, message=message)

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
    
    output_content = "\n".join(html_out)
    return Response(
        output_content,
        mimetype="text/html",
        headers={"Content-disposition": "attachment; filename=bookmarks_export.html"}
    )

@app.route('/add', methods=['GET', 'POST'])
def add_bookmark():
    if request.method == 'POST':
        # Traitement de l'enregistrement classique (quand on valide le formulaire)
        url = request.form.get('url')
        title = request.form.get('title')
        description = request.form.get('desc')
        tags = request.form.get('tags', '')
        
        # ... (votre code existant pour insérer dans SQLite) ...
        return redirect(url_for('index'))
        
    else:
        # Requete GET : C'est ce que le bookmarklet appelle pour ouvrir la fenetre
        # On recupere les infos transmises dans l'URL par le bookmarklet
        url = request.args.get('url', '')
        title = request.args.get('title', '')
        desc = request.args.get('desc', '')
        
        return render_template('add.html', url=url, title=title, desc=desc)

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

@app.route('/bookmarklet', methods=['GET', 'POST'])
def bookmarklet():
    if request.method == 'POST':
        url = request.form.get('url')
        title = request.form.get('title') or url
        description = request.form.get('description', '')
        tags = request.form.get('tags', '')
        private = 1 if request.form.get('private') else 0
        add_date = int(time.time())
        
        tags_cleaned = " ".join([t.strip() for t in re.split(r'[\s,]+', tags) if t.strip()])
        
        conn = sqlite3.connect(DB_NAME)
        try:
            conn.execute(
                "INSERT INTO bookmarks (url, title, description, tags, add_date, private) VALUES (?, ?, ?, ?, ?, ?)",
                (url, title, description, tags_cleaned, add_date, private)
            )
            conn.commit()
        except sqlite3.IntegrityError:
            conn.execute(
                "UPDATE bookmarks SET title = ?, description = ?, tags = ?, private = ? WHERE url = ?",
                (title, description, tags_cleaned, private, url)
            )
            conn.commit()
        conn.close()
        return "<script>window.close();</script><p style='text-align:center; font-family:sans-serif; margin-top:50px; color:#1b7a43;'><b>Shaare enregistré !</b> Fermeture...</p>"
    
    url = request.args.get('url', '')
    title = request.args.get('title', '')
    selection = request.args.get('selection', '')
    
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    existing = conn.execute("SELECT * FROM bookmarks WHERE url = ?", (url,)).fetchone()
    conn.close()
    
    if existing:
        data = {
            'url': existing['url'],
            'title': existing['title'],
            'description': existing['description'],
            'tags': existing['tags'],
            'private': existing['private']
        }
    else:
        data = {
            'url': url,
            'title': title,
            'description': selection,
            'tags': '',
            'private': 0
        }
        
    return render_template_string(BOOKMARKLET_POPUP_TEMPLATE, data=data)

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
        
        .bookmark-desc { 
            margin: 8px 0 12px 0; 
            font-size: 0.9em; 
            color: #2d3748; 
            line-height: 1.4; 
            white-space: pre-wrap; 
            background: #f7fafc; 
            padding: 8px 12px; 
            border-radius: 4px; 
            border: 1px solid #edf2f7; 
        }
        
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
        .pagination-footer a:hover { background: #155d34; }
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
            <a href="#">Nuage de tags</a>
            <a href="#">Quotidien</a>
        </div>
        <div class="header-right">
            <div class="stats-block">
                <div>{{ total_items }} shaares</div>
                <div style="font-weight: normal; opacity: 0.9;">{{ total_items }} liens publics</div>
            </div>
            <a href="javascript:void(0);" title="Recherche">🔍</a>
            <a href="javascript:void(0);" title="RSS">📡</a>
            <a href="javascript:void(0);" title="Déconnexion">🚪</a>
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
                
                <div style="margin-bottom: 15px; font-size: 0.9em;">
                    <label><input type="checkbox" name="private" value="1"> Privé</label>
                </div>
                
                <button type="submit" style="background:#1b7a43; color:white; border:none; padding:10px; width:100%; font-weight:bold; border-radius:3px; cursor:pointer;">Enregistrer</button>
            </form>
        </div>

        <form method="GET" class="search-bar-container">
            <div class="search-input-wrapper">
                <input type="text" name="q" placeholder="Recherche texte" value="{{ search }}">
            </div>
            <div class="search-input-wrapper">
                <input type="text" name="tag" placeholder="Filtrer par tag" value="{{ tag_filter }}">
            </div>
            <button type="submit" class="search-btn">🔍</button>
            <input type="hidden" name="per_page" value="{{ per_page }}">
        </form>

        <div class="top-nav-bar">
            <div>
                Filtres : 🔒 🌐 🏷️ ☑️
                {% if tag_filter or search %}
                | <a href="/" style="color: #1b7a43; text-decoration: underline;">Réinitialiser les filtres</a>
                {% endif %}
            </div>
            
            <div style="font-weight: bold;">
                {{ page }} / {{ total_pages }} ➔
            </div>

            <div class="per-page-links">
                Liens par page : 
                <a href="/?per_page=15{% if search %}&q={{ search }}{% endif %}{% if tag_filter %}&tag={{ tag_filter }}{% endif %}" class="{% if per_page == 15 %}active{% endif %}">15</a>
                <a href="/?per_page=20{% if search %}&q={{ search }}{% endif %}{% if tag_filter %}&tag={{ tag_filter }}{% endif %}" class="{% if per_page == 20 %}active{% endif %}">20</a>
                <a href="/?per_page=50{% if search %}&q={{ search }}{% endif %}{% if tag_filter %}&tag={{ tag_filter }}{% endif %}" class="{% if per_page == 50 %}active{% endif %}">50</a>
                <a href="/?per_page=100{% if search %}&q={{ search }}{% endif %}{% if tag_filter %}&tag={{ tag_filter }}{% endif %}" class="{% if per_page == 100 %}active{% endif %}">100</a>
            </div>
        </div>

        {% if search or tag_filter %}
        <div class="results-banner">
            {{ filtered_total }} résultat{% if filtered_total > 1 %}s{% endif %} pour 
            {% if search %}<i>{{ search }}</i>{% endif %}
            {% if search and tag_filter %} + {% endif %}
            {% if tag_filter %}tag: <i>{{ tag_filter }}</i>{% endif %}
        </div>
        {% endif %}

        {% for b in bookmarks %}
        <div class="bookmark-card">
            {% if b.private == 1 %}
            <div class="private-badge">Privé</div>
            {% endif %}
            
            <div class="bookmark-header">
                <span style="font-size: 1.1em;">📝</span>
                <a href="{{ b.url }}" target="_blank" class="bookmark-link">{{ b.title }}</a>
            </div>
            
            {% if b.description %}
            <div class="bookmark-desc">{{ b.description }}</div>
            {% endif %}
            
            {% if b.tags %}
            <div style="margin-bottom: 8px;">
                <span style="font-size: 0.8em;">🏷️</span>
                {% for t in b.tags.replace(',', ' ').split() %}
                    {% if t.strip() %}
                    <a href="/?tag={{ t.strip() }}&per_page={{ per_page }}" class="tag-badge">{{ t.strip() }}</a>
                    {% endif %}
                {% endfor %}
            </div>
            {% endif %}

            <div class="bookmark-footer">
                <div class="bookmark-actions">
                    <input type="checkbox">
                    <a href="/edit/{{ b.id }}" title="Éditer">📝</a>
                    <a href="/delete/{{ b.id }}" title="Supprimer" onclick="return confirm('Confirmer la suppression ?');">🗑️</a>
                    <a href="#" title="Épingler">📌</a>
                    <span>🕒 {{ b.formatted_date }} * · permalien</span>
                </div>
                
                <div class="bookmark-url-display">
                    🔗 <a href="{{ b.url }}" target="_blank" title="{{ b.url }}">{{ b.url }}</a>
                </div>
            </div>
        </div>
        {% else %}
        <div class="bookmark-card" style="text-align: center; color: #718096; padding: 30px;">
            Aucun favori trouvé.
        </div>
        {% endfor %}

        {% if total_pages > 1 %}
        <div class="pagination-footer">
            {% if page > 1 %}
                <a href="/?page={{ page - 1 }}&per_page={{ per_page }}{% if search %}&q={{ search }}{% endif %}{% if tag_filter %}&tag={{ tag_filter }}{% endif %}">« Précédent</a>
            {% endif %}
            
            <span style="background: white; padding: 6px 12px; border: 1px solid #bbb; border-radius: 3px; color: #333;">Page {{ page }} sur {{ total_pages }}</span>

            {% if page < total_pages %}
                <a href="/?page={{ page + 1 }}&per_page={{ per_page }}{% if search %}&q={{ search }}{% endif %}{% if tag_filter %}&tag={{ tag_filter }}{% endif %}">Suivant »</a>
            {% endif %}
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
    <meta charset="UTF-8">
    <title>Outils - Shared Bookmarks</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #dcdfdc; margin: 0; padding: 0; color: #333; }
        header { background: #1b7a43; color: white; padding: 10px 20px; display: flex; justify-content: space-between; align-items: center; font-size: 0.95em; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .header-left, .header-right { display: flex; align-items: center; gap: 20px; }
        header a { color: white; text-decoration: none; font-weight: 500; }
        header a:hover { text-decoration: underline; }
        .container { max-width: 800px; margin: 30px auto; padding: 0 15px; }
        .card { background: white; padding: 30px; border-radius: 4px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); border: 1px solid #ccc; margin-bottom: 20px; }
        h2 { color: #1b7a43; text-align: center; margin-top: 0; font-size: 1.4em; }
        .alert { background: #e6fffa; border: 1px solid #b2f5ea; color: #234e52; padding: 12px; border-radius: 4px; margin-bottom: 20px; font-size: 0.95em; text-align: center; }
        label { display: block; font-weight: 600; margin-bottom: 8px; font-size: 0.95em; }
        .btn-green { background: #1b7a43; color: white; border: none; padding: 10px 20px; font-weight: bold; border-radius: 3px; cursor: pointer; font-size: 1em; text-decoration: none; display: inline-block; }
        .btn-green:hover { background: #155d34; }
    </style>
</head>
<body>
    <header>
        <div class="header-left">
            <a href="/" style="font-size: 1.15em; font-weight: bold;">⭐ Shared Bookmarks</a>
            <a href="/">➕ Shaare</a>
            <a href="/tools">Outils</a>
            <a href="#">Nuage de tags</a>
            <a href="#">Quotidien</a>
        </div>
        <div class="header-right">
            <a href="javascript:void(0);" title="Recherche">🔍</a>
            <a href="javascript:void(0);" title="RSS">📡</a>
            <a href="javascript:void(0);" title="Déconnexion">🚪</a>
        </div>
    </header>

    <div class="container">
        {% if message %}
        <div class="alert">{{ message }}</div>
        {% endif %}

        <div class="card">
            <h2>Importer des favoris</h2>
            <p style="font-size: 0.9em; color: #555; margin-bottom: 20px;">
                Sélectionnez un fichier HTML de favoris (export Netscape / export officiel Shaarli) pour importer vos liens et descriptions. Les liens existants seront mis à jour.
            </p>
            <form method="POST" enctype="multipart/form-data">
                <input type="hidden" name="action" value="import">
                <input type="file" name="file" accept=".html" required style="margin-bottom: 15px; display: block;">
                <button type="submit" class="btn-green">Lancer l'importation</button>
            </form>
        </div>

        <div class="card">
            <h2>Exporter les favoris</h2>
            <p style="font-size: 0.9em; color: #555; margin-bottom: 20px;">
                Téléchargez l'intégralité de vos favoris sous forme de fichier HTML compatible (format Netscape / Shaarli).
            </p>
            <a href="/export" class="btn-green">Télécharger l'export HTML</a>
        </div>
    </div>
</body>
</html>
'''

EDIT_TEMPLATE = '''
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <title>Modifier le Shaare</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #dcdfdc; margin: 0; padding: 0; color: #333; }
        header { background: #1b7a43; color: white; padding: 10px 20px; display: flex; justify-content: space-between; align-items: center; font-size: 0.95em; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .header-left, .header-right { display: flex; align-items: center; gap: 20px; }
        header a { color: white; text-decoration: none; font-weight: 500; }
        header a:hover { text-decoration: underline; }
        .container { max-width: 800px; margin: 30px auto; padding: 0 15px; }
        .card { background: white; padding: 30px; border-radius: 4px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); border: 1px solid #ccc; }
        h2 { color: #1b7a43; text-align: center; margin-top: 0; font-size: 1.5em; }
        .date-info { text-align: center; font-size: 0.85em; color: #555; margin-bottom: 20px; }
        label { display: block; font-weight: 600; text-align: center; margin-bottom: 5px; font-size: 0.9em; color: #333; }
        input[type="text"], textarea { width: 100%; padding: 8px 12px; box-sizing: border-box; border: 1px solid #ccc; border-radius: 3px; font-size: 0.95em; margin-bottom: 15px; background: #fafbfc; }
        textarea { height: 150px; resize: vertical; border-color: #3182ce; }
        .checkbox-container { text-align: center; margin-bottom: 15px; font-size: 0.95em; }
        .markdown-hint { text-align: center; font-size: 0.85em; color: #666; margin-bottom: 20px; }
        .markdown-hint a { color: #1b7a43; text-decoration: none; font-weight: bold; }
        .markdown-hint a:hover { text-decoration: underline; }
        .buttons-row { display: flex; gap: 15px; }
        .btn-green { background: #1b7a43; color: white; border: none; padding: 10px; font-weight: bold; border-radius: 3px; cursor: pointer; flex: 1; font-size: 1em; text-align: center; text-decoration: none; display: inline-block; }
        .btn-green:hover { background: #155d34; }
        .btn-red { background: #a52a2a; color: white; border: none; padding: 10px; font-weight: bold; border-radius: 3px; cursor: pointer; flex: 1; font-size: 1em; text-align: center; text-decoration: none; display: inline-block; }
        .btn-red:hover { background: #802020; }
    </style>
</head>
<body>
    <header>
        <div class="header-left">
            <a href="/" style="font-size: 1.15em; font-weight: bold;">⭐ Shared Bookmarks</a>
            <a href="/">➕ Shaare</a>
            <a href="/tools">Outils</a>
            <a href="#">Nuage de tags</a>
            <a href="#">Quotidien</a>
        </div>
        <div class="header-right">
            <a href="javascript:void(0);" title="Recherche">🔍</a>
            <a href="javascript:void(0);" title="RSS">📡</a>
            <a href="javascript:void(0);" title="Déconnexion">🚪</a>
        </div>
    </header>

    <div class="container">
        <div class="card">
            <h2>Modifier le Shaare</h2>
            <div class="date-info">Création : {{ bookmark.formatted_date }}</div>
            
            <form method="POST">
                <label>URL</label>
                <input type="text" name="url" value="{{ bookmark.url }}" required>
                
                <label>Titre</label>
                <input type="text" name="title" value="{{ bookmark.title }}">
                
                <label>Description</label>
                <textarea name="description">{{ bookmark.description or '' }}</textarea>
                
                <label>Tags</label>
                <input type="text" name="tags" value="{{ bookmark.tags or '' }}">
                
                <div class="checkbox-container">
                    <label style="display:inline;"><input type="checkbox" name="private" value="1" {% if bookmark.private == 1 %}checked{% endif %}> Privé</label>
                </div>
                
                <div class="markdown-hint">
                    La description sera générée avec <a href="#">la syntaxe Markdown</a>.
                </div>
                
                <div class="buttons-row">
                    <button type="submit" class="btn-green">Appliquer les changements</button>
                    <a href="/delete/{{ bookmark.id }}" class="btn-red" onclick="return confirm('Confirmer la suppression ?');">Supprimer</a>
                </div>
            </form>
        </div>
    </div>
</body>
</html>
'''

BOOKMARKLET_POPUP_TEMPLATE = '''
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <title>Nouveau Shaare</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #eef2f5; margin: 0; padding: 15px; color: #333; }
        .card { background: white; padding: 20px; border-radius: 6px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); border: 1px solid #e1e8ed; }
        h2.title-green { color: #1b7a43; text-align: center; margin-top: 0; margin-bottom: 20px; font-size: 1.4em; }
        label { display: block; font-weight: 600; margin-bottom: 6px; color: #4f5d75; text-align: center; font-size: 0.9em; }
        input[type="text"], textarea { width: 100%; padding: 8px; margin-bottom: 15px; box-sizing: border-box; border: 1px solid #ccd9e0; border-radius: 4px; font-size: 0.95em; background: #fafbfc; }
        input:focus, textarea:focus { border-color: #1b7a43; outline: none; background: white; }
        textarea { resize: vertical; height: 100px; }
        .btn-green { background: #1b7a43; color: white; border: none; padding: 10px 15px; border-radius: 4px; cursor: pointer; font-size: 1em; font-weight: bold; width: 100%; display: block; text-align: center; }
        .btn-green:hover { background: #155d34; }
    </style>
</head>
<body>
    <div class="card">
        <h2 class="title-green">Nouveau Shaare</h2>
        <form action="/bookmarklet" method="POST">
            <label>URL</label>
            <input type="text" name="url" value="{{ data.url }}" required>
            
            <label>Titre</label>
            <input type="text" name="title" value="{{ data.title }}">
            
            <label>Description</label>
            <textarea name="description">{{ data.description }}</textarea>
            
            <label>Tags</label>
            <input type="text" name="tags" value="{{ data.tags }}" placeholder="séparés par des espaces ou virgules">
            
            <div style="margin-bottom: 15px; text-align: center;">
                <label style="display:inline;"><input type="checkbox" name="private" value="1" {% if data.private == 1 %}checked{% endif %}> Privé</label>
            </div>
            
            <button type="submit" class="btn-green">Enregistrer / Mettre à jour</button>
        </form>
    </div>
</body>
</html>
'''

if __name__ == '__main__':
    init_db()
    app.run(debug=False, port=5000)