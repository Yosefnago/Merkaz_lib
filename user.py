import csv
import config

# --- User Class ---
class User:
    def __init__(self, email, password, role='user'):
        self.email = email
        self.password = password
        self.role = role

    @property
    def is_admin(self):
        return self.role == 'admin'

    def check_password(self, password_to_check):
        return self.password == password_to_check

    # --- Methods for Authenticated Users (auth_users.csv) ---
    @staticmethod
    def find_by_email(email):
        """Finds a user by email in the authentication database."""
        users = User.get_all()
        for user in users:
            if user.email == email:
                return user
        return None

    @staticmethod
    def get_all():
        """Reads all users from the authentication database."""
        return User._read_users_from_file(config.AUTH_USER_DATABASE)

    @staticmethod
    def save_all(users):
        """Rewrites the entire auth user database."""
        User._save_users_to_file(config.AUTH_USER_DATABASE, users)
        
    # --- Methods for Pending Users (new_users.csv) ---
    @staticmethod
    def find_pending_by_email(email):
        """Finds a user by email in the pending database."""
        pending_users = User.get_pending()
        for user in pending_users:
            if user.email == email:
                return user
        return None

    @staticmethod
    def get_pending():
        """Reads all users from the pending registration database."""
        return User._read_users_from_file(config.NEW_USER_DATABASE)

    @staticmethod
    def save_pending(users):
        """Rewrites the entire pending user database."""
        User._save_users_to_file(config.NEW_USER_DATABASE, users)

    # --- Private Helper Methods ---
    @staticmethod
    def _read_users_from_file(filepath):
        """Helper to read users from a given CSV file."""
        users = []
        try:
            with open(filepath, mode='r', newline='', encoding='utf-8') as f:
                reader = csv.reader(f)
                header = next(reader, None) # Skip header
                for row in reader:
                    if row and len(row) >= 3:
                        users.append(User(email=row[0], password=row[1], role=row[2]))
        except FileNotFoundError:
            return []
        return users

    @staticmethod
    def _save_users_to_file(filepath, users):
        """Helper to write a list of users to a given CSV file."""
        with open(filepath, mode='w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(["email", "password", "role"]) # Write header
            for user in users:
                writer.writerow([user.email, user.password, user.role])

