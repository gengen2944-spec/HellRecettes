import os
from datetime import timedelta
from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file
import psycopg2
from psycopg2.extras import RealDictCursor
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

# --- CONFIGURATION ---
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'EmmaLiam29!') 
app.permanent_session_lifetime = timedelta(days=31)

# Correction de l'URL pour Render/PostgreSQL
DATABASE_URL = os.environ.get('DATABASE_URL')
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# --- GESTION DE LA BASE DE DONNÉES ---
def get_db_connection():
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL manquante dans l'environnement")
    return psycopg2.connect(
        DATABASE_URL, 
        cursor_factory=RealDictCursor,
        connect_timeout=15,
        options="-c client_encoding=UTF8 -c prepare_threshold=0"
    )

# --- NOUVELLE ROUTE : PING (POUR UPTIMEROBOT) ---
@app.route('/ping')
def ping():
    """Route pour réveiller Render et Supabase sans être bloqué par le login"""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
        return "Service Active & Database Connected", 200
    except Exception as e:
        return f"Database Error: {e}", 500

# --- FONCTIONS UTILITAIRES ---
def recuperer_categories():
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT DISTINCT categorie FROM Recettes WHERE categorie IS NOT NULL ORDER BY categorie ASC")
                return [row['categorie'] for row in cur.fetchall()]
    except:
        return []

def get_ingredients(recette_id):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT * FROM Ingredients WHERE id_recette = %s', (recette_id,))
            return cur.fetchall()

def get_sous_recettes():
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT * FROM Recettes WHERE est_sous_recette = TRUE')
            return cur.fetchall()

def get_sous_recettes_utilisees(recette_id):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute('''SELECT r.* FROM Recettes r
                           JOIN SousRecettesUtilisees s ON r.id = s.id_sous_recette
                           WHERE s.id_recette = %s''', (recette_id,))
            return cur.fetchall()

# --- ROUTES PRINCIPALES ---

@app.route('/')
def index():
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT * FROM Recettes ORDER BY categorie, nom')
                recettes = cur.fetchall()
        
        recettes_par_categorie = {}
        for r in recettes:
            cat = r['categorie'] or "Sans catégorie"
            recettes_par_categorie.setdefault(cat, []).append(r)
        return render_template('index.html', recettes_par_categorie=recettes_par_categorie)
    except Exception as e:
        return f"Erreur base de données : {str(e)}"

@app.route('/recette/<int:recette_id>')
def afficher_recette(recette_id):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT * FROM Recettes WHERE id = %s', (recette_id,))
            recette = cur.fetchone()
    if not recette:
        return "Recette introuvable", 404
    return render_template('recette.html', recette=recette, 
                           ingredients=get_ingredients(recette_id), 
                           sous_recettes=get_sous_recettes_utilisees(recette_id))

@app.route('/ajout', methods=['GET', 'POST'])
def ajouter_recette():
    if request.method == 'POST':
        est_sous = 'est_sous_recette' in request.form
        try:
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute('''INSERT INTO Recettes (nom, description, categorie, est_sous_recette) 
                                   VALUES (%s, %s, %s, %s) RETURNING id''', 
                                (request.form.get('nom'), request.form.get('description'), 
                                 request.form.get('categorie'), est_sous))
                    recette_id = cur.fetchone()['id']

                    noms = request.form.getlist('ingredient_nom[]')
                    quants = request.form.getlist('ingredient_quantite[]')
                    unites = request.form.getlist('ingredient_unite[]')

                    for n, q, u in zip(noms, quants, unites):
                        if n.strip():
                            q_val = float(q.replace(',', '.')) if q and q.strip() else 0.0
                            cur.execute('INSERT INTO Ingredients (id_recette, nom, quantite, unite) VALUES (%s, %s, %s, %s)', 
                                        (recette_id, n, q_val, u))
                    
                    for s_id in request.form.getlist('sous_recette_id[]'):
                        if s_id:
                            cur.execute('INSERT INTO SousRecettesUtilisees (id_recette, id_sous_recette) VALUES (%s, %s)', (recette_id, s_id))
                conn.commit()
            return redirect(url_for('index'))
        except Exception as e:
            return f"Erreur lors de l'ajout : {str(e)}"
    return render_template('ajouter.html', sous_recettes=get_sous_recettes())

