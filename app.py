from flask import jsonify, Flask, render_template, request, redirect, session, abort, flash, send_file
from pymongo import MongoClient
from werkzeug.security import generate_password_hash, check_password_hash
import os
from datetime import datetime, timedelta, time
from dotenv import load_dotenv
import random
load_dotenv()



#db con
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

# result = slot_collection.delete_many({})
# if result.deleted_count > 0:
#     print("Success")
# else:
#     print("Nah")
result = slot_collection.delete_many({})
if result.deleted_count > 0:
    print("success clearing entire db")
days = ['Monday', 'Tuesday', 'Wednesday','Thursday','Friday']
start_time = datetime.combine(datetime.today(), time(9,0))
slots = [9,10,11,12,13,14]
slots_str = []
for h in slots:
    slots_str.append(f"{h}:00 - {h+1}:00")

slots_to_insert = []

for day in days:
    for i, slot in enumerate(slots_str):
        exist = slot_collection.find_one({"day":day, "time": slot})
        if not exist:
            
            slots_to_insert.append({
            "day":day,
            "time": slot,
            "staff": None,
            "enrolled_count": 0,
            "students":[]
        })
if slots_to_insert:
    slot_collection.insert_many(slots_to_insert)

profs = ["Prof. John", "Prof. McGonagall", "Prof. Dumbeldore", "Prof. Snape"]
unassigned_slots = slot_collection.find({"staff": None})
for slot in unassigned_slots:
    if random.choice([True, False]):
        random_prof = random.choice(profs)
        slot_collection.update_one({
            "_id": slot["_id"]
        },{"$set": {'staff':random_prof}})
    else:
        continue
print("Assigned placeholder slots")
    
@app.errorhandler(403)
def forbidden(e):
    return render_template('403.html')
@app.errorhandler(404)
def not_found(e):
    return render_template('404.html')
@app.route('/', methods=['GET','POST'])
def login():
    error = None
    if request.method == "POST":
        username = request.form['username']
        password = request.form['password']
        user = users_collection.find_one({'username':username})
        if user and check_password_hash(user['password'],password):
            session['username'] = username
            session['role'] = user['role']
        
            if user['role'] == 'staff':
                return redirect('/staff-dashboard')
            elif user['role'] == 'student':
                return redirect('/student-dashboard')
        else:
            error = "Invalid Credentials"
    return render_template("index.html", error = error)
@app.route('/register',methods=['GET','POST'])
def register():
    
    if request.method == "POST":
        username = request.form['username']
        password = request.form['password']
        role = request.form['role']
        if role not in ['student','staff']:
            return "Invalid Role", 400
        if users_collection.find_one({'username': username}):
            return redirect('/')

        hashed_password = generate_password_hash(password)

        users_collection.insert_one({
            'username': username,
            'password': hashed_password,
            'role': role
        })
        return redirect("/")
    return render_template('register.html')

@app.route('/student-dashboard')
def student_dashboard():
    if 'username' in session and session.get('role')== "student":
        table_data = {}
        for slot in slot_collection.find():
            day = slot['day']
            time = slot['time']
            staff = slot['staff']
            if day not in table_data:
                table_data[day] = {}
            table_data[day][time] = staff
        return render_template('student-dashboard.html', username = session['username'], role=session['role'], table_data = table_data, slots_str = slots_str)
    else:
        return redirect('/')

@app.route('/staff-dashboard')
def staff_dashboard():
    if 'username' in session and session.get('role')=="staff":
        table_data = {}
        for slot in slot_collection.find():
            day = slot['day']
            time = slot['time']
            staff = slot['staff']
            if day not in table_data:
                table_data[day] = {}
            table_data[day][time] = staff
        
        return render_template('staff-dashboard.html',table_data = table_data,slots_str= slots_str,username = session['username'],role=session['role'])
    else:
        return abort(403)

@app.route('/get-timeslots/<day>')
def get_timeslots(day):
    available_slots = slot_collection.find({
        "day" : day,
        "staff": None
    })
    times = []
    for entry in available_slots:
        time_value = entry['time']
        times.append(time_value)
    return jsonify(times)
    
