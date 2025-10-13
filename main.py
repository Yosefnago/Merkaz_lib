import os
import csv
import shutil
import zipfile
from io import BytesIO
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, session, send_from_directory, send_file, abort
import config
# --- New Import for Excel Conversion ---
# NOTE: The 'openpyxl' library is required for this functionality.
try:
    from openpyxl.workbook import Workbook
except ImportError:
    print("Warning: openpyxl not found. Excel export will not work. Run 'pip install openpyxl'.")
    class Workbook: pass # Mock to avoid runtime error

# --- Configuration ---
SHARE_FOLDER = config.SHARE_FOLDER

NEW_USER_DATABASE = config.NEW_USER_DATABASE
AUTH_USER_DATABASE = config.AUTH_USER_DATABASE
SESSION_LOG_FILE = config.SESSION_LOG_FILE
DOWNLOAD_LOG_FILE = config.DOWNLOAD_LOG_FILE
SUGGESTION_LOG_FILE = config.SUGGESTION_LOG_FILE

app = Flask(__name__)
app.secret_key = config.SUPER_SECRET_KEY
# Set the session to expire after 15 minutes of inactivity
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=15)
share_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), SHARE_FOLDER)

# --- Logging Helper Function ---
def log_event(filename, data):
    """Appends a new row to a specified CSV log file."""
    with open(filename, mode='a', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(data)

# --- CSV to XLSX Conversion Helper ---
def csv_to_xlsx_in_memory(csv_filepath):
    """Converts a CSV file to an XLSX file in memory (BytesIO)."""
    if 'Workbook' not in globals():
        raise RuntimeError("openpyxl library is missing.")
        
    wb = Workbook()
    ws = wb.active
    
    # Use the filename as the worksheet title, stripping '.csv'
    ws.title = os.path.basename(csv_filepath).replace('.csv', '').title()

    try:
        with open(csv_filepath, 'r', encoding='utf-8', newline='') as f:
            reader = csv.reader(f)
            for row in reader:
                # Append each row from CSV to the worksheet
                ws.append(row)
    except FileNotFoundError:
        print(f"Error: CSV file not found at {csv_filepath}")
        # Create an empty workbook to serve as an error placeholder
        ws.append(["Error", "File Not Found"])

    # Save the workbook to an in-memory file
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
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]
        
        # Default to failed until proven successful
        login_success = False
        
        try:
            with open(AUTH_USER_DATABASE, mode='r') as f:
                reader = csv.reader(f)
                for row in reader:
                    if row and row[0] == email and row[1] == password:
                        session["logged_in"] = True
                        session["email"] = email
                        login_success = True
                        break
        except FileNotFoundError:
            # If the auth database doesn't exist, treat as failure
            pass

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_event(SESSION_LOG_FILE, [timestamp, email, "LOGIN_SUCCESS" if login_success else "LOGIN_FAIL"])
        
        if login_success:
            return redirect(url_for("downloads"))
        else:
            error = "Invalid credentials. Please try again or register."

    return render_template("login.html", error=error)

# --- NEW ROUTE: Admin Metrics Dashboard ---
@app.route("/admin/metrics")
def admin_metrics():
    if not session.get("logged_in"):
        return redirect(url_for("login"))
        
    # Define the log files available for download
    log_files = [
        {"type": "session", "name": "Session Log (Login/Logout)", "description": "Track user login and failure events."},
        {"type": "download", "name": "Download Log (File/Folder)", "description": "Track all file and folder downloads."},
        {"type": "suggestion", "name": "Suggestion Log (User Feedback)", "description": "Records all user suggestions."},
    ]
    
    return render_template("admin_metrics.html", log_files=log_files)


