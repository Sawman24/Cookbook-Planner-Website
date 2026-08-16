import os
import sqlite3
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

DATABASE = os.environ.get('DATABASE_PATH', os.path.join(os.path.abspath(os.path.dirname(__file__)), 'recipes.db'))

def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row  # Access columns by name
    return conn

def init_db():
    db_dir = os.path.dirname(DATABASE)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)

    bundled_db = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'recipes.db')
    if not os.path.exists(DATABASE) and os.path.exists(bundled_db) and os.path.abspath(DATABASE) != bundled_db:
        import shutil
        shutil.copy2(bundled_db, DATABASE)

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS recipes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            ingredients TEXT NOT NULL,
            instructions TEXT NOT NULL
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS planner (
            date_key TEXT PRIMARY KEY,
            breakfast TEXT DEFAULT 'Not planned',
            lunch TEXT DEFAULT 'Not planned',
            dinner TEXT DEFAULT 'Not planned',
            tasks TEXT DEFAULT '',
            notes TEXT DEFAULT ''
        )
    ''')
    conn.commit()
    conn.close()

# Initialize the database when the app starts
with app.app_context():
    init_db()

# --- Recipe Endpoints ---

@app.route('/api/recipes', methods=['GET'])
def get_recipes():
    conn = get_db_connection()
    recipes_db = conn.execute('SELECT * FROM recipes ORDER BY id DESC').fetchall()
    conn.close()

    recipes_list = []
    for recipe in recipes_db:
        recipes_list.append({
            'id': recipe['id'],
            'title': recipe['title'],
            'ingredients': recipe['ingredients'],
            'instructions': recipe['instructions']
        })
    return jsonify(recipes_list)

@app.route('/api/recipes/<int:recipe_id>', methods=['GET'])
def get_recipe(recipe_id):
    conn = get_db_connection()
    recipe = conn.execute('SELECT * FROM recipes WHERE id = ?', (recipe_id,)).fetchone()
    conn.close()
    if recipe:
        return jsonify({
            'id': recipe['id'],
            'title': recipe['title'],
            'ingredients': recipe['ingredients'],
            'instructions': recipe['instructions']
        })
    return jsonify({'error': 'Recipe not found'}), 404

@app.route('/api/recipes', methods=['POST'])
def add_recipe():
    data = request.get_json()
    if not data or not all(k in data for k in ('title', 'ingredients', 'instructions')):
        return jsonify({'error': 'Missing data. Required: title, ingredients, instructions'}), 400

    title = data['title'].strip()
    ingredients = data['ingredients'].strip()
    instructions = data['instructions'].strip()

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO recipes (title, ingredients, instructions) VALUES (?, ?, ?)",
            (title, ingredients, instructions)
        )
        conn.commit()
        new_recipe_id = cursor.lastrowid
        conn.close()
        return jsonify({'message': 'Recipe added successfully', 'id': new_recipe_id}), 201
    except sqlite3.Error as e:
        conn.rollback()
        conn.close()
        return jsonify({'error': str(e)}), 500

@app.route('/api/recipes/<int:recipe_id>', methods=['PUT'])
def update_recipe(recipe_id):
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    updates = []
    params = []

    if 'title' in data:
        updates.append("title = ?")
        params.append(data['title'])
    if 'ingredients' in data:
        updates.append("ingredients = ?")
        params.append(data['ingredients'])
    if 'instructions' in data:
        updates.append("instructions = ?")
        params.append(data['instructions'])

    if not updates:
        conn.close()
        return jsonify({'error': 'No fields to update'}), 400

    params.append(recipe_id)
    query = f"UPDATE recipes SET {', '.join(updates)} WHERE id = ?"

    try:
        cursor.execute(query, tuple(params))
        conn.commit()
        rows_affected = cursor.rowcount
        conn.close()
        if rows_affected > 0:
            return jsonify({'message': 'Recipe updated successfully', 'id': recipe_id}), 200
        else:
            return jsonify({'error': 'Recipe not found'}), 404
    except sqlite3.Error as e:
        conn.rollback()
        conn.close()
        return jsonify({'error': str(e)}), 500

@app.route('/api/recipes/<int:recipe_id>', methods=['DELETE'])
def delete_recipe(recipe_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM recipes WHERE id = ?", (recipe_id,))
    conn.commit()
    rows_affected = cursor.rowcount
    conn.close()

    if rows_affected > 0:
        return jsonify({'message': 'Recipe deleted successfully', 'id': recipe_id}), 200
    else:
        return jsonify({'error': 'Recipe not found'}), 404

# --- Planner Endpoints ---

@app.route('/api/planner', methods=['GET'])
def get_planner():
    conn = get_db_connection()
    rows = conn.execute('SELECT * FROM planner').fetchall()
    conn.close()

    planner_data = {}
    for row in rows:
        planner_data[row['date_key']] = {
            'meals': {
                'breakfast': row['breakfast'] or 'Not planned',
                'lunch': row['lunch'] or 'Not planned',
                'dinner': row['dinner'] or 'Not planned'
            },
            'tasks': row['tasks'] or '',
            'notes': row['notes'] or ''
        }
    return jsonify(planner_data)

@app.route('/api/planner/<date_key>', methods=['GET'])
def get_planner_day(date_key):
    conn = get_db_connection()
    row = conn.execute('SELECT * FROM planner WHERE date_key = ?', (date_key,)).fetchone()
    conn.close()

    if row:
        return jsonify({
            'meals': {
                'breakfast': row['breakfast'] or 'Not planned',
                'lunch': row['lunch'] or 'Not planned',
                'dinner': row['dinner'] or 'Not planned'
            },
            'tasks': row['tasks'] or '',
            'notes': row['notes'] or ''
        })
    return jsonify({
        'meals': {'breakfast': 'Not planned', 'lunch': 'Not planned', 'dinner': 'Not planned'},
        'tasks': '',
        'notes': ''
    })

@app.route('/api/planner/<date_key>', methods=['POST', 'PUT'])
def save_planner_day(date_key):
    data = request.get_json() or {}
    meals = data.get('meals', {})
    breakfast = meals.get('breakfast', 'Not planned')
    lunch = meals.get('lunch', 'Not planned')
    dinner = meals.get('dinner', 'Not planned')
    tasks = data.get('tasks', '')
    notes = data.get('notes', '')

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO planner (date_key, breakfast, lunch, dinner, tasks, notes)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(date_key) DO UPDATE SET
                breakfast = excluded.breakfast,
                lunch = excluded.lunch,
                dinner = excluded.dinner,
                tasks = excluded.tasks,
                notes = excluded.notes
        ''', (date_key, breakfast, lunch, dinner, tasks, notes))
        conn.commit()
        conn.close()
        return jsonify({'message': f'Planner data for {date_key} saved successfully', 'date_key': date_key}), 200
    except sqlite3.Error as e:
        conn.rollback()
        conn.close()
        return jsonify({'error': str(e)}), 500

@app.route('/api/planner/<date_key>', methods=['DELETE'])
def delete_planner_day(date_key):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM planner WHERE date_key = ?", (date_key,))
    conn.commit()
    rows_affected = cursor.rowcount
    conn.close()

    if rows_affected > 0:
        return jsonify({'message': f'Planner data for {date_key} deleted successfully'}), 200
    else:
        return jsonify({'error': 'Date entry not found'}), 404

if __name__ == '__main__':
    # For development only. For production, use Gunicorn/Nginx.
    app.run(host='0.0.0.0', port=5000, debug=True)
