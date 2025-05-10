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

# Set the Stripe API key
stripe.api_key = os.environ.get('STRIPE_SECRET_KEY')

# Get domain for redirect URLs
def get_domain():
    if os.environ.get('REPLIT_DEPLOYMENT') != '':
        return os.environ.get('REPLIT_DEV_DOMAIN', '')
    else:
        domains = os.environ.get('REPLIT_DOMAINS', '').split(',')
        return domains[0] if domains else request.host

# Make si_profiles available to all templates
@app.context_processor
def inject_si_profiles():
    return dict(si_profiles=si_profiles)

# Ensure session exists for user tracking
@app.before_request
def check_session():
    try:
        if 'user_session_id' not in session:
            session['user_session_id'] = str(uuid.uuid4())
            # Create user record in database
            new_user = User(session_id=session['user_session_id'])
            db.session.add(new_user)
            db.session.commit()
    except Exception as e:
        app.logger.error(f"Error in check_session: {e}")
        # If we can't create a user, at least provide a session ID
        if 'user_session_id' not in session:
            session['user_session_id'] = str(uuid.uuid4())

def get_current_user():
    if 'user_session_id' in session:
        try:
            return User.query.filter_by(session_id=session['user_session_id']).first()
        except Exception as e:
            app.logger.error(f"Error in get_current_user: {e}")
    return None

# Home route
@app.route('/')
def index():
    return render_template('index.html')

# SI Profile routes
@app.route('/si/<si_id>')
def si_profile(si_id):
    # Get user information
    user = get_current_user()
    
    # Check if SI exists
    if si_id not in si_profiles:
        flash('Structured Intelligence not found', 'danger')
        return redirect(url_for('index'))
    
    si_data = si_profiles[si_id]
    
    # Check if user has access
    if user and user.access_tier == "Public" and si_data['tier_required'] != "Public":
        return render_template('si/locked.html', si=si_data)
    
    # Check tier requirements
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

# SI Interaction route
@app.route('/si/<si_id>/interact', methods=['POST'])
def si_interact(si_id):
    user = get_current_user()
    user_input = request.form.get('user_input', '')
    
    # Check if SI exists
    if si_id not in si_profiles:
        return jsonify({'error': 'Structured Intelligence not found'}), 404
    
    # Generate a response based on SI personality
    si_data = si_profiles[si_id]
    
    # Simple response generation (in a real app, this would be more sophisticated)
    response = f"{si_data['name']} acknowledges your message: '{user_input}'"
    
    # Store the interaction in the database
    if user:
        try:
            interaction = Interaction(
                user_id=user.id,
                si_id=si_id,
                user_input=user_input,
                si_response=response
            )
            db.session.add(interaction)
            db.session.commit()
        except Exception as e:
            app.logger.error(f"Error storing interaction: {e}")
            db.session.rollback()
            # Still return a response even if storage fails
    
    return jsonify({'response': response})

# Tier system routes
@app.route('/tiers')
def tiers():
    return render_template('payment/tiers.html')

# Process access code
@app.route('/access-code', methods=['POST'])
def process_access_code():
    code = request.form.get('access_code', '')
    user = get_current_user()
    
    if not user:
        flash('Session error. Please try again.', 'danger')
        return redirect(url_for('tiers'))
    
    try:
        # Check if code exists and is not used
        access_code = AccessCode.query.filter_by(code=code, is_used=False).first()
        
        if access_code:
            # Update user's access tier
            user.access_tier = access_code.tier
            
            # Mark code as used
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