# --- NEW ROUTE: Download Metrics as XLSX ---
@app.route("/metrics/download/<log_type>")
def download_metrics_xlsx(log_type):
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    log_map = {
        "session": (SESSION_LOG_FILE, "Session_Log"),
        "download": (DOWNLOAD_LOG_FILE, "Download_Log"),
        "suggestion": (SUGGESTION_LOG_FILE, "Suggestion_Log")
    }

    if log_type not in log_map:
        return abort(404, "Invalid log type")

    csv_filepath, file_prefix = log_map[log_type]

    try:
        xlsx_data = csv_to_xlsx_in_memory(csv_filepath)
        download_name = f"{file_prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"

        return send_file(
            xlsx_data,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            download_name=download_name,
            as_attachment=True
        )
    except FileNotFoundError:
        return abort(404, f"Metrics file {csv_filepath} not found.")
    except Exception as e:
        # Catch the openpyxl missing error or other conversion errors
        print(f"Error during XLSX conversion for {csv_filepath}: {e}")
        return abort(500, "Error converting file to Excel format. Check server logs for details (openpyxl might be missing).")


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
    
    # Ensure safe path access
    safe_dir = os.path.join(share_dir, directory)
    if not safe_dir.startswith(share_dir) or not os.path.isdir(safe_dir):
        return abort(403) # Forbidden access

    return send_from_directory(safe_dir, filename, as_attachment=True)

@app.route("/download/folder/<path:folder_path>")
def download_folder(folder_path):
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    # --- METRICS: Log the folder download event ---
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    user_email = session.get("email", "unknown")
    log_event(DOWNLOAD_LOG_FILE, [timestamp, user_email, "FOLDER", folder_path])
    
    absolute_folder_path = os.path.join(share_dir, folder_path)
    
    # Security check: must be a directory and inside the share_dir
    if not os.path.isdir(absolute_folder_path) or not absolute_folder_path.startswith(share_dir):
        return abort(404, "Folder not found or access denied")

    memory_file = BytesIO()
    try:
        with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(absolute_folder_path):
                # Calculate the path relative to the folder being zipped
                relative_path_start = os.path.dirname(absolute_folder_path)
                for file in files:
                    file_path = os.path.join(root, file)
                    zf.write(file_path, os.path.relpath(file_path, relative_path_start))
    except Exception as e:
        print(f"Error zipping folder: {e}")
        return abort(500, "Failed to create zip file")

    memory_file.seek(0)
    return send_file(memory_file, download_name=f'{os.path.basename(folder_path)}.zip', as_attachment=True)

# --- Suggestion Cooldown Tiers (in seconds) ---
COOLDOWN_LEVELS = [60, 300, 600, 1800, 3600]

@app.route("/suggest", methods=["POST"])
def suggest():
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    suggestion_text = request.form.get("suggestion")
    if not suggestion_text:
        return redirect(url_for("downloads"))

    now = datetime.now()
    user_email = session.get("email", "unknown")

    last_suggestion_time_str = session.get("last_suggestion_time")
    cooldown_index = session.get("cooldown_index", 0)

    # --- Cooldown Reset Logic ---
    if last_suggestion_time_str:
        last_suggestion_time = datetime.fromisoformat(last_suggestion_time_str)
        # Reset cooldown if it's a new day (and user reached max cooldown before)
        if last_suggestion_time.date() < now.date() and cooldown_index > 0:
            cooldown_index = 0
            session["cooldown_index"] = cooldown_index

    # --- Cooldown Check ---
    if last_suggestion_time_str:
        last_suggestion_time = datetime.fromisoformat(last_suggestion_time_str)
        elapsed_time = (now - last_suggestion_time).total_seconds()
        
        # Check against the highest cooldown level reached (or the current one)
        current_cooldown = COOLDOWN_LEVELS[cooldown_index]

        if elapsed_time < current_cooldown:
            # User is on cooldown
            remaining = round((current_cooldown - elapsed_time) / 60)
            # Ensure remaining is at least 1 minute if still under cooldown
            remaining = max(1, remaining) 
            error_message = f"You must wait another {remaining} minute(s) before submitting again. Your current cooldown level is {cooldown_index + 1}."
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
    # else: cooldown_index remains max

    session['suggestion_success'] = "Thank you, your suggestion has been submitted!"
    return redirect(url_for("downloads"))

