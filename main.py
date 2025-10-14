import os
import csv
import shutil
import zipfile
import re # Import regex module
from io import BytesIO
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, session, send_from_directory, send_file, abort, flash
import config
from user import User # Import User class from user.py

# --- New Import for Excel Conversion ---
# NOTE: The 'openpyxl' library is required for this functionality.
try:
    from openpyxl.workbook import Workbook
except ImportError:
    print("Warning: openpyxl not found. Excel export will not work. Run 'pip install openpyxl'.")
    class Workbook: pass # Mock to avoid runtime error

# --- Configuration ---
SHARE_FOLDER = config.SHARE_FOLDER
TRASH_FOLDER = config.TRASH_FOLDER

NEW_USER_DATABASE = config.NEW_USER_DATABASE
AUTH_USER_DATABASE = config.AUTH_USER_DATABASE
DENIED_USER_DATABASE = config.DENIED_USER_DATABASE
SESSION_LOG_FILE = config.SESSION_LOG_FILE
DOWNLOAD_LOG_FILE = config.DOWNLOAD_LOG_FILE
SUGGESTION_LOG_FILE = config.SUGGESTION_LOG_FILE

app = Flask(__name__, static_folder='assets')
app.secret_key = config.SUPER_SECRET_KEY
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=15)
share_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), SHARE_FOLDER)
trash_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), TRASH_FOLDER)


# --- Logging Helper Function ---
def log_event(filename, data):
    """Appends a new row to a specified CSV log file."""
    with open(filename, mode='a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(data)

# --- CSV to XLSX Conversion Helper ---
def csv_to_xlsx_in_memory(csv_filepath):
    """Converts a CSV file to an XLSX file in memory (BytesIO)."""
    if 'Workbook' not in globals():
        raise RuntimeError("openpyxl library is missing.")
    wb = Workbook()
    ws = wb.active
    ws.title = os.path.basename(csv_filepath).replace('.csv', '').title()
    try:
        with open(csv_filepath, 'r', encoding='utf-8', newline='') as f:
            reader = csv.reader(f)
            for row in reader:
                ws.append(row)
    except FileNotFoundError:
        ws.append(["Error", "File Not Found"])
    memory_file = BytesIO()
    wb.save(memory_file)
    memory_file.seek(0)
    return memory_file

# --- Routes ---
@app.before_request
def before_request():
    """Reset the session timer with each request."""
    session.permanent = True

@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    email_value = ""
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]
        email_value = email

        user = User.find_by_email(email)
        login_success = False

        if user and user.check_password(password):
            session["logged_in"] = True
            session["email"] = user.email
            session["is_admin"] = user.is_admin # Store admin status in session
            login_success = True

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_event(SESSION_LOG_FILE, [timestamp, email, "LOGIN_SUCCESS" if login_success else "LOGIN_FAIL"])
        
        if login_success:
            return redirect(url_for("downloads"))
        else:
            if User.find_pending_by_email(email):
                 error = "Your account is pending administrator approval."
            elif User.find_denied_by_email(email):
                 error = "Your registration has been denied."
            else:
                 error = "Invalid credentials. Please try again or register."

    return render_template("login.html", error=error, email=email_value)

# --- Admin Routes ---
@app.route("/admin/metrics")
def admin_metrics():
    if not session.get("is_admin"): abort(403)
    log_files = [
        {"type": "session", "name": "Session Log (Login/Logout)", "description": "Track user login and failure events."},
        {"type": "download", "name": "Download Log (File/Folder/Delete)", "description": "Track all file, folder, and delete events."},
        {"type": "suggestion", "name": "Suggestion Log (User Feedback)", "description": "Records all user suggestions."},
    ]
    return render_template("admin_metrics.html", log_files=log_files)

@app.route("/admin/users")
def admin_users():
    if not session.get("is_admin"): abort(403)
    all_users = User.get_all()
    return render_template("admin_users.html", users=all_users, current_user_email=session.get('email'))

