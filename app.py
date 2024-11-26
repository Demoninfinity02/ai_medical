
import os
import sqlite3
from flask import Flask, flash, redirect, render_template, request, session, jsonify
from werkzeug.security import check_password_hash, generate_password_hash
import google.generativeai as genai
from helpers import apology, login_required

genai.configure(api_key=os.environ["GENAI_API_KEY"])

app = Flask(__name__)
app.secret_key = os.urandom(24)
app.config['SESSION_PERMANENT'] = False

# Initialize and configure the database connection
db = sqlite3.connect('nameofdb.db', check_same_thread=False)
cursor = db.cursor()

# Create user_diagnosis table to store user credentials and details
cursor.execute('''
    CREATE TABLE IF NOT EXISTS user_diagnosis (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL UNIQUE,
        password TEXT NOT NULL,
        name TEXT DEFAULT NULL,
        age INTEGER DEFAULT NULL,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
''')

# Create diagnosis_history table for storing diagnosis entries, linked to user_id
cursor.execute('''
    CREATE TABLE IF NOT EXISTS diagnosis_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        name TEXT,
        age INTEGER,
        symptoms TEXT NOT NULL,
        diagnosis TEXT NOT NULL,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES user_diagnosis(id)
    )
''')
db.commit()

# Homepage route
@app.route("/")
def index():
    return render_template("homepage.html")

@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# User registration route
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        # Check if username already exists
        cursor.execute("SELECT * FROM user_diagnosis WHERE user_id = ?", (request.form.get("username"),))
        rows = cursor.fetchall()
        if rows:
            return apology('Username Taken', 400)

        # Validate username and password input
        if not request.form.get('username') or not request.form.get('password'):
            return apology('Must provide Username and Password', 400)

        # Hash password and insert new user into database
        hashed_password = generate_password_hash(request.form.get('password'))
        cursor.execute(
            'INSERT INTO user_diagnosis (user_id, password) VALUES (?, ?)', 
            (request.form.get('username'), hashed_password)
        )
        db.commit()
        return redirect('/login')
    else:
        return render_template("registration.html")

# User login route
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if not request.form.get("username") or not request.form.get("password"):
            return apology("must provide username and password", 403)

        cursor.execute("SELECT * FROM user_diagnosis WHERE user_id = ?", (request.form.get("username"),))
        rows = cursor.fetchall()

        # Validate user credentials
        if len(rows) != 1 or not check_password_hash(rows[0][2], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Store user info in session
        session["user_id"] = rows[0][0]
        session['username'] = rows[0][1]
        return redirect("/")
    else:
        return render_template("login.html")

# Diagnosis route with chatbot
@app.route('/chat', methods=["GET", "POST"])
@login_required
def chat():
    if request.method == "POST":
        try:
            # Validate form inputs
            if not request.form.get("name") or not request.form.get("age") or not request.form.get("symptoms"):
                return apology("must provide name, age, and symptoms", 403)

            # Generate diagnosis response
            model = genai.GenerativeModel("gemini-1.5-flash")
            symptoms = request.form.get("symptoms")
            chat = model.start_chat(
                history=[
                    {"role": "user", "parts": ["I need your help"]},
                    {"role": "model", "parts": ["What help do you need?"]}
                ]
            )

            response = chat.send_message(f"Analyze the symptoms: {symptoms}", stream=True)
            diagnosis_text = "".join(chunk.text for chunk in response)

            # Save diagnosis entry to diagnosis_history table
            cursor.execute(
                """
                INSERT INTO diagnosis_history (user_id, name, age, symptoms, diagnosis)
                VALUES (?, ?, ?, ?, ?)
                """,
                (session.get("user_id"), request.form.get("name"), request.form.get("age"), symptoms, diagnosis_text)
            )
            db.commit()
            return render_template("result.html", symp=diagnosis_text)

        except sqlite3.Error as e:
            print("Database error:", e)
            return apology("Database error. Please try again later.", 500)
        except Exception as e:
            print("Error:", e)
            return apology("An error occurred. Please try again.", 500)
    else:
        return render_template("chatbox.html")
    

@app.route("/history")
@login_required
def history():
    """Fetch and display all recorded symptoms and diagnoses for the logged-in user."""
    try:
        # Query the database for all records belonging to the current user
        cursor.execute(
            "SELECT name, age, symptoms, diagnosis, timestamp FROM diagnosis_history WHERE user_id = ? ORDER BY timestamp DESC",
            (session["user_id"],)
        )
        records = cursor.fetchall()

        # Render the records on the history page
        return render_template("history.html", records=records)

    except sqlite3.Error as e:
        print("Database error:", e)
        return apology("Database error. Please try again later.", 500)
    
@app.route("/aboutus")
def aboutus():
    return render_template("aboutus.html")

# User logout route
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")
