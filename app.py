import os
import time
import psycopg2
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import (
    LoginManager,
    UserMixin,
    login_user,
    logout_user,
    login_required,
)
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key-change-me")

login_manager = LoginManager(app)
login_manager.login_view = "login"

DB_CONFIG = {
    "host": os.environ.get("DB_HOST", "db"),
    "dbname": os.environ.get("DB_NAME", "testdb"),
    "user": os.environ.get("DB_USER", "postgres"),
    "password": os.environ.get("DB_PASSWORD", "postgres"),
}

QUOTES = [
    "The only way to do great work is to love what you do. — Steve Jobs",
    "Success is not final, failure is not fatal: it is the courage to continue that counts. — Winston Churchill",
    "Believe you can and you're halfway there. — Theodore Roosevelt",
    "It always seems impossible until it's done. — Nelson Mandela",
    "Don't watch the clock; do what it does. Keep going. — Sam Levenson",
    "The future belongs to those who believe in the beauty of their dreams. — Eleanor Roosevelt",
    "Hardships often prepare ordinary people for an extraordinary destiny. — C.S. Lewis",
    "The secret of getting ahead is getting started. — Mark Twain",
    "You are never too old to set another goal or to dream a new dream. — C.S. Lewis",
    "What lies behind us and what lies before us are tiny matters compared to what lies within us. — Ralph Waldo Emerson",
    "Act as if what you do makes a difference. It does. — William James",
    "Opportunities don't happen. You create them. — Chris Grosser",
    "The way to get started is to quit talking and begin doing. — Walt Disney",
    "Don't be afraid to give up the good to go for the great. — John D. Rockefeller",
    "I find that the harder I work, the more luck I seem to have. — Thomas Jefferson",
    "It does not matter how slowly you go as long as you do not stop. — Confucius",
    "Everything you've ever wanted is on the other side of fear. — George Addair",
    "Success is walking from failure to failure with no loss of enthusiasm. — Winston Churchill",
    "The only limit to our realization of tomorrow will be our doubts of today. — Franklin D. Roosevelt",
    "Do not wait to strike till the iron is hot, but make it hot by striking. — William Butler Yeats",
    "Whether you think you can or you think you can't, you're right. — Henry Ford",
    "Life is 10% what happens to us and 90% how we react to it. — Charles R. Swindoll",
    "The best time to plant a tree was 20 years ago. The second best time is now. — Chinese Proverb",
    "You miss 100% of the shots you don't take. — Wayne Gretzky",
    "Quality is not an act, it is a habit. — Aristotle",
    "Perseverance is not a long race; it is many short races one after another. — Walter Elliot",
    "Your limitation—it's only your imagination. — Unknown",
    "Great things never come from comfort zones. — Unknown",
    "Dream it. Wish it. Do it. — Unknown",
    "Success doesn't just find you. You have to go out and get it. — Unknown",
    "Little things make big days. — Unknown",
    "It's going to be hard, but hard does not mean impossible. — Unknown",
    "Don't wait for opportunity. Create it. — Unknown",
    "Push yourself, because no one else is going to do it for you. — Unknown",
    "Sometimes we're tested not to show our weaknesses, but to discover our strengths. — Unknown",
    "The key to success is to focus on goals, not obstacles. — Unknown",
]

QUOTE_ROTATE_SECONDS = 15 * 60


def current_quote():
    bucket = int(time.time() // QUOTE_ROTATE_SECONDS)
    return QUOTES[bucket % len(QUOTES)]


def get_conn():
    return psycopg2.connect(**DB_CONFIG)


def wait_for_db(retries=30, delay=1):
    for _ in range(retries):
        try:
            conn = get_conn()
            conn.close()
            return
        except psycopg2.OperationalError:
            time.sleep(delay)
    raise RuntimeError("Could not connect to database after retries")


def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS records (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT NOT NULL
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL
        )
    """)
    conn.commit()
    cur.close()
    conn.close()


def seed_admin():
    username = os.environ.get("ADMIN_USERNAME", "admin")
    password = os.environ.get("ADMIN_PASSWORD", "admin")
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE username = %s", (username,))
    if cur.fetchone() is None:
        cur.execute(
            "INSERT INTO users (username, password_hash) VALUES (%s, %s)",
            (username, generate_password_hash(password)),
        )
        conn.commit()
    cur.close()
    conn.close()


class User(UserMixin):
    def __init__(self, id, username):
        self.id = id
        self.username = username


@login_manager.user_loader
def load_user(user_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id, username FROM users WHERE id = %s", (user_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return User(row[0], row[1]) if row else None


@app.route("/health")
def health():
    try:
        conn = get_conn()
        conn.close()
        return {"status": "ok"}, 200
    except psycopg2.OperationalError:
        return {"status": "db unreachable"}, 503


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            "SELECT id, username, password_hash FROM users WHERE username = %s",
            (username,),
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
        if row and check_password_hash(row[2], password):
            login_user(User(row[0], row[1]))
            return redirect(url_for("index"))
        flash("Invalid username or password")
    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


@app.route("/")
@login_required
def index():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id, name, email FROM records ORDER BY id DESC")
    records = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("index.html", records=records, quote=current_quote())


@app.route("/add", methods=["POST"])
@login_required
def add():
    name = request.form["name"]
    email = request.form["email"]
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("INSERT INTO records (name, email) VALUES (%s, %s)", (name, email))
    conn.commit()
    cur.close()
    conn.close()
    return redirect("/")


@app.route("/delete/<int:record_id>")
@login_required
def delete(record_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM records WHERE id = %s", (record_id,))
    conn.commit()
    cur.close()
    conn.close()
    return redirect("/")


if __name__ == "__main__":
    wait_for_db()
    init_db()
    seed_admin()
    app.run(host="0.0.0.0", port=5000, debug=False)