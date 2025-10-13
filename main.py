import os
import csv
import shutil
import zipfile
from io import BytesIO
from datetime import datetime, timedelta # Import timedelta
from flask import Flask, render_template, request, redirect, url_for, session, send_from_directory, send_file, abort

# --- Configuration ---
SHARE_FOLDER = "files_to_share"
NEW_USER_DATABASE = "new_users.csv"
AUTH_USER_DATABASE = "authorized_users.csv"
SESSION_LOG_FILE = "session_logs.csv"
DOWNLOAD_LOG_FILE = "download_logs.csv"
SUGGESTION_LOG_FILE = "suggestions.log"

app = Flask(__name__)
app.secret_key = "a_super_random_secret_key"
# Set the session to expire after 15 minutes of inactivity
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=15)
share_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), SHARE_FOLDER)

# --- Logging Helper Function ---
def log_event(filename, data):
    """Appends a new row to a specified CSV log file."""
    with open(filename, mode='a', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(data)

# --- Routes ---
@app.before_request
def before_request():
    """Reset the session timer with each request."""
    session.permanent = True

@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]
        with open(AUTH_USER_DATABASE, mode='r') as f:
            reader = csv.reader(f)
            for row in reader:
                if row and row[0] == email and row[1] == password:
                    session["logged_in"] = True
                    session["email"] = email
                    
                    # --- METRICS: Log the login event ---
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    log_event(SESSION_LOG_FILE, [timestamp, email, "LOGIN_SUCCESS"])
                    
                    return redirect(url_for("downloads"))
        
        # --- METRICS: Log the failed login attempt ---
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_event(SESSION_LOG_FILE, [timestamp, email, "LOGIN_FAIL"])
        error = "Invalid credentials. Please try again or register."

    return render_template("login.html", error=error)

@app.route("/download/file/<path:file_path>")
def download_file(file_path):
    if not session.get("logged_in"):
        return redirect(url_for("login"))
        
    # --- METRICS: Log the file download event ---
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    user_email = session.get("email", "unknown")
    log_event(DOWNLOAD_LOG_FILE, [timestamp, user_email, "FILE", file_path])
    
    directory = os.path.dirname(file_path)
    filename = os.path.basename(file_path)
    return send_from_directory(os.path.join(share_dir, directory), filename, as_attachment=True)

@app.route("/download/folder/<path:folder_path>")
def download_folder(folder_path):
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    # --- METRICS: Log the folder download event ---
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    user_email = session.get("email", "unknown")
    log_event(DOWNLOAD_LOG_FILE, [timestamp, user_email, "FOLDER", folder_path])
    
    absolute_folder_path = os.path.join(share_dir, folder_path)
    if not os.path.isdir(absolute_folder_path) or not absolute_folder_path.startswith(share_dir):
        return abort(404, "Folder not found")

    memory_file = BytesIO()
    with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(absolute_folder_path):
            for file in files:
                file_path = os.path.join(root, file)
                zf.write(file_path, os.path.relpath(file_path, os.path.dirname(absolute_folder_path)))
    
    memory_file.seek(0)
    return send_file(memory_file, download_name=f'{os.path.basename(folder_path)}.zip', as_attachment=True)

# --- Suggestion Cooldown Tiers (in seconds) ---
# 1 min, 5 min, 10 min, 30 min, 1 hour
COOLDOWN_LEVELS = [60, 300, 600, 1800, 3600]

@app.route("/suggest", methods=["POST"])
def suggest():
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    suggestion_text = request.form.get("suggestion")
    if not suggestion_text:
        # Although the textarea is required, handle cases where it might be empty
        return redirect(url_for("downloads"))

    now = datetime.now()
    user_email = session.get("email", "unknown")

    last_suggestion_time_str = session.get("last_suggestion_time")
    cooldown_index = session.get("cooldown_index", 0)

    # --- Cooldown Reset Logic ---
    if last_suggestion_time_str:
        last_suggestion_time = datetime.fromisoformat(last_suggestion_time_str)
        # Reset cooldown if it's a new day and the user is at the max cooldown level
        if last_suggestion_time.date() < now.date() and cooldown_index == len(COOLDOWN_LEVELS) - 1:
            cooldown_index = 0
            session["cooldown_index"] = cooldown_index

    # --- Cooldown Check ---
    if last_suggestion_time_str:
        last_suggestion_time = datetime.fromisoformat(last_suggestion_time_str)
        elapsed_time = (now - last_suggestion_time).total_seconds()
        current_cooldown = COOLDOWN_LEVELS[cooldown_index]

        if elapsed_time < current_cooldown:
            # User is on cooldown, redirect back with an error message
            remaining = round((current_cooldown - elapsed_time) / 60)
            error_message = f"You must wait another {remaining} minute(s) before submitting again."
            session['suggestion_error'] = error_message
            return redirect(url_for('downloads'))

    # --- Log the Suggestion ---
    timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
    log_event(SUGGESTION_LOG_FILE, [timestamp, user_email, suggestion_text])

    # --- Update Session for Next Cooldown ---
    session["last_suggestion_time"] = now.isoformat()
    # Move to the next cooldown level, but don't go past the end of the list
    if cooldown_index < len(COOLDOWN_LEVELS) - 1:
        session["cooldown_index"] = cooldown_index + 1

    session['suggestion_success'] = "Thank you, your suggestion has been submitted!"
    return redirect(url_for("downloads"))

# --- (Other routes: register, logout, downloads remain the same) ---
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]
        with open(NEW_USER_DATABASE, mode='a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([email, password])
        return redirect(url_for("login"))
    return render_template("register.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route('/')
@app.route('/browse/<path:subpath>')
def downloads(subpath=''):
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    
    suggestion_error = session.pop('suggestion_error', None)
    suggestion_success = session.pop('suggestion_success', None)

    current_path = os.path.join(share_dir, subpath)
    if not os.path.exists(current_path) or not current_path.startswith(share_dir):
        return abort(404, "Path not found")
        
    items = []
    try:
        for item_name in os.listdir(current_path):
            item_path = os.path.join(current_path, item_name)
            is_folder = os.path.isdir(item_path)
            items.append({"name": item_name, "is_folder": is_folder, "path": os.path.join(subpath, item_name)})
    except FileNotFoundError:
        pass

    # NEW: Sort items to show folders first, then files, all alphabetically
    items.sort(key=lambda x: (not x['is_folder'], x['name'].lower()))

    return render_template(
        "downloads.html", 
        items=items, 
        current_path=subpath,
        suggestion_error=suggestion_error,
        suggestion_success=suggestion_success
    )


# --- Startup Logic (Updated to create log files) ---
def create_file_with_header(filename, header):
    """Creates a CSV file with a header if it doesn't exist."""
    if not os.path.exists(filename):
        with open(filename, mode='w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(header)
        print(f"Created log file: {filename}")

if __name__ == "__main__":
    if not os.path.exists(share_dir):
        os.makedirs(share_dir)
    
    # Create user databases if they don't exist
    create_file_with_header(AUTH_USER_DATABASE, ["email", "password"])
    create_file_with_header(NEW_USER_DATABASE, ["email", "password"])
    
    # Create log files if they don't exist
    create_file_with_header(SESSION_LOG_FILE, ["timestamp", "email", "event"])
    create_file_with_header(DOWNLOAD_LOG_FILE, ["timestamp", "email", "type", "path"])
    create_file_with_header(SUGGESTION_LOG_FILE, ["timestamp", "email", "suggestion"])

    from waitress import serve
    print("Starting server with Waitress...")
    serve(app, host="0.0.0.0", port=8000)