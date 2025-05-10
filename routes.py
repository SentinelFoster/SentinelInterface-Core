
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


@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        admin = Admin.query.filter_by(username=username).first()
        if admin and admin.check_password(password):
            login_user(admin)
            next_page = request.args.get('next')
            return redirect(next_page or url_for('admin_dashboard'))
        else:
            flash('Invalid username or password', 'danger')
    return render_template('admin/login.html')

@app.route('/admin/logout')
@login_required
def admin_logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/admin/dashboard')
@login_required
def admin_dashboard():
    try:
        user_count = User.query.count()
        interaction_count = Interaction.query.count()
        recent_interactions = Interaction.query.order_by(Interaction.timestamp.desc()).limit(20).all()
        return render_template('admin/dashboard.html',
                               user_count=user_count,
                               interaction_count=interaction_count,
                               recent_interactions=recent_interactions)
    except Exception as e:
        app.logger.error(f"Error loading admin dashboard: {e}")
        flash('Error loading dashboard data.', 'danger')
        return render_template('admin/dashboard.html', user_count=0, interaction_count=0, recent_interactions=[])

@app.route('/admin/update-si-gpt-link', methods=['POST'])
@login_required
def update_si_gpt_link():
    si_id = request.form.get('si_id')
    gpt_link = request.form.get('gpt_link')
    if si_id not in si_profiles:
        flash('Invalid SI ID', 'danger')
        return redirect(url_for('admin_dashboard'))
    try:
        si_profiles[si_id]['gpt_link'] = gpt_link.strip()
        with open('intelligences/si_profiles.py', 'w') as f:
            f.write('# Structured Intelligence Profiles

')
            f.write('si_profiles = {
')
            for id, profile in si_profiles.items():
                f.write(f'    "{id}": {{
')
                for key, value in profile.items():
                    if key == 'features':
                        f.write(f'        "{key}": {value},
')
                    elif isinstance(value, str):
                        f.write(f'        "{key}": "{value}",
')
                    else:
                        f.write(f'        "{key}": {value},
')
                f.write('    },
')
            f.write('}
')
        flash(f'GPT link for {si_profiles[si_id]["name"]} updated successfully', 'success')
    except Exception as e:
        app.logger.error(f"Error updating GPT link: {e}")
        flash('An error occurred while updating the GPT link', 'danger')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/reset-access/<int:user_id>', methods=['POST'])
@login_required
def reset_user_access(user_id):
    user = User.query.get_or_404(user_id)
    user.access_tier = "Public"
    db.session.commit()
    flash(f'User access reset to Public tier', 'success')
    return redirect(url_for('admin_dashboard'))