import os
import csv
from flask import Flask, render_template, request, redirect, url_for, session, send_from_directory

# --- Configuration ---
# The folder where your files are stored.
SHARE_FOLDER = "files_to_share"
NEW_USER_DATABASE = "new_users.csv"
AUTH_USER_DATABASE = "authorized_users.csv"


# --- Flask App Initialization ---
app = Flask(__name__)
# This secret key is used by Flask to keep the user's session secure.
app.secret_key = "a_super_random_secret_key"
# Get the absolute path of the share folder
share_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), SHARE_FOLDER)

# --- Routes ---

# Registration Page
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"] # In a real app, HASH THIS PASSWORD!

        # Save the new user to the CSV file
        with open(NEW_USER_DATABASE, mode='a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([email, password])
        
        return redirect(url_for("login")) # Redirect to login after registering
    return render_template("register.html")

# Login Page
@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]
        
        # Check credentials against the CSV file
        with open(AUTH_USER_DATABASE, mode='r') as f:
            reader = csv.reader(f)
            for row in reader:
                if row and row[0] == email and row[1] == password:
                    session["logged_in"] = True
                    # Store user's email in session for potential future use
                    session["email"] = email 
                    return redirect(url_for("downloads"))
        
        error = "Invalid credentials. Please try again or register."
            
    return render_template("login.html", error=error)

# The main downloads page (protected)
@app.route("/")
def downloads():
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    
    try:
        files = os.listdir(share_dir)
    except FileNotFoundError:
        files = []
        
    return render_template("downloads.html", files=files)

# The route to handle file downloads (protected)
@app.route("/download/<filename>")
def download_file(filename):
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    
    return send_from_directory(share_dir, filename, as_attachment=True)

# Logout route
@app.route("/logout")
def logout():
    session.clear() # Clears all session data
    return redirect(url_for("login"))

def create_csv(filename):
    """Creates a CSV file with a header if it doesn't exist."""
    with open(filename, mode='w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["email", "password"])
    print(f"Created user database file: {filename}")

# --- Run the App with Waitress for Production ---
if __name__ == "__main__":
    # Ensure the share folder exists
    if not os.path.exists(share_dir):
        os.makedirs(share_dir)
        print(f"Created share folder at: {share_dir}")
    
    # Create the user CSV file with a header if it doesn't exist
    if not os.path.exists(AUTH_USER_DATABASE):
        create_csv(AUTH_USER_DATABASE)

    if not os.path.exists(NEW_USER_DATABASE):
        create_csv(NEW_USER_DATABASE)

    from waitress import serve
    print("Starting server with Waitress...")
    serve(app, host="0.0.0.0", port=8000)