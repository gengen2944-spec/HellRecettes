#
#
#  Version 2.0
#   07/05/2026  ajout de la route Warmup pour generation de trafic
#
#
#
import os
from datetime import timedelta
from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file
import psycopg2
from psycopg2.extras import RealDictCursor
from io import BytesIO

# Imports ReportLab mis à jour pour les cadres, le sommaire et la pagination
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, CondPageBreak
from reportlab.lib import colors

# --- CONFIGURATION ---
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'EmmaLiam29!') 
app.permanent_session_lifetime = timedelta(days=31)

DATABASE_URL = os.environ.get('DATABASE_URL')
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Liste globale des catégories
CATEGORIES_LISTE = ['Entrées/Plat', 'A picorer', 'Desserts', 'Sauce/Marinade/Condiments']

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
    exempt_routes = ['login', 'static', 'ping', 'keepalive', 'warmup']
    if request.endpoint in exempt_routes:
        return None
    if not session.get('logged_in'):
        return redirect(url_for('login'))

#------route pour maintenir render actif---------
@app.route('/ping')
def ping():
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        return "Service Active", 200
    except Exception as e:
        return f"Error: {e}", 500

#-------route pour generer du trafic pour supabase-----------en plus keepalive
@app.route('/warmup')
def warmup():
    try:
        results = {}
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM Recettes")
                results['recettes'] = cur.fetchone()['count']
                cur.execute("SELECT COUNT(*) FROM Ingredients")
                results['ingredients'] = cur.fetchone()['count']
                cur.execute("SELECT COUNT(*) FROM SousRecettesUtilisees")
                results['sous_recettes'] = cur.fetchone()['count']
                cur.execute("SELECT id, nom FROM Recettes ORDER BY id DESC LIMIT 5")
                results['dernières'] = [r['nom'] for r in cur.fetchall()]
        return {"status": "ok", "timestamp": str(__import__('datetime').datetime.now()), "data": results}, 200
    except Exception as e:
        return {"status": "error", "message": str(e)}, 500
        
#------route pour maintenir supabase actif---------
@app.route('/keepalive')
def keepalive():
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM Recettes")
                count = cur.fetchone()['count']
        return f"OK - {count} recettes", 200
    except Exception as e:
        return f"Erreur: {e}", 500

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
        ordre_categories = CATEGORIES_LISTE + ['DIVERS']
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT * FROM Recettes ORDER BY nom')
                recettes = cur.fetchall()
        
        recettes_par_categorie = {}
        for r in recettes:
            cat = r['categorie'] or "DIVERS"
            recettes_par_categorie.setdefault(cat, []).append(r)
            
        return render_template('index.html', 
                               recettes_par_categorie=recettes_par_categorie, 
                               ordre_categories=ordre_categories,
                               categories=CATEGORIES_LISTE)
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
@app.route('/ajout', methods=['GET', 'POST'])
def ajouter_recette():
    if request.method == 'POST':
        nom = request.form.get('nom').strip().capitalize()
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
                            nom_ing_propre = n.strip().capitalize()
                            cur.execute('INSERT INTO Ingredients (id_recette, nom, quantite, unite) VALUES (%s, %s, %s, %s)', (new_id, nom_ing_propre, q, u))
                    for sr_id in sr_ids:
                        if sr_id:
                            cur.execute('INSERT INTO SousRecettesUtilisees (id_recette, id_sous_recette) VALUES (%s, %s)', (new_id, sr_id))
                conn.commit()
            flash("Recette ajoutée !", "success")
            return redirect(url_for('index'))
        except Exception as e:
            flash(f"Erreur : {e}", "danger")

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT id, nom FROM Recettes WHERE est_sous_recette = True ORDER BY nom')
            sous_recettes = cur.fetchall()
    return render_template('ajouter.html', categories=CATEGORIES_LISTE, sous_recettes=sous_recettes)