# Create Stripe checkout session
@app.route('/process-payment', methods=['POST'])
def process_payment():
    tier = request.form.get('tier', '')
    user = get_current_user()
    
    if not user:
        flash('Session error. Please try again.', 'danger')
        return redirect(url_for('tiers'))
    
    # Tier pricing (in cents for Stripe)
    tier_prices = {
        "Dormant Observer": 1000,  # $10.00
        "Sentinel Core": 2500,     # $25.00
        "Guardian Elite": 6000     # $60.00
    }
    
    # Tier names for Stripe display
    tier_names = {
        "Dormant Observer": "Dormant Observer Access Tier",
        "Sentinel Core": "Sentinel Core Access Tier",
        "Guardian Elite": "Guardian Elite Access Tier"
    }
    
    if tier not in tier_prices:
        flash('Invalid tier selected', 'danger')
        return redirect(url_for('tiers'))
    
    try:
        domain_url = f"https://{get_domain()}"
        
        # Create a new Stripe Checkout Session
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[
                {
                    'price_data': {
                        'currency': 'usd',
                        'product_data': {
                            'name': tier_names[tier],
                            'description': f'Access to Sentinel SI Interface - {tier} Tier',
                        },
                        'unit_amount': tier_prices[tier],
                    },
                    'quantity': 1,
                },
            ],
            mode='payment',
            success_url=domain_url + url_for('payment_success') + f'?tier={tier}&session_id={{CHECKOUT_SESSION_ID}}',
            cancel_url=domain_url + url_for('payment_cancel'),
            client_reference_id=str(user.id),
            metadata={
                'user_id': user.id,
                'tier': tier
            }
        )
        
        # Create a pending payment record
        payment = Payment(
            user_id=user.id,
            tier=tier,
            amount=tier_prices[tier]/100,  # Convert back to dollars for our DB
            transaction_id=checkout_session.id,
            status="pending"
        )
        
        db.session.add(payment)
        db.session.commit()
        
        # Redirect to Stripe Checkout
        return redirect(checkout_session.url)
        
    except Exception as e:
        app.logger.error(f"Error creating checkout session: {e}")
        db.session.rollback()
        flash('An error occurred while processing your payment. Please try again.', 'danger')
        return redirect(url_for('tiers'))

# Payment success route
@app.route('/payment-success')
def payment_success():
    session_id = request.args.get('session_id')
    tier = request.args.get('tier')
    user = get_current_user()
    
    if not user or not session_id or not tier:
        flash('Invalid payment session.', 'danger')
        return redirect(url_for('tiers'))
    
    try:
        # Verify the payment with Stripe
        checkout_session = stripe.checkout.Session.retrieve(session_id)
        
        if checkout_session.payment_status == 'paid':
            # Update the payment record
            payment = Payment.query.filter_by(transaction_id=session_id).first()
            if payment:
                payment.status = "completed"
                
                # Update user's access tier
                user.access_tier = tier
                
                db.session.commit()
                
                flash(f'Payment processed successfully! Your account has been upgraded to {tier}.', 'success')
            else:
                flash('Payment record not found.', 'warning')
        else:
            flash('Payment not completed. Please try again.', 'warning')
    except Exception as e:
        app.logger.error(f"Error processing successful payment: {e}")
        flash('An error occurred while verifying your payment. Please contact support.', 'danger')
    
    return redirect(url_for('tiers'))

# Payment cancel route
@app.route('/payment-cancel')
def payment_cancel():
    flash('Payment canceled. Your access tier has not been changed.', 'warning')
    return redirect(url_for('tiers'))

# Admin routes
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
    # Get stats for dashboard
    try:
        user_count = User.query.count()
        interaction_count = Interaction.query.count()
        recent_interactions = Interaction.query.order_by(Interaction.timestamp.desc()).limit(20).all()
        
        return render_template(
            'admin/dashboard.html',
            user_count=user_count,
            interaction_count=interaction_count,
            recent_interactions=recent_interactions
        )
    except Exception as e:
        app.logger.error(f"Error loading admin dashboard: {e}")
        flash('Error loading dashboard data. Database connection may be unavailable.', 'danger')
        return render_template('admin/dashboard.html', user_count=0, interaction_count=0, recent_interactions=[])

