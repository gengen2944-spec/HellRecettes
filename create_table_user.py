import sqlite3
from werkzeug.security import generate_password_hash

# Créer la table users
conn = sqlite3.connect('recettes.db')
cursor = conn.cursor()
cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL
    )
''')

# Vérifier si l'utilisateur 'admin' existe déjà
cursor.execute('SELECT * FROM users WHERE username = ?', ('admin',))
user = cursor.fetchone()

if not user:
    # Ajouter l'utilisateur 'admin'
    hashed_password = generate_password_hash('admin')
    cursor.execute('INSERT INTO users (username, password) VALUES (?, ?)', ('admin', hashed_password))
    conn.commit()
    print("Utilisateur 'admin' ajouté avec succès.")
else:
    print("L'utilisateur 'admin' existe déjà.")

conn.close()
