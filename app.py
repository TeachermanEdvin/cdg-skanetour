from flask import Flask, render_template, request, redirect, url_for, session
import psycopg2
import os

app = Flask(__name__)
app.secret_key = "supersecure"
DATABASE_URL = os.environ.get("DATABASE_URL")

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
        total_ace INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS rounds (
        id SERIAL PRIMARY KEY
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
            cur.execute("ALTER TABLE players ADD COLUMN IF NOT EXISTS tour_id INTEGER REFERENCES tours(id);")
            cur.execute("ALTER TABLE rounds ADD COLUMN IF NOT EXISTS tour_id INTEGER REFERENCES tours(id);")
        conn.commit()


@app.route('/select_tour', methods=['GET', 'POST'])
def select_tour():
    conn = get_db()
    cur = conn.cursor()
    if request.method == 'POST':
        tour_name = request.form['tour_name']
        cur.execute("INSERT INTO tours (name) VALUES (%s) RETURNING id", (tour_name,))
        session['tour_id'] = cur.fetchone()[0]
        conn.commit()
        return redirect(url_for('setup'))
    cur.execute("SELECT id, name FROM tours ORDER BY created_at DESC")
    tours = cur.fetchall()
    conn.close()
    return render_template('select_tour.html', tours=tours)

@app.route('/set_tour/<int:tour_id>')
def set_tour(tour_id):
    session['tour_id'] = tour_id
    return redirect(url_for('index'))

@app.route('/setup', methods=['GET', 'POST'])
def setup():
    tour_id = session.get('tour_id')
    if not tour_id:
        return redirect(url_for('select_tour'))

    if request.method == 'POST':
        names = request.form.getlist('name')
        handicaps = request.form.getlist('handicap')
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM players WHERE tour_id = %s", (tour_id,))
            for name, h in zip(names, handicaps):
                cur.execute("INSERT INTO players (tour_id, name, handicap) VALUES (%s, %s, %s)", (tour_id, name, int(h)))
            conn.commit()
        return redirect(url_for('index'))
    return render_template('setup.html')

@app.route('/', methods=['GET', 'POST'])
def index():
    init_db()
    tour_id = session.get('tour_id')
    if not tour_id:
        return redirect(url_for('select_tour'))

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
            ace = request.form.get(f'ace_{name}') == '1'
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
                (round_id, info['id'], info['raw'], adjusted[name], place, info['handicap'], info['c2'], bool(info['ctp']), bool(info['ace']))
            )
            points = 4 - place
            cur.execute("UPDATE players SET points = points + %s, total_c2 = total_c2 + %s, total_ctp = total_ctp + %s, total_ace = total_ace + %s WHERE id = %s",
                        (points, info['c2'], info['ctp'], info['ace'], info['id']))
            if place == 1:
                cur.execute("UPDATE players SET handicap = GREATEST(handicap - 1, 0) WHERE id = %s", (info['id'],))
            elif place == 3:
                cur.execute("UPDATE players SET handicap = handicap + 1 WHERE id = %s", (info['id'],))

        conn.commit()
        conn.close()
        return redirect(url_for('index'))

    cur.execute("SELECT id FROM rounds WHERE tour_id = %s ORDER BY id", (tour_id,))
    rounds = cur.fetchall()
    round_data = []
    for r in rounds:
        cur.execute(
            "SELECT rs.*, p.name FROM round_scores rs JOIN players p ON rs.player_id = p.id WHERE rs.round_id = %s ORDER BY rs.placement",
            (r[0],))
        scores = cur.fetchall()
        round_data.append({'id': r[0], 'scores': scores})

    cur.close()
    conn.close()
    return render_template('index.html', players=players, rounds=round_data)

if __name__ == '__main__':
    init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
