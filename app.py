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

DATABASE_URL = os.environ.get('DATABASE_URL')
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# --- DB CONNECTION ---
def get_db_connection():
    return psycopg2.connect(
        DATABASE_URL, 
        cursor_factory=RealDictCursor,
        connect_timeout=15,
        options="-c client_encoding=UTF8 -c prepare_threshold=0"
    )

# --- SÉCURITÉ ---
@app.before_request
def check_login():
    exempt_routes = ['login', 'static', 'ping']
    if request.endpoint in exempt_routes:
        return None
    if not session.get('logged_in'):
        return redirect(url_for('login'))

@app.route('/ping')
def ping():
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        return "Service Active", 200
    except Exception as e:
        return f"Error: {e}", 500

# --- AUTHENTIFICATION ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        try:
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute('SELECT * FROM users WHERE username = %s AND password = %s', (username, password))
                    user = cur.fetchone()
            if user:
                session.clear()
                session['logged_in'] = True
                session.permanent = True
                return redirect(url_for('index'))
            flash('Identifiants incorrects', 'danger')
        except Exception as e:
            flash(f"Erreur technique : {e}", 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# --- AFFICHAGE ---
@app.route('/')
def index():
    try:
        ordre_categories = ['ENTREES', 'PLATS', 'DESSERTS', 'BOULANGERIE', 'DIVERS']
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT * FROM Recettes ORDER BY nom')
                recettes = cur.fetchall()
        recettes_par_categorie = {}
        cats_base = set()
        for r in recettes:
            cat = r['categorie'] or "DIVERS"
            cats_base.add(cat)
            recettes_par_categorie.setdefault(cat, []).append(r)
        for c in cats_base:
            if c not in ordre_categories:
                ordre_categories.append(c)
        return render_template('index.html', recettes_par_categorie=recettes_par_categorie, ordre_categories=ordre_categories)
    except Exception as e:
        return f"Erreur index : {str(e)}"

@app.route('/recette/<int:recette_id>')
def afficher_recette(recette_id):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT * FROM Recettes WHERE id = %s', (recette_id,))
            recette = cur.fetchone()
            cur.execute('SELECT * FROM Ingredients WHERE id_recette = %s', (recette_id,))
            ingredients = cur.fetchall()
            cur.execute('''SELECT r.* FROM Recettes r JOIN SousRecettesUtilisees s ON r.id = s.id_sous_recette WHERE s.id_recette = %s''', (recette_id,))
            sous_recettes = cur.fetchall()
    if not recette: return "Introuvable", 404
    return render_template('recette.html', recette=recette, ingredients=ingredients, sous_recettes=sous_recettes)

# --- GESTION (AJOUT / MODIF / SUPPR) ---

@app.route('/ajouter_recette', methods=['GET', 'POST'])
@app.route('/ajouter', methods=['GET', 'POST'])
@app.route('/ajout', methods=['GET', 'POST'])  # <-- On rajoute celle-ci pour corriger le lien 404
def ajouter_recette():
    if request.method == 'POST':
        nom = request.form.get('nom')
        categorie = request.form.get('categorie')
        description = request.form.get('description')
        est_sous_recette = True if request.form.get('est_sous_recette') else False
        
        noms_ing = request.form.getlist('ingredient_nom[]')
        quants_ing = request.form.getlist('ingredient_quantite[]')
        unites_ing = request.form.getlist('ingredient_unite[]')
        sr_ids = request.form.getlist('sous_recette_id[]')
        
        try:
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute('''INSERT INTO Recettes (nom, categorie, description, est_sous_recette) 
                                   VALUES (%s, %s, %s, %s) RETURNING id''', 
                                (nom, categorie, description, est_sous_recette))
                    new_id = cur.fetchone()['id']
                    
                    for n, q, u in zip(noms_ing, quants_ing, unites_ing):
                        if n.strip():
                            cur.execute('INSERT INTO Ingredients (id_recette, nom, quantite, unite) VALUES (%s, %s, %s, %s)', (new_id, n, q, u))
                    
                    for sr_id in sr_ids:
                        if sr_id:
                            cur.execute('INSERT INTO SousRecettesUtilisees (id_recette, id_sous_recette) VALUES (%s, %s)', (new_id, sr_id))
                conn.commit()
            flash("Recette ajoutée !", "success")
            return redirect(url_for('index'))
        except Exception as e:
            flash(f"Erreur : {e}", "danger")

    categories = ['ENTREES', 'PLATS', 'DESSERTS', 'BOULANGERIE', 'DIVERS']
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT id, nom FROM Recettes ORDER BY nom')
            sous_recettes = cur.fetchall()
    # Utilisation du nom correct : ajouter.html
    return render_template('ajouter.html', categories=categories, sous_recettes=sous_recettes)

@app.route('/modifier_recette/<int:recette_id>', methods=['GET', 'POST'])
@app.route('/modifier/<int:recette_id>', methods=['GET', 'POST'])
def modifier_recette(recette_id):
    if request.method == 'POST':
        nom = request.form.get('nom')
        categorie = request.form.get('categorie')
        description = request.form.get('description')
        est_sous_recette = True if request.form.get('est_sous_recette') else False
        
        noms_ing = request.form.getlist('ingredient_nom[]')
        quants_ing = request.form.getlist('ingredient_quantite[]')
        unites_ing = request.form.getlist('ingredient_unite[]')
        sr_ids = request.form.getlist('sous_recette_id[]')

        try:
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute('''UPDATE Recettes SET nom=%s, categorie=%s, description=%s, est_sous_recette=%s 
                                   WHERE id=%s''', (nom, categorie, description, est_sous_recette, recette_id))
                    
                    cur.execute('DELETE FROM Ingredients WHERE id_recette=%s', (recette_id,))
                    for n, q, u in zip(noms_ing, quants_ing, unites_ing):
                        if n.strip():
                            cur.execute('INSERT INTO Ingredients (id_recette, nom, quantite, unite) VALUES (%s, %s, %s, %s)', (recette_id, n, q, u))
                    
                    cur.execute('DELETE FROM SousRecettesUtilisees WHERE id_recette=%s', (recette_id,))
                    for sr_id in sr_ids:
                        if sr_id:
                            cur.execute('INSERT INTO SousRecettesUtilisees (id_recette, id_sous_recette) VALUES (%s, %s)', (recette_id, sr_id))
                conn.commit()
            flash("Recette modifiée !", "success")
            return redirect(url_for('afficher_recette', recette_id=recette_id))
        except Exception as e:
            flash(f"Erreur : {e}", "danger")

    categories = ['ENTREES', 'PLATS', 'DESSERTS', 'BOULANGERIE', 'DIVERS']
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT * FROM Recettes WHERE id=%s', (recette_id,))
            recette = cur.fetchone()
            cur.execute('SELECT * FROM Ingredients WHERE id_recette=%s', (recette_id,))
            ingredients = cur.fetchall()
            cur.execute('''SELECT r.id, r.nom FROM Recettes r 
                           JOIN SousRecettesUtilisees s ON r.id = s.id_sous_recette 
                           WHERE s.id_recette = %s''', (recette_id,))
            sous_recettes_utilisees = cur.fetchall()
            cur.execute('SELECT id, nom FROM Recettes WHERE id != %s ORDER BY nom', (recette_id,))
            sous_recettes = cur.fetchall()
            
    # Utilisation du nom correct : modifier_recette.html
    return render_template('modifier_recette.html', recette=recette, ingredients=ingredients, 
                           sous_recettes_utilisees=sous_recettes_utilisees, 
                           sous_recettes=sous_recettes, categories=categories)

# ... (Reste du code identique : supprimer, imprimer, recherche)
# Je ne remets pas la fin pour gagner de la place, mais garde bien tes fonctions supprimer et imprimer !