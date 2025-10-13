import os
import csv
import shutil
import zipfile
from io import BytesIO
from flask import Flask, render_template, request, redirect, url_for, session, send_from_directory, send_file, abort

# --- (Configuration and App Initialization are the same) ---
SHARE_FOLDER = "files_to_share"
NEW_USER_DATABASE = "new_users.csv"
AUTH_USER_DATABASE = "authorized_users.csv"

app = Flask(__name__)
app.secret_key = "a_super_random_secret_key"
share_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), SHARE_FOLDER)

# --- (Registration, Login, and Logout routes remain the same) ---
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
                    return redirect(url_for("downloads"))
        error = "Invalid credentials. Please try again or register."
    return render_template("login.html", error=error)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# --- NEW: Dynamic Route for Browsing Files and Subfolders ---
@app.route('/')
@app.route('/browse/<path:subpath>')
def downloads(subpath=''):
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    # Security check: prevent directory traversal attacks
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

    return render_template("downloads.html", items=items, current_path=subpath)

# --- UPDATED: Download routes to handle subpaths ---
@app.route("/download/file/<path:file_path>")
def download_file(file_path):
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    # Security check is implicitly handled by send_from_directory
    directory = os.path.dirname(file_path)
    filename = os.path.basename(file_path)
    return send_from_directory(os.path.join(share_dir, directory), filename, as_attachment=True)

@app.route("/download/folder/<path:folder_path>")
def download_folder(folder_path):
    if not session.get("logged_in"):
        return redirect(url_for("login"))

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

# --- (Startup logic remains the same) ---
def create_csv(filename):
    with open(filename, mode='w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["email", "password"])
    print(f"Created user database file: {filename}")

if __name__ == "__main__":
    if not os.path.exists(share_dir):
        os.makedirs(share_dir)
    if not os.path.exists(AUTH_USER_DATABASE):
        create_csv(AUTH_USER_DATABASE)
    if not os.path.exists(NEW_USER_DATABASE):
        create_csv(NEW_USER_DATABASE)

    from waitress import serve
    print("Starting server with Waitress...")
    serve(app, host="0.0.0.0", port=8000)