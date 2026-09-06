import sqlite3
from datetime import datetime
from urllib.parse import urlparse
from flask import Flask, render_template, request, redirect, url_for

app = Flask(__name__)
app.secret_key = 'votre_cle_secrete_ici'

DB_NAME = 'bookmarks.db'

def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS bookmarks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT NOT NULL,
            title TEXT,
            description TEXT,
            tags TEXT,
            add_date TEXT,
            private INTEGER DEFAULT 0
        )
    ''')
    conn.commit()
    conn.close()

init_db()

@app.route('/')
def index():
    conn = get_db_connection()
    cursor = conn.execute('SELECT * FROM bookmarks ORDER BY id DESC')
    bookmarks = cursor.fetchall()
    conn.close()
    return render_template('index.html', bookmarks=bookmarks)

@app.route('/add', methods=['GET', 'POST'])
def add_bookmark():
    if request.method == 'POST':
        url = request.form.get('url', '').strip()
        title = request.form.get('title', '').strip()
        desc = request.form.get('desc', '').strip()
        tags = request.form.get('tags', '').strip()
        private = 1 if request.form.get('private') else 0
        add_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        if url:
            conn = get_db_connection()
            conn.execute(
                'INSERT INTO bookmarks (url, title, description, tags, add_date, private) VALUES (?, ?, ?, ?, ?, ?)',
                (url, title, desc, tags, add_date, private)
            )
            conn.commit()
            conn.close()
            return redirect(url_for('index'))
            
    url = request.args.get('url', '')
    title = request.args.get('title', '')
    desc = request.args.get('description', '')
    
    return render_template('add.html', url=url, title=title, desc=desc)

@app.route('/tools')
def tools():
    return render_template('tools.html')

@app.route('/tools/top-domains')
def top_domains():
    conn = get_db_connection()
    cursor = conn.execute("SELECT url FROM bookmarks")
    domains = {}
    for row in cursor:
        try:
            parsed_url = urlparse(row['url'])
            domain = parsed_url.netloc
            if domain:
                domains[domain] = domains.get(domain, 0) + 1
        except Exception:
            continue
    conn.close()
    
    sorted_domains = sorted(domains.items(), key=lambda x: x[1], reverse=True)
    return render_template('top_domains.html', sorted_domains=sorted_domains)

# Routes d'outils pour éviter toute erreur BuildError
@app.route('/tools/optimize-tags', methods=['GET', 'POST'])
def optimize_tags():
    return render_template('tools.html')

@app.route('/tools/tags-by-year')
def tags_by_year():
    return render_template('tools.html')

@app.route('/tools/rename-tags', methods=['GET', 'POST'])
def rename_tags():
    return render_template('tools.html')

@app.route('/tools/import-export', methods=['GET', 'POST'])
def import_export():
    return render_template('tools.html')

if __name__ == '__main__':
    app.run(debug=True)