@app.route("/admin/pending")
def admin_pending():
    if not session.get("is_admin"): abort(403)
    pending_users = User.get_pending()
    return render_template("admin_pending.html", users=pending_users)

@app.route("/admin/denied")
def admin_denied():
    if not session.get("is_admin"): abort(403)
    denied_users = User.get_denied()
    return render_template("admin_denied.html", users=denied_users)

@app.route("/admin/approve/<string:email>", methods=["POST"])
def approve_user(email):
    if not session.get("is_admin"): abort(403)
    pending_users = User.get_pending()
    user_to_approve = next((user for user in pending_users if user.email == email), None)
    
    if user_to_approve:
        auth_users = User.get_all()
        auth_users.append(user_to_approve)
        User.save_all(auth_users)
        
        remaining_pending = [user for user in pending_users if user.email != email]
        User.save_pending(remaining_pending)
        flash(f"User {email} has been approved.", "success")
    else:
        flash(f"Could not find pending user {email}.", "error")
    return redirect(url_for('admin_pending'))

@app.route("/admin/deny/<string:email>", methods=["POST"])
def deny_user(email):
    if not session.get("is_admin"): abort(403)
    pending_users = User.get_pending()
    user_to_deny = next((user for user in pending_users if user.email == email), None)
    
    if user_to_deny:
        denied_users = User.get_denied()
        denied_users.append(user_to_deny)
        User.save_denied(denied_users)
        
        remaining_pending = [user for user in pending_users if user.email != email]
        User.save_pending(remaining_pending)
        flash(f"Registration for {email} has been denied.", "success")
    else:
        flash(f"Could not find pending user {email}.", "error")
    return redirect(url_for('admin_pending'))
    
@app.route("/admin/re_pend/<string:email>", methods=["POST"])
def re_pend_user(email):
    if not session.get("is_admin"): abort(403)
    denied_users = User.get_denied()
    user_to_re_pend = next((user for user in denied_users if user.email == email), None)

    if user_to_re_pend:
        pending_users = User.get_pending()
        pending_users.append(user_to_re_pend)
        User.save_pending(pending_users)
        
        remaining_denied = [user for user in denied_users if user.email != email]
        User.save_denied(remaining_denied)
        flash(f"User {email} has been moved back to pending.", "success")
    else:
        flash(f"Could not find denied user {email}.", "error")
    return redirect(url_for('admin_denied'))


@app.route("/admin/toggle_role/<string:email>", methods=["POST"])
def toggle_role(email):
    if not session.get("is_admin"): abort(403)
    if email == session.get('email'):
        flash("For security, you cannot change your own admin status.", "error")
        return redirect(url_for('admin_users'))
    users = User.get_all()
    user_found = False
    for user in users:
        if user.email == email:
            user.role = 'user' if user.is_admin else 'admin'
            user_found = True
            break
    if user_found:
        User.save_all(users)
        flash(f"Successfully updated role for {email}.", "success")
    else:
        flash(f"Could not find user {email}.", "error")
    return redirect(url_for('admin_users'))

@app.route("/metrics/download/<log_type>")
def download_metrics_xlsx(log_type):
    if not session.get("is_admin"): abort(403)
    log_map = {"session": (SESSION_LOG_FILE, "Session_Log"), "download": (DOWNLOAD_LOG_FILE, "Download_Log"), "suggestion": (SUGGESTION_LOG_FILE, "Suggestion_Log")}
    if log_type not in log_map: return abort(404)
    csv_filepath, file_prefix = log_map[log_type]
    try:
        xlsx_data = csv_to_xlsx_in_memory(csv_filepath)
        download_name = f"{file_prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        return send_file(xlsx_data, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', download_name=download_name, as_attachment=True)
    except FileNotFoundError: return abort(404)
    except Exception as e:
        print(f"Error during XLSX conversion: {e}")
        return abort(500)