@app.route("/register", methods=["GET", "POST"])
def register():
    error = None
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]
        
        # Simple check for existing user (optional, but good practice)
        try:
            with open(AUTH_USER_DATABASE, mode='r') as f:
                reader = csv.reader(f)
                for row in reader:
                    if row and row[0] == email:
                        error = "This email is already registered."
                        return render_template("register.html", error=error)
        except FileNotFoundError:
            pass # Continue if file doesn't exist

        # Add to the new user database
        with open(NEW_USER_DATABASE, mode='a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([email, password])
            
        # Add immediately to the auth database for simple testing
        with open(AUTH_USER_DATABASE, mode='a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([email, password])
            
        session['login_message'] = "Registration successful! You can now log in."
        return redirect(url_for("login"))
        
    return render_template("register.html", error=error)

@app.route("/logout")
def logout():
    email = session.get("email", "unknown")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_event(SESSION_LOG_FILE, [timestamp, email, "LOGOUT"])
    session.clear()
    return redirect(url_for("login"))

@app.route('/')
@app.route('/browse/<path:subpath>')
def downloads(subpath=''):
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    
    suggestion_error = session.pop('suggestion_error', None)
    suggestion_success = session.pop('suggestion_success', None)
    cooldown_index = session.get("cooldown_index", 0)

    current_path = os.path.join(share_dir, subpath)
    
    # Security check: ensure path is within the designated share directory
    if not os.path.exists(current_path) or not current_path.startswith(share_dir):
        # Log this attempt if desired, but abort for security
        return abort(404, "Path not found or outside permitted boundaries.")
        
    items = []
    try:
        for item_name in os.listdir(current_path):
            # Skip hidden files
            if item_name.startswith('.'):
                continue
                
            item_path = os.path.join(current_path, item_name)
            is_folder = os.path.isdir(item_path)
            items.append({"name": item_name, "is_folder": is_folder, "path": os.path.join(subpath, item_name)})
    except FileNotFoundError:
        pass

    # Sort items to show folders first, then files, all alphabetically
    items.sort(key=lambda x: (not x['is_folder'], x['name'].lower()))

    # Calculate back path for navigation
    back_path = ''
    if subpath:
        # Split path, remove the last segment, and rejoin
        path_parts = subpath.split('/')
        if len(path_parts) > 1:
            back_path = '/'.join(path_parts[:-1])

    return render_template(
        "downloads.html", 
        items=items, 
        current_path=subpath,
        back_path=back_path,
        suggestion_error=suggestion_error,
        suggestion_success=suggestion_success,
        cooldown_level=cooldown_index + 1
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
    # Ensure share directory exists
    if not os.path.exists(share_dir):
        os.makedirs(share_dir)
        
    # Ensure a dummy file exists for testing the browse view
    dummy_file_path = os.path.join(share_dir, "Example_Document.txt")
    if not os.path.exists(dummy_file_path):
        with open(dummy_file_path, 'w') as f:
            f.write("This is a test file for download.")
            
    # Create user databases if they don't exist
    create_file_with_header(AUTH_USER_DATABASE, ["email", "password"])
    create_file_with_header(NEW_USER_DATABASE, ["email", "password"])
    
    # Create log files if they don't exist
    create_file_with_header(SESSION_LOG_FILE, ["timestamp", "email", "event"])
    create_file_with_header(DOWNLOAD_LOG_FILE, ["timestamp", "email", "type", "path"])
    create_file_with_header(SUGGESTION_LOG_FILE, ["timestamp", "email", "suggestion"])

    from waitress import serve
    print("Starting server with Waitress...")
    # NOTE: To test the Excel functionality, you must run 'pip install openpyxl' 
    # in your environment alongside 'flask' and 'waitress'.
    serve(app, host="0.0.0.0", port=8000)
