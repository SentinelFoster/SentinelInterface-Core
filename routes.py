
import uuid
import os
import json
import stripe
from flask import render_template, redirect, url_for, request, flash, session, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from app import app, db
from models import Admin, User, Interaction, AccessCode, Payment
from intelligences.si_profiles import si_profiles

# Stripe API key setup
stripe.api_key = os.environ.get('STRIPE_SECRET_KEY')

@app.context_processor
def inject_si_profiles():
    return dict(si_profiles=si_profiles)

@app.before_request
def check_session():
    try:
        if 'user_session_id' not in session:
            session['user_session_id'] = str(uuid.uuid4())
            new_user = User(session_id=session['user_session_id'])
            db.session.add(new_user)
            db.session.commit()
    except Exception as e:
        app.logger.error(f"Error in check_session: {e}")
        if 'user_session_id' not in session:
            session['user_session_id'] = str(uuid.uuid4())

def get_current_user():
    if 'user_session_id' in session:
        try:
            return User.query.filter_by(session_id=session['user_session_id']).first()
        except Exception as e:
            app.logger.error(f"Error in get_current_user: {e}")
    return None

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/si/<si_id>')
def si_profile(si_id):
    user = get_current_user()
    if si_id not in si_profiles:
        flash('Structured Intelligence not found', 'danger')
        return redirect(url_for('index'))
    si_data = si_profiles[si_id]
    tier_levels = {"Public": 0, "Dormant Observer": 1, "Sentinel Core": 2, "Guardian Elite": 3}
    user_tier_level = tier_levels.get(user.access_tier if user else "Public", 0)
    required_tier_level = tier_levels.get(si_data['tier_required'], 0)
    if user_tier_level < required_tier_level:
        return render_template('si/locked.html', si=si_data)
    return render_template('si/profile.html', si=si_data)

@app.route('/si/<si_id>/interact', methods=['POST'])
def si_interact(si_id):
    user = get_current_user()
    user_input = request.form.get('user_input', '')
    if si_id not in si_profiles:
        return jsonify({'error': 'Structured Intelligence not found'}), 404
    si_data = si_profiles[si_id]
    response = f"{si_data['name']} acknowledges your message: '{user_input}'"
    if user:
        try:
            interaction = Interaction(user_id=user.id, si_id=si_id, user_input=user_input, si_response=response)
            db.session.add(interaction)
            db.session.commit()
        except Exception as e:
            app.logger.error(f"Error storing interaction: {e}")
            db.session.rollback()
    return jsonify({'response': response})

@app.route('/tiers')
def tiers():
    return render_template('payment/tiers.html')

@app.route('/access-code', methods=['POST'])
def process_access_code():
    code = request.form.get('access_code', '')
    user = get_current_user()
    if not user:
        flash('Session error. Please try again.', 'danger')
        return redirect(url_for('tiers'))
    try:
        access_code = AccessCode.query.filter_by(code=code, is_used=False).first()
        if access_code:
            user.access_tier = access_code.tier
            access_code.is_used = True
            access_code.used_by = user.id
            db.session.commit()
            flash(f'Access granted! Your account has been upgraded to {access_code.tier} tier.', 'success')
        else:
            flash('Invalid or already used access code', 'danger')
    except Exception as e:
        app.logger.error(f"Error processing access code: {e}")
        db.session.rollback()
        flash('An error occurred while processing your access code. Please try again.', 'danger')
    return redirect(url_for('tiers'))

@app.route('/admin/generate-code', methods=['POST'])
@login_required
def generate_access_code():
    tier = request.form.get('tier', '')
    si_id = request.form.get('si_id', '')
    user_name = request.form.get('user_name', '').strip().title()
    valid_tiers = ["Dormant Observer", "Sentinel Core", "Guardian Elite"]
    if tier not in valid_tiers or not user_name or si_id not in si_profiles:
        flash('Invalid tier, SI, or user name provided.', 'danger')
        return redirect(url_for('admin_dashboard'))
    si_name = si_profiles[si_id]["name"].replace(" ", "")
    unique_number = str(uuid.uuid4().int)[-4:]
    code = f"{si_name}-{user_name}-{unique_number}-{tier.replace(' ', '').upper()}"
    access_code = AccessCode(code=code, tier=tier)
    db.session.add(access_code)
    db.session.commit()
    flash(f'Access code generated: {code}', 'success')
    return redirect(url_for('admin_dashboard'))
