from flask import Flask, render_template, request, redirect, url_for
import psycopg2
import os

app = Flask(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL")

def get_db():
    return psycopg2.connect(DATABASE_URL, sslmode='require')

def init_db():
    schema = """
    CREATE TABLE IF NOT EXISTS players (
        id SERIAL PRIMARY KEY,
        name TEXT NOT NULL UNIQUE,
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
    conn = get_db()
    cur = conn.cursor()
    cur.execute(schema)
    conn.commit()
    cur.close()
    conn.close()

@app.route('/setup', methods=['GET', 'POST'])
def setup():
    if request.method == 'POST':
        names = request.form.getlist('name')
        handicaps = request.form.getlist('handicap')
        conn = get_db()
        cur = conn.cursor()
        cur.execute("DELETE FROM round_scores")
        cur.execute("DELETE FROM rounds")
        cur.execute("DELETE FROM players")
        for name, h in zip(names, handicaps):
            cur.execute("INSERT INTO players (name, handicap) VALUES (%s, %s)", (name, int(h)))
        conn.commit()
        cur.close()
        conn.close()
        return redirect(url_for('index'))
    return render_template('setup.html')

@app.route('/', methods=['GET', 'POST'])
def index():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, name, handicap, points, total_c2, total_ctp, total_ace FROM players ORDER BY id")
    players = cur.fetchall()

    if request.method == 'POST':
        cur.execute("INSERT INTO rounds DEFAULT VALUES RETURNING id")
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
                'ctp': ctp,
                'ace': ace
            }

        adjusted = {
            name: scores[name]['raw'] - scores[name]['handicap']
            for name in scores
        }
        sorted_names = sorted(adjusted.items(), key=lambda x: x[1])
        placements = [name for name, _ in sorted_names]

        for idx, name in enumerate(placements):
            info = scores[name]
            adjusted_score = adjusted[name]
            placement = idx + 1
            cur.execute(
                "INSERT INTO round_scores (round_id, player_id, raw_score, adjusted_score, placement, handicap_used, c2, ctp, ace) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (round_id, info['id'], info['raw'], adjusted_score, placement, info['handicap'], info['c2'], info['ctp'], info['ace'])
            )

            points_add = 4 - placement
            cur.execute("UPDATE players SET points = points + %s, total_c2 = total_c2 + %s, total_ctp = total_ctp + %s, total_ace = total_ace + %s WHERE id = %s",
                        (points_add, info['c2'], info['ctp'], info['ace'], info['id']))

            if placement == 1:
                cur.execute("UPDATE players SET handicap = GREATEST(handicap - 1, 0) WHERE id = %s", (info['id'],))
            elif placement == 3:
                cur.execute("UPDATE players SET handicap = handicap + 1 WHERE id = %s", (info['id'],))

        conn.commit()
        cur.close()
        conn.close()
        return redirect(url_for('index'))

    cur.execute("SELECT id FROM rounds ORDER BY id")
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