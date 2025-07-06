
from flask import Flask, render_template, request, redirect, url_for, session
import psycopg2
import os

app = Flask(__name__)
app.secret_key = 'your_secret_key'

DATABASE_URL = os.environ.get('DATABASE_URL')

def get_db():
    return psycopg2.connect(DATABASE_URL, sslmode='require')

def init_db():
    schema = """
    CREATE TABLE IF NOT EXISTS tours (
        id SERIAL PRIMARY KEY,
        name TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS players (
        id SERIAL PRIMARY KEY,
        name TEXT NOT NULL,
        handicap INTEGER NOT NULL DEFAULT 0,
        points INTEGER NOT NULL DEFAULT 0,
        total_c2 INTEGER NOT NULL DEFAULT 0,
        total_ctp INTEGER NOT NULL DEFAULT 0,
        total_ace INTEGER NOT NULL DEFAULT 0,
        tour_id INTEGER REFERENCES tours(id)
    );
    CREATE TABLE IF NOT EXISTS rounds (
        id SERIAL PRIMARY KEY,
        tour_id INTEGER REFERENCES tours(id)
    );
    CREATE TABLE IF NOT EXISTS round_scores (
        id SERIAL PRIMARY KEY,
        round_id INTEGER REFERENCES rounds(id),
        player_id INTEGER REFERENCES players(id),
        raw_score INTEGER,
        adjusted_score INTEGER,
        placement INTEGER,
        handicap_used INTEGER,
        c2 INTEGER DEFAULT 0,
        ctp BOOLEAN DEFAULT FALSE,
        ace BOOLEAN DEFAULT FALSE
    );
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(schema)
        conn.commit()

@app.route('/', methods=['GET', 'POST'])
def index():
    init_db()
    tour_id = session.get('tour_id', 1)
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, name, handicap, points, total_c2, total_ctp, total_ace FROM players WHERE tour_id = %s ORDER BY id", (tour_id,))
    players = cur.fetchall()

    if request.method == 'POST':
        cur.execute("INSERT INTO rounds (tour_id) VALUES (%s) RETURNING id", (tour_id,))
        round_id = cur.fetchone()[0]

        scores = {}
        for pid, name, hcap, *_ in players:
            score = int(request.form[name])
            c2 = int(request.form.get(f'c2_{name}', 0))
            ctp = f'ctp_{name}' in request.form
            ace = f'ace_{name}' in request.form
            scores[name] = {
                'id': pid,
                'raw': score,
                'handicap': hcap,
                'c2': c2,
                'ctp': int(ctp),
                'ace': int(ace)
            }

        adjusted = {name: s['raw'] - s['handicap'] for name, s in scores.items()}
        placements = sorted(adjusted.items(), key=lambda x: x[1])
        for idx, (name, _) in enumerate(placements):
            info = scores[name]
            place = idx + 1
            cur.execute(
                "INSERT INTO round_scores (round_id, player_id, raw_score, adjusted_score, placement, handicap_used, c2, ctp, ace) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (round_id, info['id'], info['raw'], adjusted[name], place, info['handicap'], info['c2'], info['ctp'], info['ace'])
            )
        conn.commit()
        return redirect(url_for('index'))

    # Load rounds and scores
    cur.execute("SELECT id FROM rounds WHERE tour_id = %s ORDER BY id DESC", (tour_id,))
    round_ids = cur.fetchall()
    rounds = []
    for (rid,) in round_ids:
        cur.execute("SELECT * FROM round_scores WHERE round_id = %s", (rid,))
        scores = cur.fetchall()
        rounds.append({'id': rid, 'scores': scores})

    return render_template('index.html', players=players, rounds=rounds)

@app.route("/setup", methods=["GET", "POST"])
def setup():
    tour_id = session.get("tour_id", 1)
    if request.method == "POST":
        names = request.form.getlist("name")
        handicaps = request.form.getlist("handicap")
        with get_db() as conn:
            with conn.cursor() as cur:
                for name, hcp in zip(names, handicaps):
                    cur.execute(
                        "INSERT INTO players (name, handicap, tour_id) VALUES (%s, %s, %s)",
                        (name, int(hcp), tour_id),
                    )
                conn.commit()
        return redirect(url_for("index"))
    return render_template("setup.html")

@app.route("/select_tour", methods=["GET", "POST"])
def select_tour():
    with get_db() as conn:
        with conn.cursor() as cur:
            if request.method == "POST":
                tour_name = request.form["tour_name"]
                cur.execute("INSERT INTO tours (name) VALUES (%s)", (tour_name,))
                conn.commit()
            cur.execute("SELECT id, name FROM tours ORDER BY created_at DESC")
            tours = cur.fetchall()
    return render_template("select_tour.html", tours=tours)

@app.route("/set_tour/<int:tour_id>")
def set_tour(tour_id):
    session["tour_id"] = tour_id
    return redirect(url_for("index"))

@app.route("/edit_round/<int:round_id>", methods=["GET", "POST"])
def edit_round(round_id):
    tour_id = session.get("tour_id", 1)
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, name, handicap FROM players WHERE tour_id = %s", (tour_id,))
            players = cur.fetchall()
            if request.method == "POST":
                cur.execute("DELETE FROM round_scores WHERE round_id = %s", (round_id,))
                for player in players:
                    name = player[1]
                    raw = int(request.form[name])
                    c2 = int(request.form.get(f'c2_{name}', 0))
                    ctp = f'ctp_{name}' in request.form
                    ace = f'ace_{name}' in request.form
                    adjusted = raw - player[2]
                    cur.execute(
                        "INSERT INTO round_scores (round_id, player_id, raw_score, adjusted_score, placement, handicap_used, c2, ctp, ace) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                        (round_id, player[0], raw, adjusted, 1, player[2], c2, int(ctp), int(ace))
                    )
                conn.commit()
                return redirect(url_for("index"))
            cur.execute("SELECT * FROM round_scores WHERE round_id = %s", (round_id,))
            data = cur.fetchall()
            round_scores = {p[1]: {'raw': r[3], 'c2': r[7], 'ctp': r[8], 'ace': r[9]} for r in data for p in players if p[0] == r[2]}
    return render_template("edit_round.html", round_id=round_id, players=players, round_scores=round_scores)

@app.route("/delete_round/<int:round_id>")
def delete_round(round_id):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM round_scores WHERE round_id = %s", (round_id,))
            cur.execute("DELETE FROM rounds WHERE id = %s", (round_id,))
            conn.commit()
    return redirect(url_for("index"))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, host="0.0.0.0", port=port)