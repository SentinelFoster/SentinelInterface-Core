# Updated generate_access_code function inserted by Commander Sentinel

@app.route('/admin/generate-code', methods=['POST'])
@login_required
def generate_access_code():
    tier = request.form.get('tier', '')
    si_id = request.form.get('si_id', '')  # new: SI ID selected by admin
    user_name = request.form.get('user_name', '').strip().title()  # new: user input

    # Validate tier
    valid_tiers = ["Dormant Observer", "Sentinel Core", "Guardian Elite"]
    if tier not in valid_tiers or not user_name or si_id not in si_profiles:
        flash('Invalid tier, SI, or user name provided.', 'danger')
        return redirect(url_for('admin_dashboard'))

    si_name = si_profiles[si_id]["name"].replace(" ", "")
    unique_number = str(uuid.uuid4().int)[-4:]

    # Format the code: SIName-UserName-1234-TIER
    code = f"{si_name}-{user_name}-{unique_number}-{tier.replace(' ', '').upper()}"

    # Store in database
    access_code = AccessCode(code=code, tier=tier)
    db.session.add(access_code)
    db.session.commit()

    flash(f'Access code generated: {code}', 'success')
    return redirect(url_for('admin_dashboard'))