@app.route('/recette/<int:recette_id>/imprimer')
def imprimer_recette(recette_id):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT * FROM Recettes WHERE id = %s', (recette_id,))
            recette_principale = cur.fetchone()
            cur.execute('''SELECT r.* FROM Recettes r
                           JOIN SousRecettesUtilisees s ON r.id = s.id_sous_recette
                           WHERE s.id_recette = %s''', (recette_id,))
            sous_recettes = cur.fetchall()

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    story = []

    def ajouter_bloc_recette(data_recette, est_principal=True):
        titre_style = styles['Title'] if est_principal else styles['Heading1']
        story.append(Paragraph(data_recette['nom'], titre_style))
        story.append(Spacer(1, 12))
        
        if data_recette['description']:
            story.append(Paragraph("Instructions :", styles['Heading2']))
            texte = data_recette['description'].replace('\n', '<br/>')
            story.append(Paragraph(texte, styles['Normal']))
            story.append(Spacer(1, 12))
        
        story.append(Paragraph("Ingrédients :", styles['Heading2']))
        ings = get_ingredients(data_recette['id'])
        for ing in ings:
            q = ing['quantite'] if ing['quantite'] else ""
            u = ing['unite'] if ing['unite'] else ""
            story.append(Paragraph(f"• {q} {u} {ing['nom']}", styles['Normal']))
        story.append(Spacer(1, 24))

    ajouter_bloc_recette(recette_principale, True)
    for sr in sous_recettes:
        ajouter_bloc_recette(sr, False)
    
    doc.build(story)
    buffer.seek(0)
    nom_f = "".join([c if c.isalnum() else "_" for c in recette_principale['nom']])
    return send_file(buffer, mimetype='application/pdf', download_name=f"{nom_f}.pdf")

@app.route('/recette/<int:recette_id>/supprimer', methods=['POST'])
def supprimer_recette(recette_id):
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute('DELETE FROM Ingredients WHERE id_recette = %s', (recette_id,))
                cur.execute('DELETE FROM SousRecettesUtilisees WHERE id_recette = %s OR id_sous_recette = %s', (recette_id, recette_id))
                cur.execute('DELETE FROM Recettes WHERE id = %s', (recette_id,))
            conn.commit()
    except Exception as e:
        print(f"Erreur suppression : {e}")
    return redirect(url_for('index'))

@app.route('/recherche')
def rechercher_recette():
    terme = request.args.get('terme', '').strip()
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM Recettes WHERE nom ILIKE %s", (f'%{terme}%',))
            recettes = cur.fetchall()
    return render_template('recherche.html', recettes=recettes, terme=terme)

# --- AUTHENTIFICATION ---

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        try:
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    # Requête sécurisée pour vérifier l'utilisateur dans Supabase
                    cur.execute('SELECT * FROM users WHERE username = %s AND password = %s', (username, password))
                    user = cur.fetchone()
            
            if user:
                session['logged_in'] = True
                session.permanent = True
                return redirect(url_for('index'))
            else:
                flash('Identifiants incorrects', 'danger')
        except Exception as e:
            # En cas d'erreur de base de données (ex: table users manquante)
            print(f"Erreur login : {e}")
            flash("Erreur technique lors de la connexion", 'danger')
            
    return render_template('login.html')

@app.before_request
def check_login():
    # Autorise 'ping', 'login' et les fichiers 'static' (CSS/Images) sans connexion
    if request.endpoint not in ['login', 'static', 'ping'] and not session.get('logged_in'):
        return redirect(url_for('login'))

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)