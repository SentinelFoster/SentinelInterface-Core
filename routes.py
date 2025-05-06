import uuid
from flask import render_template, redirect, url_for, request, flash, session, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from app import app, db
from models import Admin, User, Interaction, AccessCode, Payment
from intelligences.si_profiles import si_profiles

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

# Simulate payment (in a real app, this would integrate with Stripe)
@app.route('/process-payment', methods=['POST'])
def process_payment():
    tier = request.form.get('tier', '')
    user = get_current_user()
    
    if not user:
        flash('Session error. Please try again.', 'danger')
        return redirect(url_for('tiers'))
    
    # Tier pricing
    tier_prices = {
        "Dormant Observer": 10.0,
        "Sentinel Core": 25.0,
        "Guardian Elite": 60.0
    }
    
    if tier not in tier_prices:
        flash('Invalid tier selected', 'danger')
        return redirect(url_for('tiers'))
    
    try:
        # Create a payment record
        payment = Payment(
            user_id=user.id,
            tier=tier,
            amount=tier_prices[tier],
            transaction_id=f"SIMULATED-{uuid.uuid4()}",
            status="completed"
        )
        
        # Update user's access tier
        user.access_tier = tier
        
        db.session.add(payment)
        db.session.commit()
        
        flash(f'Payment processed successfully! Your account has been upgraded to {tier}.', 'success')
    except Exception as e:
        app.logger.error(f"Error processing payment: {e}")
        db.session.rollback()
        flash('An error occurred while processing your payment. Please try again.', 'danger')
    
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

# Create initial admin account if it doesn't exist
def create_initial_admin():
    if Admin.query.count() == 0:
        admin = Admin(
            username="admin",
            email="admin@sentineldynamics.com"
        )
        admin.set_password("sentinel123")  # In production, use a secure password
        db.session.add(admin)
        db.session.commit()

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