@app.route('/modifier_recette/<int:recette_id>', methods=['GET', 'POST'])
@app.route('/modifier/<int:recette_id>', methods=['GET', 'POST'])
def modifier_recette(recette_id):
    if request.method == 'POST':
        nom = request.form.get('nom').strip().capitalize()
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
                            nom_ing_propre = n.strip().capitalize()
                            cur.execute('INSERT INTO Ingredients (id_recette, nom, quantite, unite) VALUES (%s, %s, %s, %s)', (recette_id, nom_ing_propre, q, u))
                    cur.execute('DELETE FROM SousRecettesUtilisees WHERE id_recette=%s', (recette_id,))
                    for sr_id in sr_ids:
                        if sr_id:
                            cur.execute('INSERT INTO SousRecettesUtilisees (id_recette, id_sous_recette) VALUES (%s, %s)', (recette_id, sr_id))
                conn.commit()
            flash("Recette modifiée !", "success")
            return redirect(url_for('afficher_recette', recette_id=recette_id))
        except Exception as e:
            flash(f"Erreur : {e}", "danger")

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT * FROM Recettes WHERE id=%s', (recette_id,))
            recette = cur.fetchone()
            cur.execute('SELECT * FROM Ingredients WHERE id_recette=%s', (recette_id,))
            ingredients = cur.fetchall()
            cur.execute('''SELECT r.id, r.nom FROM Recettes r JOIN SousRecettesUtilisees s ON r.id = s.id_sous_recette WHERE s.id_recette = %s''', (recette_id,))
            sous_recettes_utilisees = cur.fetchall()
            cur.execute('SELECT id, nom FROM Recettes WHERE id != %s AND est_sous_recette = True ORDER BY nom', (recette_id,))
            sous_recettes = cur.fetchall()
            
    return render_template('modifier_recette.html', recette=recette, ingredients=ingredients, 
                           sous_recettes_utilisees=sous_recettes_utilisees, 
                           sous_recettes=sous_recettes, categories=CATEGORIES_LISTE)

@app.route('/supprimer_recette/<int:recette_id>', methods=['GET', 'POST'])
@app.route('/supprimer/<int:recette_id>', methods=['GET', 'POST'])
def supprimer_recette(recette_id):
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT COUNT(*) FROM SousRecettesUtilisees WHERE id_sous_recette = %s', (recette_id,))
                usage_count = cur.fetchone()['count']
                
                if usage_count > 0:
                    flash(f"Impossible de supprimer : cette recette est utilisée comme sous-recette dans {usage_count} autre(s) plat(s).", "danger")
                    return redirect(url_for('afficher_recette', recette_id=recette_id))

                cur.execute('DELETE FROM SousRecettesUtilisees WHERE id_recette=%s', (recette_id,))
                cur.execute('DELETE FROM Ingredients WHERE id_recette=%s', (recette_id,))
                cur.execute('DELETE FROM Recettes WHERE id=%s', (recette_id,))
            conn.commit()
        flash("Recette supprimée avec succès", "info")
    except Exception as e:
        flash(f"Erreur technique lors de la suppression : {e}", "danger")
    return redirect(url_for('index'))

# --- IMPRESSION PDF (FONCTIONS AMÉLIORÉES) ---

def numeroter_pages(canvas, doc):
    canvas.saveState()
    canvas.setFont('Helvetica', 9)
    # On utilise doc.page à la place de doc.pageCounter
    canvas.drawCentredString(letter[0]/2, 20, f"Page {doc.page}")
    canvas.restoreState()

def generer_bloc_pdf(story, styles, data_recette, est_principal=True):
    # Création d'un cadre (Tableau) pour le titre
    bg_color = colors.whitesmoke if est_principal else colors.white
    border_width = 1.2 if est_principal else 0.5
    
    style_titre = styles['Title'] if est_principal else styles['Heading2']
    p_titre = Paragraph(f"<b>{data_recette['nom']}</b>", style_titre)
    
    tab_titre = Table([[p_titre]], colWidths=[460])
    tab_titre.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), bg_color),
        ('BORDER', (0, 0), (-1, -1), border_width, colors.black),
        ('TOPPADDING', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ('LEFTPADDING', (0, 0), (-1, -1), 15),
    ]))
    
    story.append(tab_titre)
    story.append(Spacer(1, 12))
    
    if data_recette['description']:
        story.append(Paragraph("<i>Instructions :</i>", styles['Heading3']))
        texte = data_recette['description'].replace('\r\n', '\n').replace('\n', '<br/>')
        story.append(Paragraph(texte, styles['Normal']))
        story.append(Spacer(1, 8))

    story.append(Paragraph("<i>Ingrédients :</i>", styles['Heading3']))
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT * FROM Ingredients WHERE id_recette = %s', (data_recette['id'],))
            ings = cur.fetchall()
    for ing in ings:
        q, u = (ing['quantite'] or ""), (ing['unite'] or "")
        story.append(Paragraph(f"&bull; {q} {u} {ing['nom']}", styles['Normal']))
    
    story.append(Spacer(1, 20))
    if not est_principal:
        story.append(Paragraph("<hr color='lightgrey' width='50%'/>", styles['Normal']))
        story.append(Spacer(1, 10))

@app.route('/recette/<int:recette_id>/imprimer')
def imprimer_recette(recette_id):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles, story = getSampleStyleSheet(), []
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT * FROM Recettes WHERE id = %s', (recette_id,))
            r = cur.fetchone()
            if r:
                generer_bloc_pdf(story, styles, r, True)
                cur.execute('''SELECT r.* FROM Recettes r JOIN SousRecettesUtilisees s ON r.id = s.id_sous_recette WHERE s.id_recette = %s''', (recette_id,))
                for sr in cur.fetchall():
                    generer_bloc_pdf(story, styles, sr, False)
    doc.build(story)
    buffer.seek(0)
    return send_file(buffer, mimetype='application/pdf', download_name=f"{r['nom']}.pdf")

