import os
import csv
import shutil
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, abort

import config
from utils import log_event

uploads_bp = Blueprint('uploads', __name__)

@uploads_bp.route("/upload", defaults={'subpath': ''}, methods=["GET", "POST"])
@uploads_bp.route("/upload/<path:subpath>", methods=["GET", "POST"])
def upload_file(subpath):
    if not session.get("logged_in"):
        return redirect(url_for("auth.login"))
        
    upload_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)).replace("routes",""), config.UPLOAD_FOLDER)
        
    if request.method == "POST":
        if 'file' not in request.files:
            flash('No file part', 'error')
            return redirect(request.url)
        file = request.files['file']
        if file.filename == '':
            flash('No selected file', 'error')
            return redirect(request.url)
            
        upload_subpath = request.form.get('subpath', '')

        if file:
            filename = file.filename
            if '/' in filename or '\\' in filename:
                flash("Invalid filename. Subdirectories are not allowed.", "error")
                return redirect(request.url)

            file.save(os.path.join(upload_dir, filename))
            log_event(config.UPLOAD_LOG_FILE, [datetime.now().strftime("%Y-%m-%d %H:%M:%S"), session.get("email"), filename, upload_subpath])
            flash(f'File "{filename}" successfully uploaded and is pending review.', 'success')
            return redirect(url_for('files.downloads', subpath=upload_subpath))

    return render_template('upload.html', subpath=subpath)

@uploads_bp.route('/my_uploads')
def my_uploads():
    if not session.get('logged_in'):
        return redirect(url_for('auth.login'))

    upload_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)).replace("routes",""), config.UPLOAD_FOLDER)
    user_email = session.get('email')
    user_uploads = []
    
    declined_files = set()
    try:
        with open(config.DECLINED_UPLOAD_LOG_FILE, 'r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row['email'] == user_email:
                    declined_files.add(row['filename'])
    except FileNotFoundError:
        pass

    try:
        with open(config.UPLOAD_LOG_FILE, 'r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row['email'] == user_email:
                    if row['filename'] in declined_files:
                        row['status'] = 'Declined'
                    elif os.path.exists(os.path.join(upload_dir, row['filename'])):
                        row['status'] = 'Pending Review'
                    else:
                        row['status'] = 'Approved & Moved'
                    user_uploads.append(row)
    except FileNotFoundError:
        pass

    user_uploads.reverse()
    return render_template('my_uploads.html', uploads=user_uploads)

@uploads_bp.route("/admin/uploads")
def admin_uploads():
    if not session.get("is_admin"):
        abort(403)
        
    upload_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)).replace("routes",""), config.UPLOAD_FOLDER)
    uploads = []
    processed_filenames = set()
    
    try:
        with open(config.UPLOAD_LOG_FILE, mode='r', newline='', encoding='utf-8') as f:
            reader = csv.reader(f)
            header = next(reader, None)
            all_uploads = list(reader)

        for row in reversed(all_uploads):
            filename = row[2]
            if filename not in processed_filenames:
                uploads.append({"timestamp": row[0], "email": row[1], "filename": filename, "path": row[3]})
                processed_filenames.add(filename)
        
        uploads.reverse()
    except (FileNotFoundError, StopIteration):
        pass
        
    existing_uploads = [up for up in uploads if os.path.exists(os.path.join(upload_dir, up['filename']))]
    return render_template("admin_uploads.html", uploads=existing_uploads)

@uploads_bp.route("/admin/move_upload/<path:filename>", methods=["POST"])
def move_upload(filename):
    if not session.get("is_admin"):
        abort(403)
        
    upload_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)).replace("routes",""), config.UPLOAD_FOLDER)
    share_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)).replace("routes",""), config.SHARE_FOLDER)
    
    target_path_str = request.form.get("target_path")
    if not target_path_str:
        flash("Target path cannot be empty.", "error")
        return redirect(url_for("uploads.admin_uploads"))

    source_file = os.path.join(upload_dir, filename)
    destination_path = os.path.join(share_dir, target_path_str)
    
    safe_destination = os.path.abspath(destination_path)
    if not safe_destination.startswith(os.path.abspath(share_dir)):
        flash("Invalid target path.", "error")
        return redirect(url_for("uploads.admin_uploads"))

    try:
        os.makedirs(os.path.dirname(safe_destination), exist_ok=True)
        shutil.move(source_file, safe_destination)
        flash(f'File "{filename}" has been successfully moved to "{target_path_str}".', "success")
    except FileNotFoundError:
        flash(f'Error: Source file "{filename}" not found.', "error")
    except Exception as e:
        flash(f"An error occurred while moving the file: {e}", "error")

    return redirect(url_for("uploads.admin_uploads"))

@uploads_bp.route("/admin/decline_upload/<path:filename>", methods=["POST"])
def decline_upload(filename):
    if not session.get("is_admin"):
        abort(403)
        
    upload_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)).replace("routes",""), config.UPLOAD_FOLDER)
    file_to_delete = os.path.join(upload_dir, filename)
    user_email = request.form.get("email", "unknown")
    
    log_event(config.DECLINED_UPLOAD_LOG_FILE, [datetime.now().strftime("%Y-%m-%d %H:%M:%S"), user_email, filename])

    try:
        if os.path.exists(file_to_delete):
            os.remove(file_to_delete)
            flash(f'File "{filename}" has been declined and removed.', "success")
        else:
            flash(f'File "{filename}" was already removed.', "error")
    except Exception as e:
        flash(f"An error occurred while declining the file: {e}", "error")

    return redirect(url_for("uploads.admin_uploads"))
