import os
from datetime import timedelta
from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import psycopg2
from psycopg2.extras import RealDictCursor
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

# --- CONFIGURATION ---
app = Flask(__name__)
# La clé est fixe pour éviter de déconnecter tout le monde au redémarrage de Render
app.secret_key = os.environ.get('SECRET_KEY', 'EmmaLiam29!') 

# Configuration de la durée de session à 1 an (365 jours)
app.permanent_session_lifetime = timedelta(days=365) 

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

# --- CONFIGURATION LOGIN ---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

class User(UserMixin):
    def __init__(self, id, username): # On n'a pas besoin de stocker le password ici
        self.id = str(id) # Flask-Login préfère les ID sous forme de string
        self.username = username

@login_manager.user_loader
def load_user(user_id):
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT * FROM users WHERE id = %s', (user_id,))
                u = cur.fetchone()
                if u: 
                    # On crée l'objet avec seulement ID et Username
                    return User(u['id'], u['username'])
    except Exception as e:
        print(f"Erreur load_user: {e}")
        return None
    return None

# --- FONCTIONS UTILITAIRES ---
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

# --- ROUTES ---

@app.route('/')
@login_required 
def index():
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # Sécurité : On s'assure de ne récupérer que des recettes avec un ID valide
                cur.execute('SELECT * FROM Recettes WHERE id IS NOT NULL ORDER BY categorie, nom')
                recettes = cur.fetchall()
        
        recettes_par_categorie = {}
        categories = set()
        for r in recettes:
            if r.get('id'): # Double vérification pour éviter le BuildError dans le template
                cat = r['categorie'] or "Sans catégorie"
                categories.add(cat)
                recettes_par_categorie.setdefault(cat, []).append(r)
        return render_template('index.html', recettes_par_categorie=recettes_par_categorie, categories=list(categories))
    except Exception as e:
        return f"Erreur critique base de données : {str(e)}"

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username, password = request.form['username'], request.form['password']
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT * FROM users WHERE username = %s', (username,))
                user_data = cur.fetchone()
        
        # Le bloc ci-dessous doit être parfaitement aligné
        if user_data and check_password_hash(user_data['password'], password):
            user_obj = User(user_data['id'], user_data['username']) # Ligne 116 corrigée
            session.permanent = True
            login_user(user_obj, remember=True)
            
            next_page = request.args.get('next')
            if not next_page or not next_page.startswith('/'):
                next_page = url_for('index')
            return redirect(next_page)
        else:
            flash('Identifiants incorrects.')
            
    return render_template('login.html')

@app.route('/recette/<int:recette_id>')
@login_required
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
@login_required
def ajouter_recette():
    if request.method == 'POST':
        # Envoi d'un vrai Booléen pour PostgreSQL
        est_sous = True if 'est_sous_recette' in request.form else False
        try:
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    # RETURNING id est crucial pour éviter les recettes sans ID
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
                            try:
                                q_val = float(q.replace(',', '.')) if q and q.strip() else 0.0
                            except ValueError:
                                q_val = 0.0
                            cur.execute('''INSERT INTO Ingredients (id_recette, nom, quantite, unite) 
                                           VALUES (%s, %s, %s, %s)''', (recette_id, n, q_val, u))
                    
                    for s_id in request.form.getlist('sous_recette_id[]'):
                        if s_id:
                            cur.execute('INSERT INTO SousRecettesUtilisees (id_recette, id_sous_recette) VALUES (%s, %s)', 
                                        (recette_id, s_id))
                conn.commit()
            flash("Recette ajoutée avec succès !")
            return redirect(url_for('index'))
        except Exception as e:
            return f"Erreur lors de l'enregistrement : {str(e)}"
    return render_template('ajouter.html', sous_recettes=get_sous_recettes())

