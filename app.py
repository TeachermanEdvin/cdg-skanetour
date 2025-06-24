from flask import Flask, render_template, request, redirect, url_for
import json
import os

app = Flask(__name__)

DATA_FILE = 'rounds.json'

# --- Helper Functions ---
def load_data():
    if not os.path.exists(DATA_FILE):
        return {"players": {}, "rounds": []}
    with open(DATA_FILE, 'r') as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def calculate_adjusted_and_placements(data, scores):
    adjusted = {
        player: scores[player] - data['players'][player]['handicap']
        for player in scores
    }
    sorted_players = sorted(adjusted.items(), key=lambda x: x[1])
    placements = [p[0] for p in sorted_players]
    return adjusted, placements

def apply_points_and_handicap(data, placements):
    for idx, player in enumerate(placements):
        data['players'][player]['points'] += 3 - idx
    data['players'][placements[0]]['handicap'] = max(0, data['players'][placements[0]]['handicap'] - 1)
    data['players'][placements[2]]['handicap'] += 1

# --- Routes ---
@app.route('/', methods=['GET', 'POST'])
def index():
    data = load_data()
    if request.method == 'POST':
        scores = {
            player: int(request.form[player])
            for player in data['players']
        }
        adjusted, placements = calculate_adjusted_and_placements(data, scores)
        data['rounds'].append({
    "id": len(data['rounds']),
    "scores": scores,
    "adjusted_scores": adjusted,
    "placements": placements
})
        apply_points_and_handicap(data, placements)
        save_data(data)
        return redirect(url_for('index'))
    return render_template('index.html', data=data)

@app.route('/setup', methods=['GET', 'POST'])
def setup():
    if request.method == 'POST':
        names = request.form.getlist('name')
        handicaps = request.form.getlist('handicap')
        data = {
            "players": {
                name: {"handicap": int(h), "points": 0}
                for name, h in zip(names, handicaps)
            },
            "rounds": []
        }
        save_data(data)
        return redirect(url_for('index'))
    return render_template('setup.html')

@app.route('/edit/<int:round_id>', methods=['GET', 'POST'])
def edit_round(round_id):
    data = load_data()
    if request.method == 'POST':
        new_scores = {
            player: int(request.form[player])
            for player in data['players']
        }
        for p in data['players'].values():
            p['points'] = 0
        initial_handicaps = request.form.getlist('initial_handicaps')
        for name, h in zip(data['players'], initial_handicaps):
            data['players'][name]['handicap'] = int(h)

        data['rounds'][round_id]['scores'] = new_scores
        for i, r in enumerate(data['rounds']):
            adjusted, placements = calculate_adjusted_and_placements(data, r['scores'])
            r['adjusted_scores'] = adjusted
            r['placements'] = placements
            apply_points_and_handicap(data, placements)
        save_data(data)
        return redirect(url_for('index'))

    return render_template('edit_round.html', data=data, round_id=round_id)

@app.route('/delete/<int:round_id>', methods=['POST'])
def delete_round(round_id):
    data = load_data()
    data['rounds'].pop(round_id)
    for p in data['players'].values():
        p['points'] = 0
    for i, r in enumerate(data['rounds']):
        adjusted, placements = calculate_adjusted_and_placements(data, r['scores'])
        r['adjusted_scores'] = adjusted
        r['placements'] = placements
        apply_points_and_handicap(data, placements)
        r['id'] = i
    save_data(data)
    return redirect(url_for('index'))

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
