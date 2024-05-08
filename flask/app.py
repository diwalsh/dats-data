import os
import zipfile
import base64
import cv2
import tempfile
import json
from flask import Flask, redirect, render_template, request, session
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash

from cs50 import SQL
from helpers import apology, login_required, normalize, get_patient_images
from model import predict
from threed import load_images_from_folder, threed_render


# configure app
app = Flask(__name__, static_url_path='/static')

# configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# use CS50 built in Library to connect to database via sqlite
# (handles messy sqlachemy connection openings/closures for you)
db = SQL("sqlite:///dats.db")

# directory to save the generated renderings, etc.
UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# ensure the upload folder exists!! lol
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
    
# earthy pink colors for organs
organ_colors = [[249, 187, 191], 
                [254, 128, 162],
                [183, 82, 100]] 
    
# goodbye cache, hello css 
@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


# ROUTES !!


# index route -- landing page/home
@app.route("/")
@login_required
def index():
    return render_template("index.html")


# about me page
@app.route("/about")
def about():
    return render_template("about.html")


# upload page on get, normalized png page on post
@app.route("/upload", methods=["GET", "POST"])
@login_required
def upload():
    # User reached route via POST (as by submitting a form)
    if request.method == "POST":
        file = request.files['data_zip_file']
        file_like_object = file.stream._file  
        zipfile_ob = zipfile.ZipFile(file_like_object)
        file_names = zipfile_ob.namelist()
        # Filter names to only include the filetype that you want:
        file_names = [file_name for file_name in file_names if file_name.endswith(".png")]
        files = [] 
        for name in file_names:
            if not name.startswith("__MACOSX"):
                img_data = zipfile_ob.open(name).read()
                with tempfile.NamedTemporaryFile(delete=False) as temp_file:
                    temp_file.write(img_data)
                    temp_file_path = temp_file.name
                # the below img's need to be sent to a resizing function
                # to be fed into a model for segmentation     
                img = normalize(temp_file_path)
                # from here on, the normalized imgs are prepared for showing on screen to user
                img_data_base64 = cv2.imencode('.png', img)[1].tostring()
                img_data_base64 = base64.b64encode(img_data_base64).decode('utf-8')
                # grabbing relevant data from file name to format for user display
                parts = name.split("/")[-1].split("_")
                case_number = ''.join(filter(str.isdigit, parts[0]))
                day_number = ''.join(filter(str.isdigit, parts[1]))
                slice_number = int(parts[3])
                formatted_name = "Case {}; Day {}: Slice {}".format(case_number, day_number, slice_number)
                # Create a unique filename for the image
                user_id = str(session["user_id"])
                # pop off any prefixed folder names
                file_name = name.split("/")[-1]
                # Remove the .png suffix from the filename
                file_name = file_name.split(".png")[0]
                img_filename = "{}_{}.png".format(file_name, user_id)
                # create the normalized folder if not already there
                normalized_folder = os.path.join(app.config['UPLOAD_FOLDER'], 'normalized')
                if not os.path.exists(normalized_folder):
                    os.makedirs(normalized_folder)
                img_path = os.path.join(normalized_folder, img_filename)
                # Save the image to the normalized folder
                cv2.imwrite(img_path, img)
                # Append printable image, formatted name, and original name for display use
                files.append((img_data_base64, formatted_name, img_path))
                os.unlink(temp_file_path)  # Delete the temporary file after use
        # Sort files based on the original file name
        files = sorted(files, key=lambda x: x[2])
        session["uploaded_files"] = files
        # Retrieve image paths
        folder_path = "static/uploads/normalized"
        image_paths = get_patient_images(case_number, day_number, folder_path, user_id)
        # Store image paths in session
        session['image_paths'] = image_paths
        return render_template("pngs.html", files=files)
    else:
        return render_template("upload.html")


# model prediction route -- lands on showing overlaid images
@app.route("/model")
@login_required
def model():
    # retrieve image paths from session, declare device, checkpoint and model
    image_paths = session.get('image_paths', [])
    # predict!!
    overlay_image_paths = predict(image_paths)
    session['overlay_paths'] = overlay_image_paths
    
    # Convert images to base64
    predictions = []
    for img_path in overlay_image_paths:
        # Extract formatted name from filename
        filename = os.path.splitext(os.path.basename(img_path))[0]
        parts = filename.split("_")
        case_number = ''.join(filter(str.isdigit, parts[0]))
        day_number = ''.join(filter(str.isdigit, parts[1]))
        slice_number = int(parts[3].split(".")[0])
        formatted_name = "Case {}; Day {}: Slice {}".format(case_number, day_number, slice_number)
        
        img_name = os.path.basename(img_path)  # Extract file name (no path)
        
        predictions.append((img_path, formatted_name, img_name))
    
    # Sort the list of file names
    predictions = sorted(predictions, key=lambda x: x[2])
    
    # set folder for output and filename for export
    output_folder = 'static/uploads/objs'
    static_folder = 'uploads/objs'
    combined_filename = os.path.join(output_folder, f'case{case_number}_day{day_number}.obj') # make dynamic
    static_filename = os.path.join(static_folder, f'case{case_number}_day{day_number}.obj')
    session['obj_path'] = os.path.splitext(static_filename)[0]

    # Set the folder where your images are stored
    image_folder = 'static/uploads/masks'  # replace with the path to your image folder
    prefix = f'case{case_number}_day{day_number}' # make dynamic

    images = load_images_from_folder(image_folder, prefix)
    threed_render(images, combined_filename, organ_colors)

    return render_template("model.html", predictions=predictions, image_paths=image_paths)


