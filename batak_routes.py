"""
Batak Demo Landing Page Routes
Add these routes to your app.py or register as a blueprint
"""

from flask import Blueprint, render_template

# Create blueprint
batak_bp = Blueprint('batak', __name__, url_prefix='/batak')


@batak_bp.route('/')
@batak_bp.route('/demo')
def batak_demo():
    """
    Render the Batak demo landing page.
    This is a one-pager showcasing multiple restaurant locations
    with integrated booking widgets.
    """
    return render_template('batak_demo.html')


# Location-specific widget IDs for reference
BATAK_LOCATIONS = {
    'batak_kajzerica': {
        'name': 'Batak Kajzerica',
        'address': 'Remetinečka 14, Zagreb',
        'phone': '01 4888 001',
        'hours': 'Mon-Sun: 10:00 - 23:00'
    },
    'batak_radnicka': {
        'name': 'Batak Radnička',
        'address': 'Radnička cesta 37c, Zagreb',
        'phone': '01 606 1155',
        'hours': 'Mon-Sun: 10:00 - 23:00'
    },
    'batak_kvatric': {
        'name': 'Batak Kvatrić',
        'address': 'Jakova Gotovca 1, Zagreb',
        'phone': '01 4664 331',
        'hours': 'Mon-Sun: 10:00 - 23:00'
    },
    'batak_centar': {
        'name': 'Batak Centar Cvjetni',
        'address': 'Trg Petra Preradovića 6, Zagreb',
        'phone': '091 462 2334',
        'hours': 'Mon-Sun: 10:00 - 23:00'
    }
}