@app.route('/imprimer_book', methods=['POST'])
def imprimer_book():
    ids = request.form.getlist('selection')
    if not ids: return redirect(url_for('index'))
    
    recettes_a_imprimer = []
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            for r_id in ids:
                cur.execute('SELECT * FROM Recettes WHERE id = %s', (r_id,))
                r = cur.fetchone()
                if r: recettes_a_imprimer.append(r)
    
    # Tri par catégorie (ordre de CATEGORIES_LISTE) puis par nom
    recettes_a_imprimer.sort(key=lambda x: (CATEGORIES_LISTE.index(x['categorie']) if x['categorie'] in CATEGORIES_LISTE else 99, x['nom']))

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles, story = getSampleStyleSheet(), []

    # --- SOMMAIRE ---
    story.append(Paragraph("Sommaire du Livre de Recettes", styles['Title']))
    story.append(Spacer(1, 20))
    current_cat = None
    for r in recettes_a_imprimer:
        if r['categorie'] != current_cat:
            current_cat = r['categorie']
            story.append(Spacer(1, 10))
            story.append(Paragraph(f"<b>{current_cat}</b>", styles['Heading2']))
        story.append(Paragraph(f"&bull; {r['nom']}", styles['Normal']))
    
    story.append(PageBreak())
# --- CORPS DU LIVRE ---
    # Cette boucle parcourt chaque recette sélectionnée et triée
    for r in recettes_a_imprimer:
        # CondPageBreak(600) : Saute à la page suivante SEULEMENT s'il reste 
        # moins de 600 points (environ 80% de la page). 
        # Cela évite de créer une page blanche si on est déjà en haut d'une page neuve.
        story.append(CondPageBreak(600)) 
        
        # 1. Générer le bloc de la recette principale (avec le grand cadre grisé)
        generer_bloc_pdf(story, styles, r, True)
        
        # 2. Chercher et générer les sous-recettes associées
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute('''SELECT r.* FROM Recettes r 
                               JOIN SousRecettesUtilisees s ON r.id = s.id_sous_recette 
                               WHERE s.id_recette = %s''', (r['id'],))
                sous_recettes = cur.fetchall()
                
                for sr in sous_recettes:
                    # On ajoute un petit espace avant la sous-recette
                    story.append(Spacer(1, 5))
                    # On génère le bloc (cadre plus fin, pas de fond grisé)
                    generer_bloc_pdf(story, styles, sr, False)

    # --- GÉNÉRATION FINALE ---
    # On utilise doc.page (et non pageCounter) pour éviter l'erreur AttributeError
    doc.build(story, onFirstPage=numeroter_pages, onLaterPages=numeroter_pages)
    
    buffer.seek(0)
    return send_file(buffer, mimetype='application/pdf', download_name="Livre_Hell_Recettes.pdf")

# --- RECHERCHE AVANCÉE (MISE À JOUR) ---
@app.route('/recherche')
def rechercher_recette():
    terme = request.args.get('terme', '').strip()
    type_recherche = request.args.get('type_recherche', 'nom')
    cat_filtre = request.args.get('categorie', '')
    
    recettes = []
    if terme or cat_filtre:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # On cherche à la fois dans le nom et les sous-recettes si c'est le type choisi
                sql = "SELECT DISTINCT r.* FROM Recettes r"
                params = []
                
                if type_recherche == 'ingredient':
                    sql += " LEFT JOIN Ingredients i ON r.id = i.id_recette WHERE i.nom ILIKE %s"
                    params.append(f'%{terme}%')
                elif type_recherche == 'sous_recette':
                    sql += " LEFT JOIN SousRecettesUtilisees sru ON r.id = sru.id_recette"
                    sql += " LEFT JOIN Recettes sr ON sru.id_sous_recette = sr.id"
                    sql += " WHERE (sr.nom ILIKE %s OR r.nom ILIKE %s)" # Recherche hybride
                    params.extend([f'%{terme}%', f'%{terme}%'])
                else:
                    sql += " WHERE r.nom ILIKE %s"
                    params.append(f'%{terme}%')
                
                if cat_filtre:
                    sql += " AND r.categorie = %s"
                    params.append(cat_filtre)
                
                sql += " ORDER BY r.nom"
                cur.execute(sql, tuple(params))
                recettes = cur.fetchall()
    
    return render_template('recherche.html', recettes=recettes, terme=terme, categories=CATEGORIES_LISTE)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)