# --- Standard User Routes ---
@app.route("/delete/<path:item_path>", methods=["POST"])
def delete_item(item_path):
    if not session.get("is_admin"): abort(403)
    
    source_path = os.path.join(share_dir, item_path)
    
    if not os.path.exists(source_path) or not source_path.startswith(share_dir):
        flash("File or folder not found.", "error")
        return redirect(request.referrer or url_for('downloads'))

    # Create a unique name for the item in the trash
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = os.path.basename(item_path)
    dest_name = f"{timestamp}_{base_name}"
    dest_path = os.path.join(trash_dir, dest_name)

    try:
        shutil.move(source_path, dest_path)
        flash(f"Successfully moved '{base_name}' to trash.", "success")
        
        # Log the delete event
        log_event(DOWNLOAD_LOG_FILE, [datetime.now().strftime("%Y-%m-%d %H:%M:%S"), session.get("email", "unknown"), "DELETE", item_path])

    except Exception as e:
        flash(f"Error deleting item: {e}", "error")

    # Redirect back to the folder the user was viewing
    parent_folder = os.path.dirname(item_path)
    if parent_folder:
        return redirect(url_for('downloads', subpath=parent_folder))
    return redirect(url_for('downloads'))

@app.route("/download/file/<path:file_path>")
def download_file(file_path):
    if not session.get("logged_in"): return redirect(url_for("login"))
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_event(DOWNLOAD_LOG_FILE, [timestamp, session.get("email", "unknown"), "FILE", file_path])
    directory, filename = os.path.split(file_path)
    safe_dir = os.path.join(share_dir, directory)
    if not safe_dir.startswith(share_dir) or not os.path.isdir(safe_dir): return abort(403)
    return send_from_directory(safe_dir, filename, as_attachment=True)

@app.route("/download/folder/<path:folder_path>")
def download_folder(folder_path):
    if not session.get("logged_in"): return redirect(url_for("login"))
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_event(DOWNLOAD_LOG_FILE, [timestamp, session.get("email", "unknown"), "FOLDER", folder_path])
    absolute_folder_path = os.path.join(share_dir, folder_path)
    if not os.path.isdir(absolute_folder_path) or not absolute_folder_path.startswith(share_dir): return abort(404)
    memory_file = BytesIO()
    with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(absolute_folder_path):
            for file in files:
                file_path = os.path.join(root, file)
                zf.write(file_path, os.path.relpath(file_path, absolute_folder_path))
    memory_file.seek(0)
    return send_file(memory_file, download_name=f'{os.path.basename(folder_path)}.zip', as_attachment=True)

COOLDOWN_LEVELS = [60, 300, 600, 1800, 3600]
@app.route("/suggest", methods=["POST"])
def suggest():
    if not session.get("logged_in"): return redirect(url_for("login"))
    suggestion_text = request.form.get("suggestion")
    if not suggestion_text: return redirect(url_for("downloads"))
    now = datetime.now()
    last_suggestion_time_str = session.get("last_suggestion_time")
    cooldown_index = session.get("cooldown_index", 0)
    if last_suggestion_time_str:
        last_suggestion_time = datetime.fromisoformat(last_suggestion_time_str)
        if last_suggestion_time.date() < now.date() and cooldown_index > 0:
            cooldown_index = 0
            session["cooldown_index"] = 0
        elapsed_time = (now - last_suggestion_time).total_seconds()
        current_cooldown = COOLDOWN_LEVELS[cooldown_index]
        if elapsed_time < current_cooldown:
            remaining = max(1, round((current_cooldown - elapsed_time) / 60))
            session['suggestion_error'] = f"You must wait another {remaining} minute(s) before submitting again."
            return redirect(url_for('downloads'))
    log_event(SUGGESTION_LOG_FILE, [now.strftime("%Y-%m-%d %H:%M:%S"), session.get("email", "unknown"), suggestion_text])
    session["last_suggestion_time"] = now.isoformat()
    if cooldown_index < len(COOLDOWN_LEVELS) - 1:
        session["cooldown_index"] = cooldown_index + 1
    session['suggestion_success'] = "Thank you, your suggestion has been submitted!"
    return redirect(url_for("downloads"))