@app.route('/recette/<int:recette_id>/modifier', methods=['GET', 'POST'])
@login_required
def modifier_recette(recette_id):
    if request.method == 'POST':
        est_sous = True if 'est_sous_recette' in request.form else False
        try:
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute('''UPDATE Recettes SET nom=%s, description=%s, categorie=%s, est_sous_recette=%s 
                                   WHERE id=%s''', (request.form.get('nom'), request.form.get('description'), 
                                                    request.form.get('categorie'), est_sous, recette_id))

                    cur.execute('DELETE FROM Ingredients WHERE id_recette = %s', (recette_id,))
                    noms = request.form.getlist('ingredient_nom[]')
                    quants = request.form.getlist('ingredient_quantite[]')
                    unites = request.form.getlist('ingredient_unite[]')

                    for n, q, u in zip(noms, quants, unites):
                        if n.strip():
                            try:
                                q_val = float(q.replace(',', '.')) if q and q.strip() else 0.0
                            except ValueError:
                                q_val = 0.0
                            cur.execute('INSERT INTO Ingredients (id_recette, nom, quantite, unite) VALUES (%s, %s, %s, %s)', 
                                        (recette_id, n, q_val, u))

                    cur.execute('DELETE FROM SousRecettesUtilisees WHERE id_recette = %s', (recette_id,))
                    for s_id in request.form.getlist('sous_recette_id[]'):
                        if s_id:
                            cur.execute('INSERT INTO SousRecettesUtilisees (id_recette, id_sous_recette) VALUES (%s, %s)', 
                                        (recette_id, s_id))
                conn.commit()
            flash("Recette mise à jour !")
            return redirect(url_for('index'))
        except Exception as e:
            return f"Erreur : {str(e)}"

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT * FROM Recettes WHERE id = %s', (recette_id,))
            recette = cur.fetchone()
    return render_template('modifier_recette.html', recette=recette, ingredients=get_ingredients(recette_id), 
                           sous_recettes=get_sous_recettes(), sous_recettes_utilisees=get_sous_recettes_utilisees(recette_id))

@app.route('/recette/<int:recette_id>/imprimer')
@login_required
def imprimer_recette(recette_id):
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT * FROM Recettes WHERE id = %s', (recette_id,))
                recette = cur.fetchone()
                cur.execute('SELECT * FROM Ingredients WHERE id_recette = %s', (recette_id,))
                ingredients = cur.fetchall()
        
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter)
        styles = getSampleStyleSheet()
        story = []

        story.append(Paragraph(f"Recette : {recette['nom']}", styles['Title']))
        story.append(Spacer(1, 12))
        story.append(Paragraph(f"<b>Catégorie :</b> {recette['categorie'] or ''}", styles['Normal']))
        story.append(Spacer(1, 12))
        story.append(Paragraph(f"<b>Description :</b> {recette['description'] or ''}", styles['Normal']))
        story.append(Spacer(1, 12))
        story.append(Paragraph("Ingrédients :", styles['Heading2']))
        
        for ing in ingredients:
            q = ing['quantite'] if ing['quantite'] is not None else ""
            u = ing['unite'] if ing['unite'] is not None else ""
            n = ing['nom'] or ""
            story.append(Paragraph(f"• {q} {u} {n}", styles['Normal']))
        
        doc.build(story)
        buffer.seek(0)
        return send_file(buffer, mimetype='application/pdf', download_name=f"{recette['nom'].replace(' ', '_')}.pdf")
    except Exception as e:
        return f"Erreur PDF : {str(e)}"
        
@app.route('/recette/<int:id>/supprimer', methods=['POST'])
@login_required
def supprimer_recette(id):
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # Nettoyage manuel des dépendances pour PostgreSQL
                cur.execute('DELETE FROM Ingredients WHERE id_recette = %s', (id,))
                cur.execute('DELETE FROM SousRecettesUtilisees WHERE id_recette = %s OR id_sous_recette = %s', (id, id))
                cur.execute('DELETE FROM Recettes WHERE id = %s', (id,))
            conn.commit()
        return redirect(url_for('index'))
    except Exception as e:
        return f"Erreur suppression : {str(e)}"
        
@app.route('/recherche', methods=['GET'])
@login_required
def rechercher_recette():
    terme = request.args.get('terme', '').strip()
    type_r = request.args.get('type_recherche', 'nom')
    cat = request.args.get('categorie', '')
    query = "SELECT * FROM Recettes WHERE 1=1"
    params = []
    
    if terme:
        if type_r == 'nom': 
            query += " AND nom ILIKE %s"; params.append(f'%{terme}%')
        elif type_r == 'ingredient':
            # Utilisation de DISTINCT pour ne pas avoir 10 fois la même recette
            query = "SELECT DISTINCT r.* FROM Recettes r JOIN Ingredients i ON r.id = i.id_recette WHERE i.nom ILIKE %s"; params.append(f'%{terme}%')
    if cat:
        query += " AND categorie = %s"; params.append(cat)
        
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            recettes = cur.fetchall()
    return render_template('recherche.html', recettes=recettes, terme=terme, categorie=cat)

@app.route('/logout')
def logout():
    logout_user()
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)