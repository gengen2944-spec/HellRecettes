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
# Utilisation de la variable d'environnement pour la sécurité
app.secret_key = os.environ.get('SECRET_KEY', 'EmmaLiam29!') 

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
def index():
    ordre_categories = [
        'A picorer', 
        'Entrées/Plat', 
        'Desserts', 
        'Sauce/Marinade/Condiments'
    ]
    
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT * FROM recettes ORDER BY nom ASC')
            toutes_les_recettes = cur.fetchall()

    recettes_par_categorie = {cat: [] for cat in ordre_categories}
    recettes_par_categorie['Divers'] = [] # Colonne de secours

    for r in toutes_les_recettes:
        # On enlève les espaces superflus pour la comparaison
        cat_recette = r['categorie'].strip() if r['categorie'] else ""
        
        found = False
        for cat_fixe in ordre_categories:
            if cat_recette.lower() == cat_fixe.lower():
                recettes_par_categorie[cat_fixe].append(r)
                found = True
                break
        
        if not found:
            recettes_par_categorie['Divers'].append(r)

    # On ne passe à l'affichage que les catégories qui ont des recettes
    categories_a_afficher = [c for c in ordre_categories if recettes_par_categorie[c]]
    if recettes_par_categorie['Divers']:
        categories_a_afficher.append('Divers')

    return render_template('index.html', 
                           recettes_par_categorie=recettes_par_categorie, 
                           ordre_categories=categories_a_afficher)

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
            return redirect(url_for('index'))
        except Exception as e:
            return f"Erreur lors de l'ajout : {str(e)}"
    return render_template('ajouter.html', sous_recettes=get_sous_recettes())

@app.route('/recette/<int:recette_id>/modifier', methods=['GET', 'POST'])
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
            return f"Erreur modification : {str(e)}"

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT * FROM Recettes WHERE id = %s', (recette_id,))
            recette = cur.fetchone()
    return render_template('modifier_recette.html', recette=recette, ingredients=get_ingredients(recette_id), 
                           sous_recettes=get_sous_recettes(), sous_recettes_utilisees=get_sous_recettes_utilisees(recette_id))

@app.route('/recette/<int:recette_id>/imprimer')
def imprimer_recette(recette_id):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            # 1. Récupérer la recette principale
            cur.execute('SELECT * FROM Recettes WHERE id = %s', (recette_id,))
            recette_principale = cur.fetchone()
            
            # 2. Récupérer les sous-recettes liées
            cur.execute('''SELECT r.* FROM Recettes r
                           JOIN SousRecettesUtilisees s ON r.id = s.id_sous_recette
                           WHERE s.id_recette = %s''', (recette_id,))
            sous_recettes = cur.fetchall()

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    story = []

    # Fonction pour ajouter une recette complète au PDF sans préfixe
    def ajouter_bloc_recette(data_recette, est_principal=True):
        # On utilise un style de titre légèrement plus petit pour les sous-recettes 
        # pour garder une hiérarchie visuelle, mais sans texte ajouté
        titre_style = styles['Title'] if est_principal else styles['Heading1']
        
        story.append(Paragraph(data_recette['nom'], titre_style))
        story.append(Spacer(1, 12))
        
        # Description / Instructions
        if data_recette['description']:
            story.append(Paragraph("Instructions :", styles['Heading2']))
            
            # 1. Nettoyage des \r\n résiduels
            texte_propre = data_recette['description'].replace('\\r\\n', '\n').replace('\\n', '\n')
            
            # 2. Conversion des sauts de ligne en balises <br/> pour ReportLab
            # Cela permet de garder chaque étape sur une nouvelle ligne
            description_formatee = texte_propre.replace('\n', '<br/>')
            
            story.append(Paragraph(description_formatee, styles['Normal']))
            story.append(Spacer(1, 12))
        
        # Ingrédients
        story.append(Paragraph("Ingrédients :", styles['Heading2']))
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT * FROM Ingredients WHERE id_recette = %s', (data_recette['id'],))
                ingredients = cur.fetchall()
        
        for ing in ingredients:
            quantite = ing['quantite'] if ing['quantite'] else ""
            unite = ing['unite'] if ing['unite'] else ""
            story.append(Paragraph(f"• {quantite} {unite} {ing['nom']}", styles['Normal']))
        
        # Séparation visuelle entre les blocs
        story.append(Spacer(1, 24))
        story.append(Paragraph("<hr/>", styles['Normal']))
        story.append(Spacer(1, 24))

    # --- Construction du document ---
    
    # 1. Ajouter la recette de base
    ajouter_bloc_recette(recette_principale, est_principal=True)
    
    # 2. Ajouter chaque sous-recette à la suite
    for sr in sous_recettes:
        ajouter_bloc_recette(sr, est_principal=False)
    
    doc.build(story)
    buffer.seek(0)

    # Nettoyage du nom de fichier : on remplace les espaces par des underscores
    # et on s'assure qu'il n'y a pas de caractères interdits
    nom_fichier = "".join([c if c.isalnum() else "_" for c in recette_principale['nom']])
    
    return send_file(
        buffer, 
        mimetype='application/pdf', 
        as_attachment=False, # Garde l'ouverture dans un nouvel onglet
        download_name=f"{nom_fichier}.pdf"
    )
    
# Correction ici : recette_id au lieu de id pour correspondre au HTML

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

# --- ROUTE LOGIN ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # Utilisation du nom de table 'users'
                cur.execute('SELECT * FROM users WHERE username = %s AND password = %s', 
                           (username, password))
                user = cur.fetchone()
        
        if user:
            session['logged_in'] = True
            session.permanent = True 
            return redirect(url_for('index'))
        else:
            flash('Identifiants incorrects', 'danger')
            
    return render_template('login.html')

# --- FILTRE DE SÉCURITÉ ---
@app.before_request
def check_login():
    # On laisse passer le login et les fichiers CSS/Images
    if request.endpoint not in ['login', 'static'] and not session.get('logged_in'):
        return redirect(url_for('login'))

# --- LOGOUT ---
@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)