# route for displaying overlaid image carousel and 3D model 
@app.route("/render")
@login_required
def render():
    # retrieve image paths from session, declare device, checkpoint and model
    image_paths = sorted(session.get('overlay_paths', []))
    obj_path = session.get('obj_path')
    user_id = session.get('user_id')
    # Calculate the middle index
    middle_index = len(image_paths) // 2
    # Access the middle image path for later use of cover image
    cover_image_path = image_paths[middle_index]
    
    parts = image_paths[0].split("/")[-1].split("_")
    case_number = ''.join(filter(str.isdigit, parts[0]))
    day_number = ''.join(filter(str.isdigit, parts[1]))
    title = "Case {}; Day {}".format(case_number, day_number)
    
    # Convert image_paths list to a JSON string
    mask_paths = json.dumps(image_paths)
    
    db.execute("INSERT INTO renderings (user_id, case_name, case_number, day_number, cover_image, mask_paths, obj_path) VALUES (?, ?, ?, ?, ?, ?, ?)",
               user_id, title, case_number, day_number, cover_image_path, mask_paths, obj_path)
    
    # Define generate_title function
    def generate_title_slice(image_path):
        parts = image_path.split("/")[-1].split("_")
        case_number = ''.join(filter(str.isdigit, parts[0]))
        day_number = ''.join(filter(str.isdigit, parts[1]))
        slice_number = int(parts[3].split(".")[0])
        formatted_name = "Case {}; Day {}: Slice {}".format(case_number, day_number, slice_number)
        return formatted_name
    
    return render_template("render2.html", image_paths=image_paths, obj_path=obj_path, title=title, generate_title_slice=generate_title_slice)


# user archive route
@app.route("/archive")
@login_required
def archive():
    user_id = session["user_id"]
    renderings = db.execute("""
        SELECT r.*
        FROM renderings r
        JOIN (
            SELECT case_name, MAX(created_at) AS max_created_at
            FROM renderings
            WHERE user_id = ?
            GROUP BY case_name
        ) m ON r.case_name = m.case_name AND r.created_at = m.max_created_at
        WHERE r.user_id = ?
        ORDER BY r.case_number ASC, r.day_number ASC
    """, user_id, user_id)

    return render_template("archive.html", renderings=renderings)


# displaying user archive in render format (overlaid image carousel and 3D model)
@app.route("/<int:rendering_id>")
@login_required
def view_render(rendering_id):
    model = db.execute("SELECT * FROM renderings WHERE id = ?", rendering_id)
    image_paths = json.loads(model[0]['mask_paths'])

    if not model:
        return apology("Model not found", 404)
    
    # Define generate_title function
    def generate_title_slice(image_path):
        parts = image_path.split("/")[-1].split("_")
        case_number = ''.join(filter(str.isdigit, parts[0]))
        day_number = ''.join(filter(str.isdigit, parts[1]))
        slice_number = int(parts[3].split(".")[0])
        formatted_name = "Case {}; Day {}: Slice {}".format(case_number, day_number, slice_number)
        return formatted_name

    return render_template("render2.html", image_paths=image_paths, obj_path=model[0]['obj_path'], title=model[0]['case_name'], generate_title_slice=generate_title_slice)


# login route
@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)
        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))
        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]
        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


# logout route
@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()
    # Redirect user to login form
    return redirect("/")


# registration route
@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must create username", 400)
        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must create password", 400)
        # Ensure password confirmation was submitted
        elif not request.form.get("confirmation"):
            return apology("must repeat password", 400)
        # Ensure passwords match!
        elif request.form.get("password") != request.form.get("confirmation"):
            return apology("passwords must match!", 400)

        # Query database for username
        exists = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username doesn't exist
        if len(exists) > 0:
            return apology("username already taken :( ", 400)

        # add user to database
        username = request.form.get("username")
        password = generate_password_hash(request.form.get("password"))
        db.execute("INSERT INTO users (username, hash) VALUES (?, ?)", username, password)

        # Remember which user has logged in
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))
        session["user_id"] = rows[0]["id"]
        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("register.html")
    
    
if __name__ == "__main__":
    app.run(debug=True)

