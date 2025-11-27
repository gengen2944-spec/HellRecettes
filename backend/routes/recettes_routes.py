from flask import Blueprint, render_template

recettes_bp = Blueprint('recettes', __name__)

@recettes_bp.route('/recettes')
def liste_recettes():
    return render_template('recettes.html')
