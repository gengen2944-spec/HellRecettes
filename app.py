import os
from git import Repo
from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import timedelta
from flask_httpauth import HTTPBasicAuth
import sqlite3

# Fonction pour restaurer la base de données depuis GitHub
def restaurer_bdd_depuis_github():
    repo_url = os.getenv('GITHUB_DATA_REPO_URL', 'https://github.com/ton-utilisateur/gengen-recettes-data.git')
    repo_dir = "/tmp/gengen-recettes-data"
    try:
        if not os.path.exists(repo_dir):
            print("Clonage du dépôt des données...")
            Repo.clone_from(repo_url, repo_dir)
        if os.path.exists(f"{repo_dir}/recettes.db"):
            print("Restauration de recettes.db...")
            os.replace(f"{repo_dir}/recettes.db", "recettes.db")
        else:
            print("Aucun fichier recettes.db trouvé dans le dépôt des données.")
    except Exception as e:
        print(f"Erreur lors de la restauration de la base de données : {e}")

# Fonction pour sauvegarder la base de données vers GitHub
def sauvegarder_bdd_vers_github():
    repo_url = os.getenv('GITHUB_DATA_REPO_URL', 'https://github.com/ton-utilisateur/gengen-recettes-data.git')
    repo_dir = "/tmp/gengen-recettes-data"
    try:
        if not os.path.exists(repo_dir):
            print("Clonage du dépôt des données...")
            Repo.clone_from(repo_url, repo_dir)
        if os.path.exists("recettes.db"):
            print("Sauvegarde de recettes.db vers GitHub...")
            os.replace("recettes.db", f"{repo_dir}/recettes.db")
            repo = Repo(repo_dir)
            repo.git.add("recettes.db")
            repo.index.commit("Mise à jour automatique de la base de données")
            origin = repo.remote(name="origin")
            origin.push()
        else:
            print("Le fichier recettes.db n'existe pas localement.")
    except Exception as e:
        print(f"Erreur lors de la sauvegarde de la base de données : {e}")

# Initialisation de l'application Flask
app = Flask(__name__)
app.secret_key = '03FredGendronCestLePlus1974'  # Remplace par une clé secrète forte et unique
app.permanent_session_lifetime = timedelta(minutes=5)  # Durée de vie de la session

# Appelle la fonction de restauration au démarrage
restaurer_bdd_depuis_github()

# --- Le reste de ton code existant ---
from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import timedelta
from flask_httpauth import HTTPBasicAuth
import sqlite3

app = Flask(__name__)
app.secret_key = '03FredGendronCestLePlus1974'  # Remplace par une clé secrète forte et unique
app.permanent_session_lifetime = timedelta(minutes=5)  # Durée de vie de la session

auth = HTTPBasicAuth()

# Configuration des utilisateurs (remplace par tes propres identifiants)
users = {
    "SousChefs": generate_password_hash("SousChefs44")  # Nom d'utilisateur: admin, Mot de passe: admin
        }

@auth.verify_password
def verify_password(username, password):
    if username in users and check_password_hash(users[username], password):
        return username

# Configuration de Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Modèle utilisateur
class User(UserMixin):
    def __init__(self, id, username, password):
        self.id = id
        self.username = username
        self.password = password

