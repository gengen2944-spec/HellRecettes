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
app.secret_key = os.environ.get('SECRET_KEY', 'EmmaLiam29!') 
app.permanent_session_lifetime = timedelta(days=365) 

DATABASE_URL = os.environ.get('DATABASE_URL')
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

def get_db_connection():
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL manquante")
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

# --- CONFIGURATION LOGIN ---
class User(UserMixin):
    def __init__(self, user_id, username):
        # On s'assure que l'ID est stocké tel quel
        self.id = user_id
        self.username = username

@login_manager.user_loader
def load_user(user_id):
    # Sécurité radicale contre le bug du "None"
    if not user_id or str(user_id).lower() == 'none':
        return None
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # On force la conversion en entier pour PostgreSQL smallint/int
                cur.execute('SELECT * FROM users WHERE id = %s', (int(user_id),))
                u = cur.fetchone()
                if u:
                    return User(u['id'], u['username'])
    except Exception as e:
        print(f"Erreur load_user : {e}")
    return None

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT * FROM users WHERE username = %s', (username,))
                user_data = cur.fetchone()
        
        if user_data and check_password_hash(user_data['password'], password):
            # Création de l'objet avec l'ID natif de la base (souvent un entier)
            user_obj = User(user_data['id'], user_data['username'])
            
            session.permanent = True
            login_user(user_obj, remember=True)
            
            next_page = request.args.get('next')
            if not next_page or not next_page.startswith('/'):
                next_page = url_for('index')
            return redirect(next_page)
        
        flash('Identifiants incorrects.')
    return render_template('login.html')
    
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
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT * FROM Recettes ORDER BY categorie, nom')
            recettes = cur.fetchall()
    
    recettes_par_categorie = {}
    categories = set()
    for r in recettes:
        cat = r['categorie'] or "Sans catégorie"
        categories.add(cat)
        recettes_par_categorie.setdefault(cat, []).append(r)
    return render_template('index.html', recettes_par_categorie=recettes_par_categorie, categories=list(categories))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT * FROM users WHERE username = %s', (username,))
                user_data = cur.fetchone()
        
        if user_data and check_password_hash(user_data['password'], password):
            # On crée l'objet avec l'ID de la base
            user_obj = User(user_data['id'], user_data['username'])
            session.permanent = True
            login_user(user_obj, remember=True)
            
            next_page = request.args.get('next')
            if not next_page or not next_page.startswith('/'):
                next_page = url_for('index')
            return redirect(next_page)
        
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
        est_sous = True if 'est_sous_recette' in request.form else False
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
            flash("Recette ajoutée !")
            return redirect(url_for('index'))
        except Exception as e:
            return f"Erreur : {str(e)}"
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
                    for n, q, u in zip(request.form.getlist('ingredient_nom[]'), 
                                       request.form.getlist('ingredient_quantite[]'), 
                                       request.form.getlist('ingredient_unite[]')):
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
    story.append(Paragraph("Ingrédients :", styles['Heading2']))
    for ing in ingredients:
        story.append(Paragraph(f"• {ing['quantite'] or ''} {ing['unite'] or ''} {ing['nom']}", styles['Normal']))
    doc.build(story)
    buffer.seek(0)
    return send_file(buffer, mimetype='application/pdf', download_name=f"{recette['nom']}.pdf")

@app.route('/recette/<int:id>/supprimer', methods=['POST'])
@login_required
def supprimer_recette(id):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute('DELETE FROM Ingredients WHERE id_recette = %s', (id,))
            cur.execute('DELETE FROM SousRecettesUtilisees WHERE id_recette = %s OR id_sous_recette = %s', (id, id))
            cur.execute('DELETE FROM Recettes WHERE id = %s', (id,))
        conn.commit()
    return redirect(url_for('index'))

@app.route('/recherche')
@login_required
def rechercher_recette():
    terme = request.args.get('terme', '').strip()
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM Recettes WHERE nom ILIKE %s", (f'%{terme}%',))
            recettes = cur.fetchall()
    return render_template('recherche.html', recettes=recettes, terme=terme)

@app.route('/logout')
def logout():
    logout_user()
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)