def email_exists(email):
    """Checks if an email exists in auth, pending, or denied users."""
    return User.find_by_email(email) or User.find_pending_by_email(email) or User.find_denied_by_email(email)

@app.route("/register", methods=["GET", "POST"])
def register():
    error = None
    email_value = ""
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]
        email_value = email
        if email_exists(email):
            error = "This email is already registered, pending approval, or has been denied."
            return render_template("register.html", error=error, email=email_value)
        if len(password) < 8: error = "Password must be at least 8 characters long."
        elif not re.search("[a-z]", password): error = "Password must contain a lowercase letter."
        elif not re.search("[A-Z]", password): error = "Password must contain an uppercase letter."
        elif not re.search("[0-9]", password): error = "Password must contain a number."
        elif not re.search(r"[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>\/?]", password): error = "Password must contain a special character."
        if error: return render_template("register.html", error=error, email=email_value)
        
        with open(NEW_USER_DATABASE, mode='a', newline='', encoding='utf-8') as f:
            csv.writer(f).writerow([email, password, 'user'])
            
        session['login_message'] = "Registration successful! Your account is now pending administrator approval."
        return redirect(url_for("login"))
    return render_template("register.html", error=error, email=email_value)

@app.route("/logout")
def logout():
    log_event(SESSION_LOG_FILE, [datetime.now().strftime("%Y-%m-%d %H:%M:%S"), session.get("email", "unknown"), "LOGOUT"])
    session.clear()
    return redirect(url_for("login"))

@app.route('/')
@app.route('/browse/<path:subpath>')
def downloads(subpath=''):
    if not session.get("logged_in"): return redirect(url_for("login"))
    current_path = os.path.join(share_dir, subpath)
    if not current_path.startswith(share_dir): return abort(404)
    items = []
    if os.path.exists(current_path):
        for item_name in os.listdir(current_path):
            if item_name.startswith('.'): continue
            item_path = os.path.join(current_path, item_name)
            items.append({"name": item_name, "is_folder": os.path.isdir(item_path), "path": os.path.join(subpath, item_name)})
    items.sort(key=lambda x: (not x['is_folder'], x['name'].lower()))
    return render_template("downloads.html", items=items, current_path=subpath,
                           suggestion_error=session.pop('suggestion_error', None),
                           suggestion_success=session.pop('suggestion_success', None),
                           cooldown_level=session.get("cooldown_index", 0) + 1,
                           is_admin=session.get('is_admin', False))

def create_file_with_header(filename, header):
    # Ensure parent directory exists
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    if not os.path.exists(filename):
        with open(filename, mode='w', newline='', encoding='utf-8') as f:
            csv.writer(f).writerow(header)
        print(f"Created file: {filename}")

if __name__ == "__main__":
    if not os.path.exists(share_dir): os.makedirs(share_dir)
    if not os.path.exists(trash_dir): os.makedirs(trash_dir) # Create trash dir
    
    create_file_with_header(AUTH_USER_DATABASE, ["email", "password", "role"])
    create_file_with_header(NEW_USER_DATABASE, ["email", "password", "role"])
    create_file_with_header(DENIED_USER_DATABASE, ["email", "password", "role"])
    
    create_file_with_header(SESSION_LOG_FILE, ["timestamp", "email", "event"])
    create_file_with_header(DOWNLOAD_LOG_FILE, ["timestamp", "email", "type", "path"])
    create_file_with_header(SUGGESTION_LOG_FILE, ["timestamp", "email", "suggestion"])

    from waitress import serve
    print("Starting server with Waitress...")
    serve(app, host="0.0.0.0", port=8000)

