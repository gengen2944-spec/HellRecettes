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
# Récupération de la clé secrète depuis Render (ou valeur par défaut sécurisée)
app.secret_key = os.environ.get('SECRET_KEY', 'EmmaLiam29!') 
# Configuration pour maintenir la connexion 31 jours
app.permanent_session_lifetime = timedelta(days=31)

# Correction de l'URL PostgreSQL pour Render/Python
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

# --- MIDDLEWARE DE SÉCURITÉ ---
@app.before_request
def check_login():
    # Liste blanche des routes accessibles sans être connecté
    exempt_routes = ['login', 'static', 'ping']
    if request.endpoint in exempt_routes:
        return None
    
    if not session.get('logged_in'):
        return redirect(url_for('login'))

# --- ROUTES TECHNIQUES ---
@app.route('/ping')
def ping():
    """Route pour UptimeRobot : réveille Render et Supabase"""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
        return "Service Active & Database Connected", 200
    except Exception as e:
        return f"Database Error: {e}", 500

# --- ROUTES PRINCIPALES ---

@app.route('/')
def index():
    try:
        # Définition de l'ordre d'affichage des catégories
        ordre_categories = ['ENTREES', 'PLATS', 'DESSERTS', 'BOULANGERIE', 'DIVERS']
        
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT * FROM Recettes ORDER BY nom')
                recettes = cur.fetchall()
        
        recettes_par_categorie = {}
        categories_trouvees = set()
        
        for r in recettes:
            cat = r['categorie'] or "DIVERS"
            categories_trouvees.add(cat)
            recettes_par_categorie.setdefault(cat, []).append(r)
        
        # Ajouter les catégories de la DB non listées dans l'ordre par défaut
        for c in categories_trouvees:
            if c not in ordre_categories:
                ordre_categories.append(c)
                
        return render_template('index.html', 
                               recettes_par_categorie=recettes_par_categorie, 
                               ordre_categories=ordre_categories)
    except Exception as e:
        return f"Erreur chargement index : {str(e)}"

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
                session.permanent = True # Active la durée de 31 jours
                return redirect(url_for('index'))
            else:
                flash('Identifiants incorrects', 'danger')
        except Exception as e:
            flash(f"Erreur technique de connexion : {e}", 'danger')
            
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# --- GESTION DES RECETTES ---

@app.route('/recette/<int:recette_id>')
def afficher_recette(recette_id):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT * FROM Recettes WHERE id = %s', (recette_id,))
            recette = cur.fetchone()
            
            cur.execute('SELECT * FROM Ingredients WHERE id_recette = %s', (recette_id,))
            ingredients = cur.fetchall()
            
            cur.execute('''SELECT r.* FROM Recettes r
                           JOIN SousRecettesUtilisees s ON r.id = s.id_sous_recette
                           WHERE s.id_recette = %s''', (recette_id,))
            sous_recettes = cur.fetchall()
            
    if not recette:
        return "Recette introuvable", 404
    return render_template('recette.html', recette=recette, ingredients=ingredients, sous_recettes=sous_recettes)

@app.route('/imprimer_book', methods=['POST'])
def imprimer_book():
    ids_selectionnes = request.form.getlist('selection')
    if not ids_selectionnes:
        flash("Aucune recette sélectionnée", "warning")
        return redirect(url_for('index'))

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    story = []

    def ajouter_bloc_recette(data_recette, est_principal=True):
        titre_style = styles['Title'] if est_principal else styles['Heading2']
        story.append(Paragraph(data_recette['nom'], titre_style))
        story.append(Spacer(1, 12))
        
        if data_recette['description']:
            story.append(Paragraph("Instructions :", styles['Heading3']))
            texte = data_recette['description'].replace('\r\n', '\n').replace('\n', '<br/>')
            story.append(Paragraph(texte, styles['Normal']))
            story.append(Spacer(1, 12))
        
        story.append(Paragraph("Ingrédients :", styles['Heading3']))
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT * FROM Ingredients WHERE id_recette = %s', (data_recette['id'],))
                ings = cur.fetchall()
        
        for ing in ings:
            q = ing['quantite'] if ing['quantite'] else ""
            u = ing['unite'] if ing['unite'] else ""
            story.append(Paragraph(f"• {q} {u} {ing['nom']}", styles['Normal']))
        
        story.append(Spacer(1, 24))
        story.append(Paragraph("<hr/>", styles['Normal']))
        story.append(Spacer(1, 24))

    for r_id in ids_selectionnes:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT * FROM Recettes WHERE id = %s', (r_id,))
                recette = cur.fetchone()
                if recette:
                    ajouter_bloc_recette(recette, True)
                    cur.execute('''SELECT r.* FROM Recettes r
                                   JOIN SousRecettesUtilisees s ON r.id = s.id_sous_recette
                                   WHERE s.id_recette = %s''', (r_id,))
                    for sr in cur.fetchall():
                        ajouter_bloc_recette(sr, False)

    doc.build(story)
    buffer.seek(0)
    return send_file(buffer, mimetype='application/pdf', download_name="Mon_Livre_Recettes.pdf")

@app.route('/recherche')
def rechercher_recette():
    terme = request.args.get('terme', '').strip()
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM Recettes WHERE nom ILIKE %s", (f'%{terme}%',))
            recettes = cur.fetchall()
    return render_template('recherche.html', recettes=recettes, terme=terme)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)