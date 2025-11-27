import sqlite3

def init_db():
    conn = sqlite3.connect('recettes.db')
    cursor = conn.cursor()

    # Créer la table Recettes
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Recettes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nom TEXT NOT NULL,
            description TEXT,
            categorie TEXT,
            est_sous_recette BOOLEAN DEFAULT FALSE
        )
    ''')

    # Créer la table Ingredients
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Ingredients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            id_recette INTEGER,
            nom TEXT NOT NULL,
            quantite REAL,
            unite TEXT,
            FOREIGN KEY(id_recette) REFERENCES Recettes(id)
        )
    ''')

    # Créer la table SousRecettesUtilisées
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS SousRecettesUtilisees (
            id_recette INTEGER,
            id_sous_recette INTEGER,
            FOREIGN KEY(id_recette) REFERENCES Recettes(id),
            FOREIGN KEY(id_sous_recette) REFERENCES Recettes(id)
        )
    ''')

    conn.commit()
    conn.close()

if __name__ == '__main__':
    init_db()
    print("Base de données initialisée avec succès !")
