import os
from datetime import timedelta
from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import psycopg2
from psycopg2.extras import RealDictCursor

# --- CONFIGURATION (Render & Supabase) ---
app = Flask(__name__)

# Sécurité de la session
app.secret_key = os.environ.get('SECRET_KEY', 'dev_key_prov')

# Récupération et correction de l'URL de la base de données
DATABASE_URL = os.environ.get('DATABASE_URL')
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

app.permanent_session_lifetime = timedelta(minutes=60)

# --- GESTION DE LA BASE DE DONNÉES ---
def get_db_connection():
    if not DATABASE_URL:
        raise ValueError("Erreur : La variable d'environnement DATABASE_URL n'est pas configurée.")
    
    # Connexion à PostgreSQL (Supabase) optimisée pour le pooler
    conn = psycopg2.connect(
        DATABASE_URL, 
        cursor_factory=RealDictCursor,
        connect_timeout=15,
        # Indispensable pour le pooler (port 6543) et l'encodage UTF8
        options="-c client_encoding=UTF8 -c prepare_threshold=0"
    )
    return conn

# --- CONFIGURATION LOGIN ---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

class User(UserMixin):
    def __init__(self, id, username, password):
        self.id = id
        self.username = username
        self.password = password

@login_manager.user_loader
def load_user(user_id):
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT * FROM users WHERE id = %s', (user_id,))
                user_data = cur.fetchone()
                if user_data:
                    return User(user_data['id'], user_data['username'], user_data['password'])
    except Exception as e:
        app.logger.error(f"Erreur lors du chargement de l'utilisateur : {e}")
    return None

# --- FONCTIONS UTILITAIRES ---
def get_ingredients(recette_id):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT * FROM Ingredients WHERE id_recette = %s', (recette_id,))
            return cur.fetchall()

def get_sous_recettes(utilisees_par_id=None):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            if utilisees_par_id:
                cur.execute('''SELECT r.* FROM Recettes r 
                               JOIN SousRecettesUtilisees s ON r.id = s.id_sous_recette 
                               WHERE s.id_recette = %s''', (utilisees_par_id,))
            else:
                cur.execute('SELECT * FROM Recettes WHERE est_sous_recette = TRUE')
            return cur.fetchall()

# --- ROUTES ---

@app.route('/')
def index():
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT * FROM Recettes ORDER BY categorie, nom')
                recettes = cur.fetchall()
        
        recettes_par_categorie = {}
        for r in recettes:
            cat = r['categorie']
            recettes_par_categorie.setdefault(cat, []).append(r)
        
        return render_template('index.html', 
                               recettes_par_categorie=recettes_par_categorie, 
                               categories=recettes_par_categorie.keys())
    except Exception as e:
        return f"Erreur de connexion à la base de données : {e}"

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username, password = request.form['username'], request.form['password']
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT * FROM users WHERE username = %s', (username,))
                user_data = cur.fetchone()
        
        if user_data and check_password_hash(user_data['password'], password):
            user = User(user_data['id'], user_data['username'], user_data['password'])
            login_user(user)
            return redirect(url_for('index'))
        flash('Erreur de connexion : Identifiants incorrects.')
    return render_template('login.html')

@app.route('/recette/<int:recette_id>')
def afficher_recette(recette_id):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT * FROM Recettes WHERE id = %s', (recette_id,))
            recette = cur.fetchone()
    return render_template('recette.html', 
                           recette=recette, 
                           ingredients=get_ingredients(recette_id), 
                           sous_recettes=get_sous_recettes(utilisees_par_id=recette_id))

@app.route('/ajout', methods=['GET', 'POST'])
@login_required
def ajouter_recette():
    if request.method == 'POST':
        est_sous = 'est_sous_recette' in request.form
        data = (request.form.get('nom'), request.form.get('description'), 
                request.form.get('categorie'), est_sous)
        
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # Création de la recette
                cur.execute('''INSERT INTO Recettes (nom, description, categorie, est_sous_recette) 
                               VALUES (%s, %s, %s, %s) RETURNING id''', data)
                recette_id = cur.fetchone()['id']
                
                # Ingrédients
                nom_ings = request.form.getlist('ingredient_nom[]')
                quantite_ings = request.form.getlist('ingredient_quantite[]')
                unite_ings = request.form.getlist('ingredient_unite[]')
                
                for n, q, u in zip(nom_ings, quantite_ings, unite_ings):
                    if n: # N'insère que si le nom de l'ingrédient n'est pas vide
                        q_val = float(q) if q and q.strip() else 0.0
                        cur.execute('''INSERT INTO Ingredients (id_recette, nom, quantite, unite) 
                                       VALUES (%s, %s, %s, %s)''', (recette_id, n, q_val, u))
                
                # Sous-recettes
                for s_id in request.form.getlist('sous_recette_id[]'):
                    cur.execute('''INSERT INTO SousRecettesUtilisees (id_recette, id_sous_recette) 
                                   VALUES (%s, %s)''', (recette_id, s_id))
            conn.commit()
        return redirect(url_for('index'))
    return render_template('ajouter.html', sous_recettes=get_sous_recettes())

@app.route('/recette/<int:recette_id>/supprimer', methods=['POST'])
@login_required
def supprimer_recette(recette_id):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            # PostgreSQL nécessite de supprimer les dépendances manuellement ou avec CASCADE
            cur.execute('DELETE FROM Ingredients WHERE id_recette = %s', (recette_id,))
            cur.execute('DELETE FROM SousRecettesUtilisees WHERE id_recette = %s', (recette_id,))
            cur.execute('DELETE FROM Recettes WHERE id = %s', (recette_id,))
        conn.commit()
    return redirect(url_for('index'))

@app.route('/logout')
def logout():
    logout_user()
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    # Sur Render, le port est géré par la plateforme, mais debug=True est utile pour les tests
    app.run(debug=True)