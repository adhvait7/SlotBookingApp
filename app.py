from flask import jsonify, Flask, render_template, request, redirect, session, abort, flash, send_file
from pymongo import MongoClient
from werkzeug.security import generate_password_hash, check_password_hash
import os
from datetime import datetime, timedelta, time
from dotenv import load_dotenv
import random

load_dotenv()

# DB connection
mongo_uri = os.getenv("MONGO_URI")
client = MongoClient(mongo_uri)

db = client['ClassBooking']
users_collection = db['users']
slot_collection = db['slots']

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")

@app.route('/favicon.ico')
def favicon():
    return send_file('favicon.png', mimetype='image/png')

# Clear existing slots and initialize
result = slot_collection.delete_many({})
if result.deleted_count > 0:
    print("success clearing entire db")

days = ['Monday', 'Tuesday', 'Wednesday','Thursday','Friday']
slots = [9,10,11,12,13,14]
slots_str = [f"{h}:00 - {h+1}:00" for h in slots]
slots_to_insert = []

for day in days:
    for slot in slots_str:
        exist = slot_collection.find_one({"day": day, "time": slot})
        if not exist:
            slots_to_insert.append({
                "day": day,
                "time": slot,
                "staff": None,
                "enrolled_count": 0,
                "students": []
            })
if slots_to_insert:
    slot_collection.insert_many(slots_to_insert)

# Assign placeholder staff to some slots
profs = ["Prof. John", "Prof. McGonagall", "Prof. Dumbeldore", "Prof. Snape"]
unassigned_slots = slot_collection.find({"staff": None})
for slot in unassigned_slots:
    if random.choice([True, False]):
        random_prof = random.choice(profs)
        slot_collection.update_one({"_id": slot["_id"]}, {"$set": {"staff": random_prof}})
print("Assigned placeholder slots")

@app.errorhandler(403)
def forbidden(e):
    return render_template('403.html')

@app.errorhandler(404)
def not_found(e):
    return render_template('404.html')

@app.route('/')
def home():
    return render_template("index.html")  # New portfolio homepage

@app.route('/login', methods=['GET','POST'])
def login():
    error = None
    if request.method == "POST":
        username = request.form['username']
        password = request.form['password']
        user = users_collection.find_one({'username': username})
        if user and check_password_hash(user['password'], password):
            session['username'] = username
            session['role'] = user['role']
            if user['role'] == 'staff':
                return redirect('/staff-dashboard')
            elif user['role'] == 'student':
                return redirect('/student-dashboard')
        else:
            error = "Invalid Credentials"
    return render_template("login.html", error=error)

@app.route('/register', methods=['GET','POST'])
def register():
    if request.method == "POST":
        username = request.form['username']
        password = request.form['password']
        role = request.form['role']
        if role not in ['student','staff']:
            return "Invalid Role", 400
        if users_collection.find_one({'username': username}):
            return redirect('/login')
        hashed_password = generate_password_hash(password)
        users_collection.insert_one({
            'username': username,
            'password': hashed_password,
            'role': role
        })
        return redirect('/login')
    return render_template('register.html')

@app.route('/student-dashboard')
def student_dashboard():
    if 'username' in session and session.get('role') == "student":
        table_data = {}
        for slot in slot_collection.find():
            day = slot['day']
            time = slot['time']
            staff = slot['staff']
            if day not in table_data:
                table_data[day] = {}
            table_data[day][time] = staff
        return render_template('student-dashboard.html', username=session['username'], role=session['role'], table_data=table_data, slots_str=slots_str)
    else:
        return redirect('/login')

@app.route('/staff-dashboard')
def staff_dashboard():
    if 'username' in session and session.get('role') == "staff":
        table_data = {}
        for slot in slot_collection.find():
            day = slot['day']
            time = slot['time']
            staff = slot['staff']
            if day not in table_data:
                table_data[day] = {}
            table_data[day][time] = staff
        return render_template('staff-dashboard.html', table_data=table_data, slots_str=slots_str, username=session['username'], role=session['role'])
    else:
        return abort(403)

@app.route('/get-timeslots/<day>')
def get_timeslots(day):
    available_slots = slot_collection.find({"day": day, "staff": None})
    times = [entry['time'] for entry in available_slots]
    return jsonify(times)

@app.route('/book-slot', methods=['POST'])
def book_slot():
    if 'username' not in session:
        return redirect('/login')
    booking_time = request.form.get('timeDropDown')
    booking_day = request.form.get('day')
    if not booking_day or not booking_time:
        return redirect('/staff-dashboard' if session['role'] == 'staff' else '/student-dashboard')

    if session['role'] == "staff":
        booking_staff = session['username']
        result = slot_collection.update_one({"day": booking_day, "time": booking_time, "staff": None}, {"$set": {"staff": booking_staff}})
        flash("✅ Slot successfully booked!" if result.modified_count > 0 else "Error!")
        return redirect('/staff-dashboard')
    elif session['role'] == "student":
        booking_student = session['username']
        result = slot_collection.update_one({"day": booking_day, "time": booking_time, "students": {"$ne": booking_student}, "staff": {"$ne": None}}, {"$push": {"students": booking_student}, "$inc": {"enrolled_count": 1}})
        flash("✅ Slot successfully booked!" if result.modified_count > 0 else "⚠️ You have already enrolled or slot is unavailable.")
        return redirect('/student-dashboard')

@app.route('/admin')
def admin_panel():
    return render_template("admin-panel.html")

@app.route('/my-classes')
def my_classes():
    if 'username' not in session or session.get('role') not in ['student', 'staff']:
        return redirect('/login')
    username = session['username']
    role = session['role']
    classes = list(slot_collection.find({'students': username})) if role == 'student' else []
    return render_template('my-classes.html', classes=classes, role=role)

@app.route('/edit-profile')
def edit_profile():
    if 'username' not in session or session.get('role') != 'student':
        return redirect('/login')
    return render_template('edit-profile.html', username=session['username'])

@app.route('/cancel-class', methods=['POST'])
def cancel_class():
    if 'username' not in session or session.get('role') != 'student':
        return redirect('/login')
    username = session['username']
    day = request.form.get('day')
    time = request.form.get('time')
    result = slot_collection.update_one({'day': day, 'time': time, 'students': username}, {'$pull': {'students': username}, '$inc': {'enrolled_count': -1}})
    flash("✅Successfully cancelled class." if result.modified_count > 0 else "⚠️Unable to cancel class")
    return redirect('/my-classes')

@app.route('/delete-account')
def delete_account():
    if 'username' not in session:
        return redirect('/login')
    username = session['username']
    result = users_collection.delete_one({'username': username})
    flash("Account deleted successfully." if result.deleted_count > 0 else "Error deleting account.")
    session.clear()
    return redirect('/')

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

if __name__ == '__main__':
    app.run(debug=True)
