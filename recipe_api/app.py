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
            instructions TEXT NOT NULL,
            category TEXT DEFAULT 'General',
            is_favorite INTEGER DEFAULT 0
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
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS groceries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item TEXT NOT NULL,
            checked INTEGER DEFAULT 0
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS stickies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT NOT NULL,
            author TEXT DEFAULT 'Note',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    # Auto-migrate columns if recipes table already exists without them
    columns = [col[1] for col in cursor.execute('PRAGMA table_info(recipes)').fetchall()]
    if 'category' not in columns:
        cursor.execute("ALTER TABLE recipes ADD COLUMN category TEXT DEFAULT 'General'")
    if 'is_favorite' not in columns:
        cursor.execute("ALTER TABLE recipes ADD COLUMN is_favorite INTEGER DEFAULT 0")

    conn.commit()
    conn.close()

# Initialize the database when the app starts
with app.app_context():
    init_db()

# --- Recipe Endpoints ---

@app.route('/api/recipes', methods=['GET'])
def get_recipes():
    conn = get_db_connection()
    recipes_db = conn.execute('SELECT * FROM recipes ORDER BY is_favorite DESC, id DESC').fetchall()
    conn.close()

    recipes_list = []
    for recipe in recipes_db:
        recipes_list.append({
            'id': recipe['id'],
            'title': recipe['title'],
            'ingredients': recipe['ingredients'],
            'instructions': recipe['instructions'],
            'category': recipe['category'] if 'category' in recipe.keys() else 'General',
            'is_favorite': bool(recipe['is_favorite']) if 'is_favorite' in recipe.keys() else False
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
            'instructions': recipe['instructions'],
            'category': recipe['category'] if 'category' in recipe.keys() else 'General',
            'is_favorite': bool(recipe['is_favorite']) if 'is_favorite' in recipe.keys() else False
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
    category = data.get('category', 'General').strip() or 'General'
    is_favorite = 1 if data.get('is_favorite') else 0

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO recipes (title, ingredients, instructions, category, is_favorite) VALUES (?, ?, ?, ?, ?)",
            (title, ingredients, instructions, category, is_favorite)
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
        params.append(data['title'].strip())
    if 'ingredients' in data:
        updates.append("ingredients = ?")
        params.append(data['ingredients'].strip())
    if 'instructions' in data:
        updates.append("instructions = ?")
        params.append(data['instructions'].strip())
    if 'category' in data:
        updates.append("category = ?")
        params.append(data['category'].strip())
    if 'is_favorite' in data:
        updates.append("is_favorite = ?")
        params.append(1 if data['is_favorite'] else 0)

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

@app.route('/api/recipes/<int:recipe_id>/toggle-favorite', methods=['POST'])
def toggle_favorite(recipe_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    recipe = conn.execute('SELECT is_favorite FROM recipes WHERE id = ?', (recipe_id,)).fetchone()
    if not recipe:
        conn.close()
        return jsonify({'error': 'Recipe not found'}), 404

    new_fav = 0 if recipe['is_favorite'] else 1
    cursor.execute("UPDATE recipes SET is_favorite = ? WHERE id = ?", (new_fav, recipe_id))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Favorite toggled', 'is_favorite': bool(new_fav)}), 200

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
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        existing = cursor.execute('SELECT * FROM planner WHERE date_key = ?', (date_key,)).fetchone()
        
        # Determine meals
        existing_breakfast = existing['breakfast'] if existing else 'Not planned'
        existing_lunch = existing['lunch'] if existing else 'Not planned'
        existing_dinner = existing['dinner'] if existing else 'Not planned'
        existing_tasks = existing['tasks'] if existing else ''
        existing_notes = existing['notes'] if existing else ''
        
        if 'meals' in data:
            meals = data.get('meals') or {}
            breakfast = meals.get('breakfast', existing_breakfast)
            lunch = meals.get('lunch', existing_lunch)
            dinner = meals.get('dinner', existing_dinner)
        else:
            breakfast = data.get('breakfast', existing_breakfast)
            lunch = data.get('lunch', existing_lunch)
            dinner = data.get('dinner', existing_dinner)
            
        tasks = data.get('tasks', existing_tasks)
        notes = data.get('notes', existing_notes)

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

# --- Grocery List Endpoints ---

@app.route('/api/groceries', methods=['GET'])
def get_groceries():
    conn = get_db_connection()
    items = conn.execute('SELECT * FROM groceries ORDER BY checked ASC, id DESC').fetchall()
    conn.close()
    return jsonify([{'id': row['id'], 'item': row['item'], 'checked': bool(row['checked'])} for row in items])

@app.route('/api/groceries', methods=['POST'])
def add_grocery():
    data = request.get_json()
    if not data or 'item' not in data:
        return jsonify({'error': 'Item text is required'}), 400

    items_to_add = data['item']
    if isinstance(items_to_add, str):
        items_list = [line.strip().lstrip('-*• ') for line in items_to_add.split('\n') if line.strip()]
    elif isinstance(items_to_add, list):
        items_list = [str(x).strip().lstrip('-*• ') for x in items_to_add if str(x).strip()]
    else:
        items_list = []

    conn = get_db_connection()
    cursor = conn.cursor()
    for item in items_list:
        cursor.execute("INSERT INTO groceries (item, checked) VALUES (?, 0)", (item,))
    conn.commit()
    conn.close()
    return jsonify({'message': f'Added {len(items_list)} items to groceries'}), 201

@app.route('/api/groceries/<int:item_id>/toggle', methods=['POST'])
def toggle_grocery(item_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    row = conn.execute('SELECT checked FROM groceries WHERE id = ?', (item_id,)).fetchone()
    if not row:
        conn.close()
        return jsonify({'error': 'Item not found'}), 404
    new_status = 0 if row['checked'] else 1
    cursor.execute("UPDATE groceries SET checked = ? WHERE id = ?", (new_status, item_id))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Grocery item updated', 'checked': bool(new_status)}), 200

@app.route('/api/groceries/<int:item_id>', methods=['DELETE'])
def delete_grocery(item_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM groceries WHERE id = ?", (item_id,))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Grocery item deleted'}), 200

@app.route('/api/groceries/clear-checked', methods=['POST'])
def clear_checked_groceries():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM groceries WHERE checked = 1")
    conn.commit()
    conn.close()
    return jsonify({'message': 'Cleared checked groceries'}), 200

# --- Sticky Notes Endpoints ---

@app.route('/api/stickies', methods=['GET'])
def get_stickies():
    conn = get_db_connection()
    rows = conn.execute('SELECT * FROM stickies ORDER BY id DESC').fetchall()
    conn.close()
    return jsonify([{'id': r['id'], 'content': r['content'], 'author': r['author'], 'created_at': r['created_at']} for r in rows])

@app.route('/api/stickies', methods=['POST'])
def add_sticky():
    data = request.get_json() or {}
    content = data.get('content', '').strip()
    author = data.get('author', '').strip() or 'Note'
    if not content:
        return jsonify({'error': 'Content is required'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO stickies (content, author) VALUES (?, ?)", (content, author))
    conn.commit()
    new_id = cursor.lastrowid
    conn.close()
    return jsonify({'message': 'Sticky added', 'id': new_id}), 201

@app.route('/api/stickies/<int:sticky_id>', methods=['DELETE'])
def delete_sticky(sticky_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM stickies WHERE id = ?", (sticky_id,))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Sticky deleted'}), 200

if __name__ == '__main__':
    # For development only. For production, use Gunicorn/Nginx.
    app.run(host='0.0.0.0', port=5000, debug=True)