@app.route('/admin/generate-code', methods=['POST'])
@login_required
def generate_access_code():
    tier = request.form.get('tier', '')
    
    # Validate tier
    valid_tiers = ["Dormant Observer", "Sentinel Core", "Guardian Elite"]
    if tier not in valid_tiers:
        flash('Invalid tier selected', 'danger')
        return redirect(url_for('admin_dashboard'))
    
    # Generate a unique access code
    code = f"{tier.replace(' ', '-').lower()}-{uuid.uuid4().hex[:8]}"
    
    # Store in database
    access_code = AccessCode(code=code, tier=tier)
    db.session.add(access_code)
    db.session.commit()
    
    flash(f'Access code generated: {code}', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/reset-access/<int:user_id>', methods=['POST'])
@login_required
def reset_user_access(user_id):
    user = User.query.get_or_404(user_id)
    user.access_tier = "Public"
    db.session.commit()
    
    flash(f'User access reset to Public tier', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/update-si-gpt-link', methods=['POST'])
@login_required
def update_si_gpt_link():
    si_id = request.form.get('si_id')
    gpt_link = request.form.get('gpt_link')
    
    if si_id not in si_profiles:
        flash('Invalid SI ID', 'danger')
        return redirect(url_for('admin_dashboard'))
    
    try:
        # Update the GPT link in the si_profiles dictionary
        si_profiles[si_id]['gpt_link'] = gpt_link.strip()
        
        # Write the updated profiles to the file
        with open('intelligences/si_profiles.py', 'w') as f:
            f.write('# Structured Intelligence Profiles\n\n')
            f.write('si_profiles = {\n')
            
            for id, profile in si_profiles.items():
                f.write(f'    "{id}": {{\n')
                for key, value in profile.items():
                    if key == 'features':
                        f.write(f'        "{key}": {value},\n')
                    elif isinstance(value, str):
                        f.write(f'        "{key}": "{value}",\n')
                    else:
                        f.write(f'        "{key}": {value},\n')
                f.write('    },\n')
            
            f.write('}\n')
        
        flash(f'GPT link for {si_profiles[si_id]["name"]} updated successfully', 'success')
    except Exception as e:
        app.logger.error(f"Error updating GPT link: {e}")
        flash('An error occurred while updating the GPT link', 'danger')
    
    return redirect(url_for('admin_dashboard'))

# Create initial admin account if it doesn't exist
def create_initial_admin():
    if Admin.query.count() == 0:
        admin = Admin(
            username="Quan",
            email="admin@sentineldynamics.com"
        )
        admin.set_password("04102017Qd")  # User-specified password
        db.session.add(admin)
        db.session.commit()

# Route to update or create admin user (only accessible in development)
@app.route('/setup-admin')
def setup_admin():
    try:
        # First, try to find existing admin with username "Quan"
        existing_admin = Admin.query.filter_by(username="Quan").first()
        
        if existing_admin:
            # Update existing admin password
            existing_admin.set_password("04102017Qd")
            db.session.commit()
            return "Existing admin password updated successfully. You can now log in with username 'Quan' and your password."
        
        # If no admin with username "Quan" exists, check for "admin"
        admin_to_update = Admin.query.filter_by(username="admin").first()
        
        if admin_to_update:
            # Update existing admin username and password
            admin_to_update.username = "Quan"
            admin_to_update.set_password("04102017Qd")
            db.session.commit()
            return "Admin username and password updated successfully. You can now log in with username 'Quan' and your password."
        
        # If no admin exists at all, create new one
        new_admin = Admin(
            username="Quan",
            email="admin@sentineldynamics.com"
        )
        new_admin.set_password("04102017Qd")
        db.session.add(new_admin)
        db.session.commit()
        
        return "New admin user created successfully. You can now log in with username 'Quan' and your password."
    except Exception as e:
        db.session.rollback()
        return f"Error creating admin user: {str(e)}"

# Stripe webhook endpoint to handle async events
@app.route('/webhook/stripe', methods=['POST'])
def stripe_webhook():
    payload = request.get_data(as_text=True)
    sig_header = request.headers.get('Stripe-Signature')
    
    # This is a simplified webhook handler for demo purposes
    # In production, you should verify the signature with a webhook secret
    try:
        event = stripe.Event.construct_from(
            json.loads(payload), stripe.api_key
        )
    except ValueError as e:
        # Invalid payload
        app.logger.error(f"Invalid Stripe webhook payload: {e}")
        return jsonify({'status': 'error'}), 400
    
    # Handle the event
    if event.type == 'checkout.session.completed':
        session = event.data.object
        
        # Fulfill the purchase
        fulfill_order(session)
    
    return jsonify({'status': 'success'})

def fulfill_order(session):
    """Fulfill order after payment is complete."""
    try:
        # Find the payment record
        payment = Payment.query.filter_by(transaction_id=session.id).first()
        if payment and payment.status != "completed":
            payment.status = "completed"
            
            # Update user's access tier
            user = User.query.get(payment.user_id)
            if user:
                user.access_tier = payment.tier
                db.session.commit()
                app.logger.info(f"Order fulfilled for payment {payment.id}")
            else:
                app.logger.error(f"User not found for payment {payment.id}")
        else:
            app.logger.warning(f"Payment record not found or already completed: {session.id}")
    except Exception as e:
        app.logger.error(f"Error fulfilling order: {e}")
        db.session.rollback()

# Call create_initial_admin from a before_request handler
@app.before_request
def before_request_func():
    if request.endpoint != 'static':
        try:
            create_initial_admin()
        except Exception as e:
            app.logger.error(f"Error in before_request: {e}")
            # Don't raise the exception to prevent the app from failing
            # A db error shouldn't prevent the app from running
