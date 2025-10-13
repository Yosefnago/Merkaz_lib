import os
import csv
import shutil # Used for creating zip archives
import zipfile
from io import BytesIO # Used to create the zip in memory
from flask import Flask, render_template, request, redirect, url_for, session, send_from_directory, send_file

# --- (Configuration and App Initialization remain the same) ---
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


# --- (Updated Downloads and New Folder Download Routes) ---

@app.route("/")
def downloads():
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    
    items = []
    try:
        # List all items in the share directory
        for item_name in os.listdir(share_dir):
            item_path = os.path.join(share_dir, item_name)
            # Check if it's a directory or a file
            is_folder = os.path.isdir(item_path)
            items.append({"name": item_name, "is_folder": is_folder})
    except FileNotFoundError:
        pass # If the share folder doesn't exist, items will be empty
        
    return render_template("downloads.html", items=items)

# Route for downloading individual files
@app.route("/download/file/<filename>")
def download_file(filename):
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    return send_from_directory(share_dir, filename, as_attachment=True)

# NEW ROUTE for downloading folders as zip files
@app.route("/download/folder/<path:folder_name>")
def download_folder(folder_name):
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    folder_path = os.path.join(share_dir, folder_name)

    # Security check: ensure the path is within the share directory
    if not os.path.isdir(folder_path) or not folder_path.startswith(share_dir):
        return "Folder not found", 404

    # Create a zip file in memory
    memory_file = BytesIO()
    with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(folder_path):
            for file in files:
                file_path = os.path.join(root, file)
                # Add file to zip, creating a relative path inside the zip
                zf.write(file_path, os.path.relpath(file_path, share_dir))

    memory_file.seek(0)
    
    return send_file(memory_file,
                     download_name=f'{folder_name}.zip',
                     as_attachment=True)

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