@app.route('/book-slot', methods=['POST'])
def book_slot():
    if 'username' not in session:
        return redirect('/')
    if session['role'] == "staff":
        booking_time = request.form.get('timeDropDown')
        booking_day = request.form.get('day')

        if not booking_day or not booking_time:
            print("Invalid booking request — missing day or time.")
            return redirect('/staff-dashboard')

        booking_staff = session['username']

        result = slot_collection.update_one(
            {
                "day": booking_day,
                "time": booking_time,
                "staff": None
            },
            {
                "$set": {"staff": booking_staff}
            }
        )
        if result.modified_count > 0:
              flash("✅ Slot successfully booked!")
        else:
              flash("Error!")
        return redirect('/staff-dashboard')
    elif session['role'] == "student":
        booking_time = request.form.get('timeDropDown')
        booking_day = request.form.get('day')
        if not booking_day or not booking_time:
            print("Invalid booking request — missing day or time.")
            return redirect('/student-dashboard')

        booking_student = session['username']
        result = slot_collection.update_one(
            {
                "day": booking_day,
                "time": booking_time,
                "students": {"$ne":booking_student},
                "staff": {"$ne": None}
            },
            {
                "$push": {"students": booking_student},
                "$inc": {"enrolled_count": 1}
            }
        )
        if result.modified_count > 0:
              flash("✅ Slot successfully booked!")
        else:
            flash("⚠️ You have already enrolled or slot is unavailable.")
        return redirect('/student-dashboard')


@app.route('/admin')
def admin_panel():
    return render_template("admin-panel.html")

@app.route('/my-classes')
def my_classes():
    username = session['username']
    role = session['role']
    if username not in session['username']:
        return redirect('/')
    if role == 'student':
        classes = list(slot_collection.find({'students': username}))
        for slot in classes:
            print(slot)
    
        return render_template('my-classes.html', classes=classes, role=role)
    
@app.route('/cancel-class', methods = ['POST'])
def cancel_class():
    if 'username' not in session or session.get('role') != 'student':
        return redirect('/')
    username = session['username']
    day = request.form.get('day')
    time = request.form.get('time')

    
    result = slot_collection.update_one(
        {'day' : day,
         'time' : time,
         'students': username
         },
         {
             '$pull':{'students': username},
             '$inc': {'enrolled_count': -1}

         }
    )
    if result.modified_count > 0:
        flash("✅Successfully cancelled class.", "success")
    else:
        flash("⚠️Unable to cancel class", "warning")
    return redirect('/my-classes')

# @app.route('/create-slots', methods = ['GET', 'POST'])
# def create_slots():
#     if request.method == "POST":
#         start_time_str = request.form['start_time']
#         end_time_str = request.form['end_time']
#         start_date_str = request.form['start_date']
#         end_date_str = request.form['end_date']
#         duration_hours = float(request.form['duration'])

#         start_time = datetime.strptime(start_time_str, "%H:%M")
#         end_time = datetime.strptime(end_time_str, "%H:%M")
#         start_date = datetime.strptime(start_date_str, "%Y-%m-%d")
#         end_date = datetime.strptime(end_date_str, "%Y-%m-%d")
#         slot_duration = timedelta(hours=duration_hours)

#         current_date = start_date
#         while current_date <= end_date:
#             current_slot_start = datetime.combine(start_date, start_time.time())
#             slot_end_time = datetime.combine(current_date, end_time.time())

#             while current_slot_start + slot_duration <= slot_end_time:
#                 current_slot_end = current_slot_start + slot_duration

#                 slots_collection.insert_one({
#                     'start-time' : current_slot_start,
#                     'end-time' : current_slot_end,
#                     'status': "Available",
#                     'staff': None
#                 })

#                 current_slot_start = current_slot_end
#             current_date += timedelta(days = 1)
#         slots = list(slots_collection.find().sort('start-time',1))
#         return render_template('staff-dashboard.html', slots = slots, username = session['username'],role = session['role'])
#     return render_template('staff-dashboard.html', slots = slots, username = session['username'],role = session['role'])

# @app.route('/delete-all-slots',methods = ['GET','POST'])
# def delete_all_slots():
#     if 'username' in session and session.get('role') == 'staff':
#         slots_collection.delete_many({})
       
#         return render_template("staff-dashboard.html", username = session['username'], role = session['role'])
#     else:
#         return abort(403)
@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')
if __name__ == '__main__':
    app.run(debug=True)