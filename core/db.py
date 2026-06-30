
from . import utils
import json

def load_exam_questions(con, exam_id, teacher):
    qs = con.execute(
        "SELECT * FROM exam_questions WHERE exam_id=? AND teacher_username=?",
        (exam_id, teacher)
    ).fetchall()
    result = []
    for q in qs:
        opts = con.execute(
            "SELECT * FROM exam_options WHERE question_id=? ORDER BY label", (q['id'],)
        ).fetchall()
        result.append({
            'text': q['question_text'],
            'type': q['question_type'],
            'points': q['points'],
            'timer_secs': q['timer_secs'] if 'timer_secs' in q.keys() else 0,
            'options': [{'label': o['label'], 'text': o['text'], 'correct': bool(o['is_correct'])} for o in opts],
        })
    return result

# ─────────────────────────────────────────────────────────────────────────────


def connect_to_database(name='database.db'):
    import sqlite3
    con = sqlite3.connect(name, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def init_db(connection):
    cursor = connection.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            username TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL,
            stu_id INTEGER NOT NULL UNIQUE,
            email TEXT NOT NULL UNIQUE,
            contact TEXT NOT NULL,

            level TEXT NOT NULL,
            department TEXT NOT NULL,

            profile_image TEXT,
            voice_intro TEXT,
            voice_embedding TEXT,    -- JSON string of embedding
            face_encoding TEXT,      -- JSON string of 128 float values
            session_token TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS doctors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL,
            phone TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            session_token TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    ''')

    cursor.executescript("""
    CREATE TABLE IF NOT EXISTS exams (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        teacher_username TEXT    NOT NULL,
        title            TEXT    NOT NULL,
        course_code      TEXT,
        department       TEXT,
        level            INTEGER DEFAULT 1,
        start_datetime   TEXT,
        duration_mins    INTEGER DEFAULT 90,
        total_marks      INTEGER DEFAULT 100,
        passing_score    INTEGER DEFAULT 60,
        instructions     TEXT,
        warning_message  TEXT,
        status           TEXT    DEFAULT 'draft',
        proc_webcam      INTEGER DEFAULT 1,
        proc_face        INTEGER DEFAULT 1,
        proc_gaze        INTEGER DEFAULT 1,
        proc_audio       INTEGER DEFAULT 1,
        proc_tab         INTEGER DEFAULT 1,
        proc_phone       INTEGER DEFAULT 1,
        proc_multiface   INTEGER DEFAULT 1,
        locking_mode     INTEGER DEFAULT 0,
        created_at       DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS forbidden_objects (
        id       INTEGER PRIMARY KEY AUTOINCREMENT,
        exam_id  INTEGER NOT NULL REFERENCES exams(id) ON DELETE CASCADE,
        name     TEXT    NOT NULL,
        allowed  INTEGER DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS exam_questions (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        exam_id          INTEGER NOT NULL REFERENCES exams(id) ON DELETE CASCADE,
        teacher_username TEXT    NOT NULL,
        question_text    TEXT    NOT NULL,
        question_type    TEXT    DEFAULT 'mcq',
        points           INTEGER DEFAULT 2,
        timer_secs       INTEGER DEFAULT 0,
        created_at       DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS exam_options (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        question_id INTEGER NOT NULL REFERENCES exam_questions(id) ON DELETE CASCADE,
        label       TEXT    NOT NULL,
        text        TEXT    NOT NULL,
        is_correct  INTEGER DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS student_exams (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        student_username TEXT    NOT NULL,
        exam_id          INTEGER NOT NULL REFERENCES exams(id),
        started_at       DATETIME DEFAULT CURRENT_TIMESTAMP,
        submitted_at     DATETIME,
        score            INTEGER,
        passed           INTEGER DEFAULT 0,
        UNIQUE(student_username, exam_id)
    );
    CREATE TABLE IF NOT EXISTS student_answers (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        student_exam_id INTEGER NOT NULL REFERENCES student_exams(id) ON DELETE CASCADE,
        question_id     INTEGER NOT NULL REFERENCES exam_questions(id),
        option_id       INTEGER REFERENCES exam_options(id),
        answer_text     TEXT,
        is_correct      INTEGER DEFAULT 0
    );
    """)

    # Migrations for existing databases that predate these columns
    exam_cols = {row[1] for row in cursor.execute("PRAGMA table_info(exams)")}
    if 'locking_mode' not in exam_cols:
        cursor.execute("ALTER TABLE exams ADD COLUMN locking_mode INTEGER DEFAULT 0")

    q_cols = {row[1] for row in cursor.execute("PRAGMA table_info(exam_questions)")}
    if 'timer_secs' not in q_cols:
        cursor.execute("ALTER TABLE exam_questions ADD COLUMN timer_secs INTEGER DEFAULT 0")

    connection.commit()


def add_doctor(connection, username,password, phone ,email):
    cursor = connection.cursor()
    hashed_password = utils.hash_password(password)
    cursor.execute('''
        INSERT INTO doctors (username, password, phone, email)
        VALUES (?, ?, ?, ?)
    ''', (username, hashed_password, phone,email))

    connection.commit()
    return cursor.lastrowid

# def init_db(connection):
#     cursor = connection.cursor()
#
#     cursor.execute('''
#         CREATE TABLE IF NOT EXISTS students (
#             id INTEGER PRIMARY KEY AUTOINCREMENT,
#
#             username TEXT NOT NULL UNIQUE,
#             password TEXT NOT NULL,
#             stu_id INTEGER NOT NULL UNIQUE,
#             email TEXT NOT NULL UNIQUE,
#             contact TEXT NOT NULL,
#
#             level TEXT NOT NULL,
#             department TEXT NOT NULL,
#
#             profile_image TEXT,
#             voice_intro TEXT,
#             voice_embedding TEXT,    -- JSON string of embedding
#             face_encoding TEXT,      -- JSON string of 128 float values
#             session_token TEXT,
#             created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
#         );
#     ''')
#
#
#
#     connection.commit()
#

def get_doctor(connection, username):
    cursor = connection.cursor()
    cursor.execute("SELECT * FROM doctors WHERE username = ?", (username,))
    return cursor.fetchone()

def add_student(connection, username, password, stu_id,
                email="", contact="",
                level="", department="",
                profile_image="", voice_intro="",
                voice_embedding=None, face_encoding=None):

    cursor = connection.cursor()
    hashed_password = utils.hash_password(password)

    # Convert voice embedding to JSON string
    embedding_json = None
    if voice_embedding is not None:
        if hasattr(voice_embedding, "tolist"):
            embedding_json = json.dumps(voice_embedding.tolist())
        else:
            embedding_json = json.dumps(voice_embedding)

    # Convert face encoding to JSON string
    face_json = None
    if face_encoding is not None:
        if hasattr(face_encoding, "tolist"):
            face_json = json.dumps(face_encoding.tolist())
        else:
            face_json = json.dumps(face_encoding)

    query = '''
        INSERT INTO students
        (username, password, stu_id, email, contact,
         level, department,
         profile_image, voice_intro,
         voice_embedding, face_encoding)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    '''

    cursor.execute(query, (
        username,
        hashed_password,
        stu_id,
        email,
        contact,
        level,
        department,
        profile_image,
        voice_intro,
        embedding_json,
        face_json
    ))

    connection.commit()



import json
import torch

def get_student_voice_embedding(connection, student_id):
    cursor = connection.cursor()

    cursor.execute(
        "SELECT voice_embedding FROM students WHERE stu_id = ?",
        (student_id,)
    )

    row = cursor.fetchone()

    if row is None:
        return None

    embedding_json = row[0]

    if embedding_json is None:
        return None

    # Convert JSON string back to list
    embedding_list = json.loads(embedding_json)

    # Convert list to torch tensor
    embedding_tensor = torch.tensor(embedding_list, dtype=torch.float32)

    # Normalize (important!)
    embedding_tensor = embedding_tensor / torch.norm(embedding_tensor)

    return embedding_tensor


def add_product(connection,product_data):
    cursor = connection.cursor()
    query = '''INSERT INTO products (name, description, price,img,Category, type) VALUES (?, ?, ?,?,?,?)'''
    cursor.execute(query, (product_data['name'], product_data['description'], product_data['price'],product_data['img'],product_data['Category'],product_data['type']))
    connection.commit()

def delete_user(connection, username):
    cursor = connection.cursor()
    query = ''' DELETE FROM users WHERE username = ? '''
    cursor.execute(query, (username,)) 
    connection.commit()

def update_user(connection , user_data):
    cursor = connection.cursor()
    query = ''' UPDATE users set email = ? , contact = ? WHERE username = ? '''
    cursor.execute(query,(user_data['email'] , user_data['contact'] , user_data['username']))
    connection.commit() 

def update_user_photo(connection, filename , username):
    cursor = connection.cursor()  
    query = '''UPDATE users SET img = ? WHERE username = ?'''
    cursor.execute(query, (filename,username))  
    connection.commit()  

def update_product_photo(connection, filename , name):
    cursor = connection.cursor()  
    query = '''UPDATE products SET img = ? WHERE name = ?'''
    cursor.execute(query, (filename,name))  
    connection.commit() 

def get_user(connection, username):
    cursor = connection.cursor()
    query = '''SELECT * FROM students WHERE username = ?'''
    cursor.execute(query, (username,))
    return cursor.fetchone()

def add_to_cart(connection, username, productID):
    pass


def get_cart_products(connection, username):
    user = get_user(connection, username)
    cursor = connection.cursor()
    query ='''
        SELECT products_id
        FROM payment 
        WHERE user_id = ?;
    '''
    cursor.execute(query, (user[0],))
    print("in get cart product")
    tmp = cursor.fetchall()
    products =[]
    for product in tmp:
        products.append(get_product_byID(connection,product))

    return products, len(tmp)

def get_all_products(connection):
    cursor = connection.cursor()
    query = 'SELECT * FROM products'
    cursor.execute(query)
    return cursor.fetchall()


def get_product_byID(connection, id):
    cursor = connection.cursor()
    query = '''SELECT * FROM products WHERE id = ?'''
    cursor.execute(query, (id,))
    return cursor.fetchone()

def get_product(connection, name):
    cursor = connection.cursor()
    query = '''SELECT * FROM products WHERE name = ?'''
    cursor.execute(query, (name,))
    return cursor.fetchone()

def get_all_users(connection):
    cursor = connection.cursor()
    query = 'SELECT * FROM users'
    cursor.execute(query)
    return cursor.fetchall()

def seed_admin_user(connection):
    admin_username = 'admin'
    admin_password = 'admin'

    admin_user = get_user(connection, admin_username)
    if not admin_user:
        # add_user(connection, admin_username, admin_password)
        print("Admin user seeded successfully.")


def set_active_session(connection, username, token, role='student'):
    """
    Set a session token for a user (student or doctor).
    """
    cursor = connection.cursor()
    # Choose the correct table based on the role
    table = 'doctors' if role == 'doctor' else 'students'
    query = f'''UPDATE {table} SET session_token = ? WHERE username = ?'''
    cursor.execute(query, (token, username))
    connection.commit()


def get_active_session(connection, username, role='student'):
    """
    Get the current active session token of a user.
    Returns None if no active session.
    """
    cursor = connection.cursor()
    table = 'doctors' if role == 'doctor' else 'students'
    query = f'''SELECT session_token FROM {table} WHERE username = ?'''
    cursor.execute(query, (username,))
    result = cursor.fetchone()
    return result[0] if result else None


def get_allowed_objects(connection, exam_id):
    """Return a list of object names that are explicitly allowed in the given exam."""
    rows = connection.execute(
        "SELECT name FROM forbidden_objects WHERE exam_id=? AND allowed=1",
        (exam_id,)
    ).fetchall()
    return [r["name"] for r in rows]


def upsert_exam(connection, exam_id, fields, teacher):
    """Insert a new exam or update an existing one. Returns the exam_id."""
    if exam_id:
        connection.execute("""
            UPDATE exams SET title=?,course_code=?,department=?,level=?,
            start_datetime=?,duration_mins=?,total_marks=?,passing_score=?,
            instructions=?,warning_message=?,status=?,
            proc_webcam=?,proc_face=?,proc_gaze=?,proc_audio=?,
            proc_tab=?,proc_phone=?,proc_multiface=?,locking_mode=?
            WHERE id=? AND teacher_username=?
        """, (*fields[:-1], exam_id, teacher))
        return exam_id
    else:
        cur = connection.execute("""
            INSERT INTO exams
            (title,course_code,department,level,start_datetime,duration_mins,
             total_marks,passing_score,instructions,warning_message,status,
             proc_webcam,proc_face,proc_gaze,proc_audio,proc_tab,proc_phone,
             proc_multiface,locking_mode,teacher_username)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, fields)
        return cur.lastrowid


def save_exam_objects(connection, exam_id, objects):
    """Replace all forbidden/allowed object entries for an exam."""
    connection.execute("DELETE FROM forbidden_objects WHERE exam_id=?", (exam_id,))
    for obj in objects:
        connection.execute(
            "INSERT INTO forbidden_objects (exam_id, name, allowed) VALUES (?,?,?)",
            (exam_id, obj['name'], 1 if obj.get('allowed') else 0)
        )


def save_exam_questions(connection, exam_id, teacher, questions):
    """Replace all questions and their options for an exam."""
    connection.execute("DELETE FROM exam_questions WHERE exam_id=?", (exam_id,))
    for q in questions:
        timer_secs = int(q.get('timer_secs', 0))
        qcur = connection.execute(
            """INSERT INTO exam_questions
               (exam_id, teacher_username, question_text, question_type, points, timer_secs)
               VALUES (?,?,?,?,?,?)""",
            (exam_id, teacher, q.get('text', ''), q.get('type', 'mcq'),
             int(q.get('points', 2)), timer_secs)
        )
        qid = qcur.lastrowid
        for opt in q.get('options', []):
            connection.execute(
                "INSERT INTO exam_options (question_id,label,text,is_correct) VALUES (?,?,?,?)",
                (qid, opt['label'], opt['text'], 1 if opt.get('correct') else 0)
            )


def clear_active_session(connection, username, role='student'):
    """
    Clear the active session token for a user.
    """
    cursor = connection.cursor()
    table = 'doctors' if role == 'doctor' else 'students'
    query = f'''UPDATE {table} SET session_token = NULL WHERE username = ?'''
    cursor.execute(query, (username,))
    connection.commit()




# def set_active_session(connection, username, token):
#     """
#     Set a session token for a student.
#     """
#     cursor = connection.cursor()
#     query = '''UPDATE students SET session_token = ? WHERE username = ?'''
#     cursor.execute(query, (token, username))
#     connection.commit()
#
#
# def get_active_session(connection, username):
#     """
#     Get the current active session token of a student.
#     Returns None if no active session.
#     """
#     cursor = connection.cursor()
#     query = '''SELECT session_token FROM students WHERE username = ?'''
#     cursor.execute(query, (username,))
#     result = cursor.fetchone()
#     return result[0] if result else None
#
#
# def clear_active_session(connection, username):
#     """
#     Clear the active session token for a student.
#     """
#     cursor = connection.cursor()
#     query = '''UPDATE students SET session_token = NULL WHERE username = ?'''
#     cursor.execute(query, (username,))
#     connection.commit()

