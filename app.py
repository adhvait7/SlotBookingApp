from flask import (
    Flask, render_template, request, redirect,
    session, abort, flash, send_file, jsonify
)
from pymongo import MongoClient
from werkzeug.security import generate_password_hash, check_password_hash
import os
from dotenv import load_dotenv
import random

load_dotenv()

# --------------------
# Config
# --------------------
BASE = "/projects/slot-booking"

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")

mongo_uri = os.getenv("MONGO_URI")
client = MongoClient(mongo_uri)

db = client["ClassBooking"]
users_collection = db["users"]
slot_collection = db["slots"]

# --------------------
# GLOBAL TIME SLOTS (THIS WAS MISSING)
# --------------------
slots_str = [
    "9:00 - 10:00",
    "10:00 - 11:00",
    "11:00 - 12:00",
    "12:00 - 13:00",
    "13:00 - 14:00",
    "14:00 - 15:00"
]

# --------------------
# Helpers
# --------------------
def is_logged_in(role=None):
    if "username" not in session:
        return False
    if role and session.get("role") != role:
        return False
    return True

# --------------------
# Static
# --------------------
@app.route("/favicon.ico")
def favicon():
    return send_file("favicon.png", mimetype="image/png")

# --------------------
# Error Pages
# --------------------
@app.errorhandler(403)
def forbidden(e):
    return render_template("slot_booking/403.html"), 403

@app.errorhandler(404)
def not_found(e):
    return render_template("slot_booking/404.html"), 404

# --------------------
# Portfolio
# --------------------
@app.route("/")
def portfolio():
    return render_template("portfolio.html")

# --------------------
# Slot Booking Entry
# --------------------
@app.route(BASE)
def slot_booking_home():
    return redirect(f"{BASE}/login")

# --------------------
# Auth
# --------------------
@app.route(f"{BASE}/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        user = users_collection.find_one({"username": username})
        if user and check_password_hash(user["password"], password):
            session["username"] = username
            session["role"] = user["role"]

            return redirect(
                f"{BASE}/staff-dashboard"
                if user["role"] == "staff"
                else f"{BASE}/student-dashboard"
            )
        else:
            error = "Invalid credentials"

    return render_template("slot_booking/login.html", error=error)

@app.route(f"{BASE}/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        role = request.form["role"]

        if role not in ["student", "staff"]:
            abort(403)

        if users_collection.find_one({"username": username}):
            return redirect(f"{BASE}/login")

        users_collection.insert_one({
            "username": username,
            "password": generate_password_hash(password),
            "role": role
        })

        return redirect(f"{BASE}/login")

    return render_template("slot_booking/register.html")

@app.route(f"{BASE}/logout")
def logout():
    session.clear()
    return redirect(f"{BASE}/login")


# --------------------
# Dashboards
# --------------------
@app.route(f"{BASE}/student-dashboard")
def student_dashboard():
    if not is_logged_in("student"):
        return redirect(f"{BASE}/login")

    table_data = {}
    for slot in slot_collection.find():
        table_data.setdefault(slot["day"], {})[slot["time"]] = slot["staff"]

    return render_template(
        "slot_booking/student-dashboard.html",
        username=session["username"],
        role=session["role"],
        table_data=table_data,
        slots_str=slots_str      # ✅ REQUIRED
    )

@app.route(f"{BASE}/staff-dashboard")
def staff_dashboard():
    if not is_logged_in("staff"):
        abort(403)

    table_data = {}
    for slot in slot_collection.find():
        table_data.setdefault(slot["day"], {})[slot["time"]] = slot["staff"]

    return render_template(
        "slot_booking/staff-dashboard.html",
        username=session["username"],
        role=session["role"],
        table_data=table_data,
        slots_str=slots_str      # ✅ REQUIRED
    )

# --------------------
# Slot APIs
# --------------------
@app.route(f"{BASE}/get-timeslots/<day>")
def get_timeslots(day):
    available = slot_collection.find({"day": day, "staff": None})
    return jsonify([slot["time"] for slot in available])

@app.route(f"{BASE}/book-slot", methods=["POST"])
def book_slot():
    if not is_logged_in():
        return redirect(f"{BASE}/login")

    day = request.form.get("day")
    time = request.form.get("timeDropDown")

    if not day or not time:
        return redirect(f"{BASE}/{session['role']}-dashboard")

    if session["role"] == "staff":
        slot_collection.update_one(
            {"day": day, "time": time, "staff": None},
            {"$set": {"staff": session["username"]}}
        )
        return redirect(f"{BASE}/staff-dashboard")

    slot_collection.update_one(
        {
            "day": day,
            "time": time,
            "staff": {"$ne": None},
            "students": {"$ne": session["username"]}
        },
        {"$push": {"students": session["username"]}}
    )

    return redirect(f"{BASE}/student-dashboard")

# --------------------
# Dev-only Slot Init
# --------------------
if os.getenv("ENV") == "dev":
    slot_collection.delete_many({})

    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]

    for day in days:
        for time in slots_str:
            slot_collection.update_one(
                {"day": day, "time": time},
                {"$setOnInsert": {
                    "day": day,
                    "time": time,
                    "staff": None,
                    "students": [],
                    "enrolled_count": 0
                }},
                upsert=True
            )

# --------------------
# Run
# --------------------
if __name__ == "__main__":
    app.run(debug=True)
