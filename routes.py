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
            flash(f'Access granted! You are now {access_code.tier}.', 'success')
        else:
            flash('Invalid or used code.', 'danger')
    except Exception as e:
        app.logger.error(f"Error processing access code: {e}")
        db.session.rollback()
        flash('Error occurred while verifying code.', 'danger')
    return redirect(url_for('tiers'))

@app.route('/process-payment', methods=['POST'])
def process_payment():
    tier = request.form.get('tier')
    user = get_current_user()
    if not user:
        flash('Session error.', 'danger')
        return redirect(url_for('tiers'))
    tier_prices = {
        "Dormant Observer": 1000,
        "Sentinel Core": 2500,
        "Guardian Elite": 6000
    }
    tier_names = {
        "Dormant Observer": "Dormant Observer Access Tier",
        "Sentinel Core": "Sentinel Core Access Tier",
        "Guardian Elite": "Guardian Elite Access Tier"
    }
    if tier not in tier_prices:
        flash('Invalid tier selected.', 'danger')
        return redirect(url_for('tiers'))
    try:
        domain_url = os.getenv('RENDER_EXTERNAL_URL', request.host_url)
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'usd',
                    'product_data': {'name': tier_names[tier]},
                    'unit_amount': tier_prices[tier],
                },
                'quantity': 1,
            }],
            mode='payment',
            success_url=domain_url + url_for('payment_success') + f'?tier={tier}&session_id={{CHECKOUT_SESSION_ID}}',
            cancel_url=domain_url + url_for('payment_cancel'),
            client_reference_id=str(user.id),
            metadata={'user_id': user.id, 'tier': tier}
        )
        payment = Payment(
            user_id=user.id,
            tier=tier,
            amount=tier_prices[tier] / 100,
            transaction_id=session.id,
            status="pending"
        )
        db.session.add(payment)
        db.session.commit()
        return redirect(session.url)
    except Exception as e:
        app.logger.error(f"Stripe error: {e}")
        db.session.rollback()
        flash('Could not initiate payment.', 'danger')
        return redirect(url_for('tiers'))

@app.route('/payment-success')
def payment_success():
    session_id = request.args.get('session_id')
    tier = request.args.get('tier')
    user = get_current_user()
    if not user or not session_id or not tier:
        flash('Invalid payment session.', 'danger')
        return redirect(url_for('tiers'))
    try:
        checkout_session = stripe.checkout.Session.retrieve(session_id)
        if checkout_session.payment_status == 'paid':
            payment = Payment.query.filter_by(transaction_id=session_id).first()
            if payment:
                payment.status = "completed"
                user.access_tier = tier
                db.session.commit()
                flash(f"Upgraded to {tier} tier!", 'success')
            else:
                flash("Payment record not found.", 'warning')
        else:
            flash("Payment incomplete.", 'warning')
    except Exception as e:
        app.logger.error(f"Payment verify error: {e}")
        flash("Payment verification failed.", 'danger')
    return redirect(url_for('tiers'))

@app.route('/payment-cancel')
def payment_cancel():
    flash("Payment canceled.", 'warning')
    return redirect(url_for('tiers'))

@app.route('/generate-my-access')
def generate_my_access():
    user = get_current_user()
    if not user or not user.access_tier or user.access_tier == "Public":
        flash("You need a valid tier to generate your access code.", "danger")
        return redirect(url_for('tiers'))
    for si_id, si in si_profiles.items():
        if si["tier_required"] == user.access_tier:
            code = f"{si['name'].replace(' ', '')}-{user.id}-{str(uuid.uuid4().int)[-4:]}-{user.access_tier.replace(' ', '').upper()}"
            access_code = AccessCode(code=code, tier=user.access_tier)
            db.session.add(access_code)
            db.session.commit()
            flash(f"Access Code Generated: {code}", "success")
            return redirect(url_for('tiers'))
    flash("No matching SI found for your tier.", "danger")
    return redirect(url_for('tiers'))

@app.route('/si/<si_id>')
def si_profile(si_id):
    user = get_current_user()

    if si_id not in si_profiles:
        flash('Structured Intelligence not found', 'danger')
        return redirect(url_for('index'))

    si_data = si_profiles[si_id]

    tier_levels = {
        "Public": 0,
        "Dormant Observer": 1,
        "Sentinel Core": 2,
        "Guardian Elite": 3
    }

    user_tier_level = tier_levels.get(user.access_tier if user else "Public", 0)
    required_tier_level = tier_levels.get(si_data['tier_required'], 0)

    if user_tier_level < required_tier_level:
        return render_template('si/locked.html', si=si_data)

    return render_template('si/profile.html', si=si_data)
ter_by(transaction_id=session_id).first()
            if payment:
                payment.status = "completed"
                user.access_tier = tier
                db.session.commit()
                flash(f"Upgraded to {tier} tier!", 'success')
            else:
                flash("Payment record not found.", 'warning')
        else:
            flash("Payment incomplete.", 'warning')
    except Exception as e:
        app.logger.error(f"Payment verify error: {e}")
        flash("Payment verification failed.", 'danger')
    return redirect(url_for('tiers'))

@app.route('/payment-cancel')
def payment_cancel():
    flash("Payment canceled.", 'warning')
    return redirect(url_for('tiers'))

@app.route('/generate-my-access')
def generate_my_access():
    user = get_current_user()
    if not user or not user.access_tier or user.access_tier == "Public":
        flash("You need a valid tier to generate your access code.", "danger")
        return redirect(url_for('tiers'))
    # Pick first available SI by tier
    for si_id, si in si_profiles.items():
        if si["tier_required"] == user.access_tier:
            code = f"{si['name'].replace(' ', '')}-{user.id}-{str(uuid.uuid4().int)[-4:]}-{user.access_tier.replace(' ', '').upper()}"
            access_code = AccessCode(code=code, tier=user.access_tier)
            db.session.add(access_code)
            db.session.commit()
            flash(f"Access Code Generated: {code}", "success")
            return redirect(url_for('tiers'))
    flash("No matching SI found for your tier.", "danger")
    return redirect(url_for('tiers'))