@login_manager.user_loader
def load_user(user_id):
    conn = sqlite3.connect('recettes.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
    user_data = cursor.fetchone()
    conn.close()
    if user_data:
        return User(user_data[0], user_data[1], user_data[2])
    return None


# app = Flask(__name__)

def get_ingredients(recette_id):
    conn = sqlite3.connect('recettes.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM Ingredients WHERE id_recette = ?', (recette_id,))
    ingredients = cursor.fetchall()
    conn.close()
    return ingredients

def get_sous_recettes():
    conn = sqlite3.connect('recettes.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM Recettes WHERE est_sous_recette = TRUE')
    sous_recettes = cursor.fetchall()
    conn.close()
    return sous_recettes

def get_sous_recettes_utilisees(recette_id):
    conn = sqlite3.connect('recettes.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('''
        SELECT r.* FROM Recettes r
        JOIN SousRecettesUtilisees s ON r.id = s.id_sous_recette
        WHERE s.id_recette = ?
    ''', (recette_id,))
    sous_recettes = cursor.fetchall()
    conn.close()
    return sous_recettes

def est_sous_recette_utilisee(sous_recette_id):
    conn = sqlite3.connect('recettes.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('''
        SELECT r.id, r.nom FROM Recettes r
        JOIN SousRecettesUtilisees s ON r.id = s.id_recette
        WHERE s.id_sous_recette = ?
    ''', (sous_recette_id,))
    recettes = cursor.fetchall()
    conn.close()
    return recettes


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        conn = sqlite3.connect('recettes.db')
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE username = ?', (username,))
        user_data = cursor.fetchone()
        conn.close()
        if user_data and check_password_hash(user_data[2], password):
            user = User(user_data[0], user_data[1], user_data[2])
            login_user(user) 
            return redirect(url_for('index'))
        flash('Nom d\'utilisateur ou mot de passe incorrect.')
    return render_template('login.html')

@app.route('/logout')
def logout():
    logout_user()
    session.clear()  # Nettoyer la session
    return redirect(url_for('login'))


@app.route('/recette/<int:recette_id>')
@auth.login_required
def afficher_recette(recette_id):
    conn = sqlite3.connect('recettes.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM Recettes WHERE id = ?', (recette_id,))
    recette = cursor.fetchone()
    cursor.execute('SELECT * FROM Ingredients WHERE id_recette = ?', (recette_id,))
    ingredients = cursor.fetchall()
    cursor.execute('''
        SELECT r.* FROM Recettes r
        JOIN SousRecettesUtilisees s ON r.id = s.id_sous_recette
        WHERE s.id_recette = ?
    ''', (recette_id,))
    sous_recettes = cursor.fetchall()
    conn.close()
    return render_template('recette.html', recette=recette, ingredients=ingredients, sous_recettes=sous_recettes)


@app.route('/')
@auth.login_required
def index():
    # Connexion à la base de données
    conn = sqlite3.connect('recettes.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Récupérer toutes les recettes
    cursor.execute('SELECT * FROM Recettes ORDER BY categorie, nom')
    recettes = cursor.fetchall()

    # Organiser les recettes par catégorie
    recettes_par_categorie = {}
    categories = set()  # Ensemble pour stocker les catégories uniques

    for recette in recettes:
        categorie = recette['categorie']
        categories.add(categorie)  # Ajouter la catégorie à l'ensemble
        if categorie not in recettes_par_categorie:
            recettes_par_categorie[categorie] = []
        recettes_par_categorie[categorie].append(recette)

    conn.close()

    # Convertir l'ensemble en liste pour le template
    categories = list(categories)

    # Passer les données au template
    return render_template('index.html', recettes_par_categorie=recettes_par_categorie, categories=categories)


@app.route('/ajout', methods=['GET', 'POST'])
@auth.login_required
def ajouter_recette():
    sous_recettes = get_sous_recettes()
    if request.method == 'POST':
        # Récupérer les données de la recette
        nom = request.form.get('nom')
        description = request.form.get('description')
        categorie = request.form.get('categorie')
        est_sous_recette = 'est_sous_recette' in request.form

        # Sauvegarder la recette dans la base de données
        conn = sqlite3.connect('recettes.db')
        cursor = conn.cursor()

        # Insérer la recette
        cursor.execute(
            'INSERT INTO Recettes (nom, description, categorie, est_sous_recette) VALUES (?, ?, ?, ?)',
            (nom, description, categorie, est_sous_recette)
        )
        recette_id = cursor.lastrowid  # Récupérer l'ID de la recette ajoutée

        # Récupérer et sauvegarder les ingrédients
        ingredient_noms = request.form.getlist('ingredient_nom[]')
        ingredient_quantites = request.form.getlist('ingredient_quantite[]')
        ingredient_unites = request.form.getlist('ingredient_unite[]')

        for nom, quantite, unite in zip(ingredient_noms, ingredient_quantites, ingredient_unites):
            cursor.execute(
                'INSERT INTO Ingredients (id_recette, nom, quantite, unite) VALUES (?, ?, ?, ?)',
                (recette_id, nom, quantite, unite)
            )

        # Récupérer les sous-recettes sélectionnées
        sous_recette_ids = request.form.getlist('sous_recette_id[]')

        # Ajouter les sous-recettes
        for sous_recette_id in sous_recette_ids:
            cursor.execute(
                'INSERT INTO SousRecettesUtilisees (id_recette, id_sous_recette) VALUES (?, ?)',
                (recette_id, sous_recette_id)
            ) 
        conn.commit()
        conn.close()
sauvegarder_bdd_vers_github()
        return redirect(url_for('index'))

    return render_template('ajouter.html', sous_recettes=sous_recettes)
    
from flask import send_file
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from io import BytesIO

@app.route('/recette/<int:recette_id>/modifier', methods=['GET', 'POST'])
@auth.login_required
def modifier_recette(recette_id):
    sous_recettes = get_sous_recettes()
    sous_recettes_utilisees = get_sous_recettes_utilisees(recette_id)

    if request.method == 'POST':
        # Récupérer les données de la recette
        nom = request.form.get('nom')
        description = request.form.get('description')
        categorie = request.form.get('categorie')
        est_sous_recette = 'est_sous_recette' in request.form

        # Mettre à jour la recette
        conn = sqlite3.connect('recettes.db')
        cursor = conn.cursor()
        cursor.execute(
            'UPDATE Recettes SET nom = ?, description = ?, categorie = ?, est_sous_recette = ? WHERE id = ?',
            (nom, description, categorie, est_sous_recette, recette_id)
        )

        # Supprimer les anciens ingrédients
        cursor.execute('DELETE FROM Ingredients WHERE id_recette = ?', (recette_id,))

        # Ajouter les nouveaux ingrédients
        ingredient_noms = request.form.getlist('ingredient_nom[]')
        ingredient_quantites = request.form.getlist('ingredient_quantite[]')
        ingredient_unites = request.form.getlist('ingredient_unite[]')

        for nom, quantite, unite in zip(ingredient_noms, ingredient_quantites, ingredient_unites):
            cursor.execute(
                'INSERT INTO Ingredients (id_recette, nom, quantite, unite) VALUES (?, ?, ?, ?)',
                (recette_id, nom, quantite, unite)
            )

        # Supprimer les anciennes sous-recettes
        cursor.execute('DELETE FROM SousRecettesUtilisees WHERE id_recette = ?', (recette_id,))

        # Récupérer les sous-recettes sélectionnées
        sous_recette_ids = request.form.getlist('sous_recette_id[]')

        # Ajouter les nouvelles sous-recettes
        for sous_recette_id in sous_recette_ids:
            cursor.execute(
                'INSERT INTO SousRecettesUtilisees (id_recette, id_sous_recette) VALUES (?, ?)',
                (recette_id, sous_recette_id)
            )

        conn.commit()
        conn.close()
sauvegarder_bdd_vers_github()
        return redirect(url_for('afficher_recette', recette_id=recette_id))

    # Récupérer les données de la recette et des ingrédients
    conn = sqlite3.connect('recettes.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM Recettes WHERE id = ?', (recette_id,))
    recette = cursor.fetchone()
    cursor.execute('SELECT * FROM Ingredients WHERE id_recette = ?', (recette_id,))
    ingredients = cursor.fetchall()
    conn.close()
sauvegarder_bdd_vers_github()
    return render_template('modifier_recette.html', recette=recette, ingredients=ingredients, sous_recettes=sous_recettes, sous_recettes_utilisees=sous_recettes_utilisees)

from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from io import BytesIO

@app.route('/recette/<int:recette_id>/imprimer')
@auth.login_required
def imprimer_recette(recette_id):
    # Connexion à la base de données
    conn = sqlite3.connect('recettes.db')
    conn.row_factory = sqlite3.Row  # Activer les résultats sous forme de dictionnaires
    cursor = conn.cursor()

    # Récupérer la recette et ses ingrédients
    cursor.execute('SELECT * FROM Recettes WHERE id = ?', (recette_id,))
    recette = cursor.fetchone()

    cursor.execute('SELECT * FROM Ingredients WHERE id_recette = ?', (recette_id,))
    ingredients = cursor.fetchall()

    cursor.execute('''
        SELECT r.* FROM Recettes r
        JOIN SousRecettesUtilisees s ON r.id = s.id_sous_recette
        WHERE s.id_recette = ?
    ''', (recette_id,))
    sous_recettes = cursor.fetchall()

    # Créer un buffer pour le PDF
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=72, leftMargin=72, topMargin=72, bottomMargin=72)

    # Styles pour le texte
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='CustomTitle', fontSize=16, leading=18, spaceAfter=10, borderWidth=1, borderColor=colors.black, borderPadding=5, textColor=colors.black, alignment=1))
    styles.add(ParagraphStyle(name='CustomSubtitle', fontSize=14, leading=16, spaceAfter=10))
    styles.add(ParagraphStyle(name='CustomNormal', fontSize=12, leading=14, spaceAfter=10))
    styles.add(ParagraphStyle(name='CustomListItem', fontSize=12, leading=14, leftIndent=20, spaceAfter=5))

    # Contenu du PDF
    story = []

    # Titre de la recette
    story.append(Paragraph(f"Recette : {recette['nom']}", styles['CustomTitle']))

    # Catégorie
    story.append(Paragraph(f"Catégorie : {recette['categorie']}", styles['CustomNormal']))

    # Description
    story.append(Paragraph("Description :", styles['CustomSubtitle']))
    description_lines = recette['description'].split('\n')
    for line in description_lines:
        if line.strip():
            story.append(Paragraph(line, styles['CustomNormal']))

    # Ingrédients
    story.append(Spacer(1, 10))
    story.append(Paragraph("Ingrédients :", styles['CustomSubtitle']))
    for ingredient in ingredients:
        story.append(Paragraph(f"• {ingredient['quantite']} {ingredient['unite']} de {ingredient['nom']}", styles['CustomListItem']))

    # Sous-recettes
    for sous_recette in sous_recettes:
        story.append(Spacer(1, 20))
        story.append(Paragraph(f"Sous-recette : {sous_recette['nom']}", styles['CustomSubtitle']))

        # Description de la sous-recette
        story.append(Paragraph("Description :", styles['CustomNormal']))
        sous_description_lines = sous_recette['description'].split('\n')
        for line in sous_description_lines:
            if line.strip():
                story.append(Paragraph(line, styles['CustomNormal']))

        # Ingrédients de la sous-recette
        story.append(Spacer(1, 10))
        story.append(Paragraph("Ingrédients :", styles['CustomNormal']))

        # Nouvelle connexion pour les ingrédients de la sous-recette
        sous_recette_conn = sqlite3.connect('recettes.db')
        sous_recette_conn.row_factory = sqlite3.Row  # Activer les résultats sous forme de dictionnaires
        sous_recette_cursor = sous_recette_conn.cursor()
        sous_recette_cursor.execute('SELECT * FROM Ingredients WHERE id_recette = ?', (sous_recette['id'],))
        sous_ingredients = sous_recette_cursor.fetchall()
        sous_recette_conn.close()

        for ingredient in sous_ingredients:
            story.append(Paragraph(f"• {ingredient['quantite']} {ingredient['unite']} de {ingredient['nom']}", styles['CustomListItem']))

    # Générer le PDF
    doc.build(story)
    buffer.seek(0)

    # Envoyer le PDF
    return send_file(
        buffer,
        mimetype='application/pdf',
        as_attachment=False,
        download_name=f"Recette_{recette['nom']}.pdf"
    )

# Route pour supprimer une recette
@app.route('/recette/<int:recette_id>/supprimer', methods=['POST'])
@auth.login_required
def supprimer_recette(recette_id):
    # Supprimer les ingrédients de la recette
    conn = sqlite3.connect('recettes.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM Ingredients WHERE id_recette = ?', (recette_id,))

    # Supprimer les liens vers les sous-recettes (sans supprimer les sous-recettes elles-mêmes)
    cursor.execute('DELETE FROM SousRecettesUtilisees WHERE id_recette = ?', (recette_id,))

    # Supprimer la recette
    cursor.execute('DELETE FROM Recettes WHERE id = ?', (recette_id,))

    conn.commit()
    conn.close()
sauvegarder_bdd_vers_github()
    return redirect(url_for('index'))


@app.route('/sous-recette/<int:sous_recette_id>/supprimer', methods=['POST'])
@auth.login_required
def supprimer_sous_recette(sous_recette_id):
    recettes_associees = est_sous_recette_utilisee(sous_recette_id)
    if recettes_associees:
        # Si la sous-recette est utilisée, afficher un message d'erreur avec les recettes associées
        recettes_noms = [recette['nom'] for recette in recettes_associees]
        return render_template('erreur_suppression_sous_recette.html', sous_recette_id=sous_recette_id, recettes=recettes_noms)

    # Si la sous-recette n'est pas utilisée, la supprimer
    conn = sqlite3.connect('recettes.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM Ingredients WHERE id_recette = ?', (sous_recette_id,))
    cursor.execute('DELETE FROM Recettes WHERE id = ?', (sous_recette_id,))
    conn.commit()
    conn.close()
sauvegarder_bdd_vers_github()
    return redirect(url_for('index'))

@app.route('/recherche')
@auth.login_required
def recherche():
    # Affiche simplement le formulaire de recherche
    return render_template('recherche.html')

@app.route('/rechercher', methods=['GET'])
@auth.login_required
def rechercher_recette():
    # Récupérer les paramètres de recherche
    terme = request.args.get('terme', '').strip()
    type_recherche = request.args.get('type_recherche', 'nom')
    categorie = request.args.get('categorie', '')

    # Connexion à la base de données
    conn = sqlite3.connect('recettes.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Construire la requête SQL en fonction des paramètres
    if not terme and categorie:
        # Si le terme est vide mais qu'une catégorie est sélectionnée, afficher toutes les recettes de cette catégorie
        query = 'SELECT * FROM Recettes WHERE categorie = ?'
        params = [categorie]
    else:
        # Sinon, utiliser la recherche classique
        if type_recherche == 'nom':
            query = 'SELECT * FROM Recettes WHERE nom LIKE ?'
            params = [f'%{terme}%']
        elif type_recherche == 'ingredient':
            query = '''
                SELECT DISTINCT r.* FROM Recettes r
                JOIN Ingredients i ON r.id = i.id_recette
                WHERE i.nom LIKE ?
            '''
            params = [f'%{terme}%']
        elif type_recherche == 'sous_recette':
            query = '''
                SELECT DISTINCT r.* FROM Recettes r
                JOIN SousRecettesUtilisees s ON r.id = s.id_recette
                JOIN Recettes sr ON s.id_sous_recette = sr.id
                WHERE sr.nom LIKE ?
            '''
            params = [f'%{terme}%']

        # Ajouter la condition pour la catégorie si elle est spécifiée
        if categorie:
            query += ' AND categorie = ?'
            params.append(categorie)

    # Exécuter la requête
    cursor.execute(query, params)
    recettes = cursor.fetchall()
    conn.close()

    # Afficher les résultats de la recherche
    return render_template('recherche.html', recettes=recettes, terme=terme, categorie=categorie)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
