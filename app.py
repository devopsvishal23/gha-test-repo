import os
import time
import psycopg2
from flask import Flask, render_template, request, redirect

app = Flask(__name__)

DB_CONFIG = {
    "host": os.environ.get("DB_HOST", "db"),
    "dbname": os.environ.get("DB_NAME", "testdb"),
    "user": os.environ.get("DB_USER", "postgres"),
    "password": os.environ.get("DB_PASSWORD", "postgres"),
}


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
    conn.commit()
    cur.close()
    conn.close()


@app.route("/health")
def health():
    try:
        conn = get_conn()
        conn.close()
        return {"status": "ok"}, 200
    except psycopg2.OperationalError:
        return {"status": "db unreachable"}, 503


@app.route("/")
def index():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id, name, email FROM records ORDER BY id DESC")
    records = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("index.html", records=records)


@app.route("/add", methods=["POST"])
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
    app.run(host="0.0.0.0", port=5000, debug=True)