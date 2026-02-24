import os
from datetime import timedelta
from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file
import psycopg2
from psycopg2.extras import RealDictCursor
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak

# --- CONFIGURATION ---
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'EmmaLiam29!') 
app.permanent_session_lifetime = timedelta(days=31)

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

# --- NOUVELLE ROUTE : KEEP-ALIVE (UPTIME ROBOT) ---

@app.route('/ping')
def ping():
    """Route pour empêcher la mise en veille de Render et Supabase"""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # Exécute une requête minimale pour simuler une activité SQL
                cur.execute("SELECT 1")
                cur.fetchone()
        return "Service Active & Database Connected", 200
    except Exception as e:
        print(f"Erreur lors du ping : {e}")
        return f"Database Error: {e}", 500

# --- SUITE DU CODE EXISTANT ---

def recuperer_categories():
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT nom FROM Categories ORDER BY nom ASC")
                return [row['nom'] for row in cur.fetchall()]
    except Exception as e:
        print(f"Erreur catégories : {e}")
        return []

# ... (Le reste de tes fonctions utilitaires reste inchangé)

def get_ingredients(recette_id):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT * FROM Ingredients WHERE id_recette = %s', (recette_id,))
            return cur.fetchall()

# ... (Gardez toutes les autres fonctions et routes telles quelles jusqu'à check_login)

@app.before_request
def check_login():
    # AJOUT DE 'ping' à la liste des exceptions pour permettre à UptimeRobot d'y accéder sans login
    if request.endpoint not in ['login', 'static', 'ping'] and not session.get('logged_in'):
        return redirect(url_for('login'))

# ... (Fin du fichier avec logout et le bloc if __name__ == '__main__':)

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)