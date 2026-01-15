import os
from git import Repo
import shutil

# Configuration
GITHUB_TOKEN = "<ton-token-github>"  # Remplace par ton token GitHub
REPO_URL = f"https://{GITHUB_TOKEN}@github.com/gengen2944-spec/gengen-recettes-data.git"
REPO_DIR = "/tmp/gengen-recettes-data-test"  # Dossier temporaire pour le test
LOCAL_DB_PATH = "recettes.db"  # Chemin local de ta base de données

def test_clone_repo():
    """Teste le clonage du dépôt GitHub."""
    try:
        if os.path.exists(REPO_DIR):
            shutil.rmtree(REPO_DIR)  # Supprime le dossier s'il existe déjà

        print(f"Clonage du dépôt depuis {REPO_URL}...")
        Repo.clone_from(REPO_URL, REPO_DIR)
        print("✅ Dépôt cloné avec succès.")

        # Vérifie si recettes.db existe dans le dépôt cloné
        cloned_db_path = os.path.join(REPO_DIR, "recettes.db")
        if os.path.exists(cloned_db_path):
            print(f"✅ Fichier recettes.db trouvé dans {REPO_DIR}.")
            print(f"Taille du fichier : {os.path.getsize(cloned_db_path)} octets.")
        else:
            print(f"❌ Fichier recettes.db introuvable dans {REPO_DIR}.")
            print(f"Contenu du dossier : {os.listdir(REPO_DIR)}")

    except Exception as e:
        print(f"❌ Erreur lors du clonage : {e}")

def test_save_db():
    """Teste la sauvegarde de recettes.db vers GitHub."""
    try:
        if not os.path.exists(REPO_DIR):
            print(f"Clonage du dépôt pour le test de sauvegarde...")
            Repo.clone_from(REPO_URL, REPO_DIR)

        # Simule une copie de recettes.db vers le dépôt cloné
        if os.path.exists(LOCAL_DB_PATH):
            shutil.copy(LOCAL_DB_PATH, os.path.join(REPO_DIR, "recettes.db"))
            print(f"✅ Fichier {LOCAL_DB_PATH} copié vers {REPO_DIR}.")

            # Commit et push
            repo = Repo(REPO_DIR)
            repo.git.add("recettes.db")
            repo.index.commit("Test : Mise à jour de recettes.db")
            origin = repo.remote(name="origin")
            origin.push()
            print("✅ Fichier sauvegardé sur GitHub avec succès.")
        else:
            print(f"❌ Fichier {LOCAL_DB_PATH} introuvable en local.")

    except Exception as e:
        print(f"❌ Erreur lors de la sauvegarde : {e}")

if __name__ == "__main__":
    print("=== Test de clonage du dépôt ===")
    test_clone_repo()

    print("\n=== Test de sauvegarde de recettes.db ===")
    test_save_db()
