@admin_bp.route('/set-user-shift/<int:user_id>/<shift>')
@admin_required
def set_user_shift(user_id, shift):
    """Set shift untuk user tertentu."""
    
    valid_shifts = ['morning', 'night', 'gantung_pagi', 'gantung_malam', 'auto']
    if shift not in valid_shifts:
        flash('Invalid shift value', 'danger')
        return redirect(url_for('admin.user_shifts'))
    
    try:
        # Cek user
        user = query_db('SELECT * FROM users WHERE id = ?', [user_id], one=True)
        
        if not user:
            flash(f'User not found', 'danger')
            return redirect(url_for('admin.user_shifts'))
        
        # Update shift
        execute_db('UPDATE users SET default_shift = ? WHERE id = ?', [shift, user_id])
        
        # Verifikasi
        updated_user = query_db('SELECT default_shift FROM users WHERE id = ?', [user_id], one=True)
        
        if updated_user and updated_user['default_shift'] == shift:
            flash(f'User shift updated to {shift} successfully', 'success')
        else:
            flash(f'Update failed', 'danger')
            
    except Exception as e:
        flash(f'Error: {str(e)}', 'danger')
    
    return redirect(url_for('admin.user_shifts'))