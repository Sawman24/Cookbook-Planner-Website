import os
import re
import json
import sqlite3
from datetime import datetime
from fractions import Fraction
import requests
from bs4 import BeautifulSoup
from flask import Flask, request, jsonify, make_response
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
            is_favorite INTEGER DEFAULT 0,
            prep_time TEXT DEFAULT '',
            cook_time TEXT DEFAULT '',
            difficulty TEXT DEFAULT 'Easy',
            servings TEXT DEFAULT ''
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
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS pantry (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item TEXT NOT NULL,
            category TEXT DEFAULT 'General',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Auto-migrate columns if recipes table already exists without them
    recipe_columns = [col[1] for col in cursor.execute('PRAGMA table_info(recipes)').fetchall()]
    if 'category' not in recipe_columns:
        cursor.execute("ALTER TABLE recipes ADD COLUMN category TEXT DEFAULT 'General'")
    if 'is_favorite' not in recipe_columns:
        cursor.execute("ALTER TABLE recipes ADD COLUMN is_favorite INTEGER DEFAULT 0")
    if 'prep_time' not in recipe_columns:
        cursor.execute("ALTER TABLE recipes ADD COLUMN prep_time TEXT DEFAULT ''")
    if 'cook_time' not in recipe_columns:
        cursor.execute("ALTER TABLE recipes ADD COLUMN cook_time TEXT DEFAULT ''")
    if 'difficulty' not in recipe_columns:
        cursor.execute("ALTER TABLE recipes ADD COLUMN difficulty TEXT DEFAULT 'Easy'")
    if 'servings' not in recipe_columns:
        cursor.execute("ALTER TABLE recipes ADD COLUMN servings TEXT DEFAULT ''")

    conn.commit()
    conn.close()

# Initialize the database when the app starts
with app.app_context():
    init_db()

# --- Helper: Smart Ingredient Parser & Consolidator ---

FRACTIONS_MAP = {
    '½': 0.5, '⅓': 1/3, '⅔': 2/3, '¼': 0.25, '¾': 0.75,
    '⅕': 0.2, '⅖': 0.4, '⅗': 0.6, '⅘': 0.8,
    '⅙': 1/6, '⅚': 5/6, '⅛': 0.125, '⅜': 0.375, '⅝': 0.625, '⅞': 0.875
}

UNIT_SYNONYMS = {
    'cups': 'cup', 'cup': 'cup', 'c.': 'cup', 'c': 'cup',
    'tablespoons': 'tbsp', 'tablespoon': 'tbsp', 'tbsp': 'tbsp', 'tbs': 'tbsp', 'tb': 'tbsp', 'tbsps': 'tbsp',
    'teaspoons': 'tsp', 'teaspoon': 'tsp', 'tsp': 'tsp', 'tsps': 'tsp',
    'ounces': 'oz', 'ounce': 'oz', 'oz': 'oz', 'ozs': 'oz',
    'pounds': 'lb', 'pound': 'lb', 'lbs': 'lb', 'lb': 'lb',
    'grams': 'g', 'gram': 'g', 'g': 'g', 'gs': 'g',
    'kilograms': 'kg', 'kilogram': 'kg', 'kg': 'kg', 'kgs': 'kg',
    'milliliters': 'ml', 'milliliter': 'ml', 'ml': 'ml',
    'liters': 'liter', 'liter': 'liter', 'l': 'liter',
    'cloves': 'clove', 'clove': 'clove',
    'cans': 'can', 'can': 'can',
    'slices': 'slice', 'slice': 'slice',
    'stalks': 'stalk', 'stalk': 'stalk',
    'pinches': 'pinch', 'pinch': 'pinch',
    'dashes': 'dash', 'dash': 'dash',
    'packages': 'package', 'package': 'package', 'pkg': 'package', 'pkgs': 'package',
    'bunches': 'bunch', 'bunch': 'bunch',
    'heads': 'head', 'head': 'head'
}

def format_quantity_fraction(amount):
    if amount <= 0:
        return ""
    whole = int(amount)
    remainder = amount - whole
    fraction_str = ""
    # Map common decimals to fractions
    for frac_val, frac_symbol in [
        (0.5, '1/2'), (0.25, '1/4'), (0.75, '3/4'),
        (0.333, '1/3'), (0.666, '2/3'), (0.125, '1/8'),
        (0.375, '3/8'), (0.625, '5/8'), (0.875, '7/8')
    ]:
        if abs(remainder - frac_val) < 0.045:
            fraction_str = frac_symbol
            break
    if fraction_str:
        return f"{whole} {fraction_str}".strip()
    if remainder == 0:
        return str(whole)
    return f"{amount:.2f}".rstrip('0').rstrip('.')

def parse_ingredient_line(line):
    clean = line.strip().lstrip('-*• ').strip()
    if not clean:
        return None

    # Replace unicode fractions
    for unicode_char, val in FRACTIONS_MAP.items():
        if unicode_char in clean:
            clean = clean.replace(unicode_char, f" {val} ")

    clean = re.sub(r'\s+', ' ', clean).strip()

    # Regex for mixed fraction, simple fraction, or decimal/int
    qty_regex = r'^(\d+\s+\d+/\d+|\d+/\d+|\d+(?:\.\d+)?)\s*(.*)$'
    match = re.match(qty_regex, clean)

    if not match:
        return {'qty': None, 'unit': '', 'item': clean, 'raw': clean}

    qty_str = match.group(1).strip()
    rest = match.group(2).strip()

    # Calculate float qty
    try:
        if ' ' in qty_str:
            whole, frac = qty_str.split()
            qty = float(whole) + float(Fraction(frac))
        elif '/' in qty_str:
            qty = float(Fraction(qty_str))
        else:
            qty = float(qty_str)
    except Exception:
        qty = None

    if qty is None:
        return {'qty': None, 'unit': '', 'item': clean, 'raw': clean}

    # Extract unit if present
    words = rest.split()
    unit = ''
    item_words = words
    if words:
        first_word_clean = words[0].lower().rstrip('.,')
        if first_word_clean in UNIT_SYNONYMS:
            unit = UNIT_SYNONYMS[first_word_clean]
            item_words = words[1:]

    item_name = " ".join(item_words).strip()
    # Remove trailing descriptors like ", minced", ", chopped", etc. for grouping
    canonical_item = re.sub(r',?\s*(minced|chopped|diced|sliced|divided|crushed|to taste|optional|melted|softened|room temperature|fresh|grated|peeled|drained)\b', '', item_name, flags=re.I).strip()
    if not canonical_item:
        canonical_item = item_name

    return {
        'qty': qty,
        'unit': unit,
        'item': canonical_item if canonical_item else clean,
        'display_name': item_name if item_name else clean,
        'raw': clean
    }

def consolidate_ingredients(items_list):
    """
    Intelligently merges duplicate ingredients by summing quantities for identical units.
    """
    parsed_items = []
    for raw in items_list:
        parsed = parse_ingredient_line(raw)
        if parsed:
            parsed_items.append(parsed)

    grouped = {}
    unparsed_items = []

    for p in parsed_items:
        if p['qty'] is None:
            # Check if exact unparsed item already added
            if p['raw'] not in unparsed_items:
                unparsed_items.append(p['raw'])
            continue

        key = (p['item'].lower(), p['unit'].lower())
        if key not in grouped:
            grouped[key] = {
                'qty': p['qty'],
                'unit': p['unit'],
                'name': p['display_name']
            }
        else:
            grouped[key]['qty'] += p['qty']

    results = []
    for (item_key, unit_key), data in grouped.items():
        qty_formatted = format_quantity_fraction(data['qty'])
        unit = data['unit']
        if unit:
            # Pluralize common units if needed
            if data['qty'] > 1 and unit in ['cup', 'clove', 'can', 'slice', 'stalk', 'package', 'bunch', 'head']:
                unit = unit + 's'
            results.append(f"{qty_formatted} {unit} {data['name']}".strip())
        else:
            results.append(f"{qty_formatted} {data['name']}".strip())

    for u in unparsed_items:
        if u not in results:
            results.append(u)

    return results

# --- Recipe Web Scraper Helpers & Endpoints ---

VALID_RECIPE_CATEGORIES = [
    'General', 'Breakfast', 'Mains & Entrees', 'Soup', 'Sandwich',
    'Salad', 'Pasta', 'Side Dish', 'Sauce', 'Dressing',
    'Appetizers & Dips', 'Dessert', 'Baking & Bread',
    'Snacks & Smoothies', 'Drinks & Cocktails'
]

def parse_iso_duration(val):
    """Converts ISO 8601 duration (e.g. PT25M, PT1H30M, P0Y0M0DT0H10M0.000S) or numeric minutes into human-readable strings."""
    if not val:
        return ""
    if isinstance(val, (int, float)):
        return f"{int(val)} mins"
    val_str = str(val).strip()
    if not val_str:
        return ""

    # Comprehensive ISO 8601 duration regex matching
    iso_match = re.match(r'^P(?:(\d+)Y)?(?:(\d+)M)?(?:(\d+)W)?(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+(?:\.\d+)?)M)?(?:(\d+(?:\.\d+)?)S)?)?$', val_str, re.IGNORECASE)
    if iso_match:
        years, months, weeks, days, hours, minutes, seconds = iso_match.groups()
        parts = []
        if days and int(days) > 0:
            parts.append(f"{int(days)} day{'s' if int(days) > 1 else ''}")
        if hours and int(hours) > 0:
            parts.append(f"{int(hours)} hr{'s' if int(hours) > 1 else ''}")
        if minutes and float(minutes) > 0:
            m_val = int(float(minutes))
            parts.append(f"{m_val} min{'s' if m_val > 1 else ''}")
        if seconds and float(seconds) > 0 and not hours and not minutes:
            s_val = int(float(seconds))
            parts.append(f"{s_val} secs")
        return " ".join(parts) if parts else ""

    return val_str

def classify_recipe_category(title, raw_category="", text=""):
    """Intelligently maps raw category or recipe keywords to one of the 15 supported categories."""
    t_lower = title.lower()
    raw_lower = raw_category.lower()
    combined = f"{title} {raw_category} {text}".lower()

    # Exact match on raw category if present
    for cat in VALID_RECIPE_CATEGORIES:
        if cat.lower() in raw_lower:
            return cat

    # High priority matching on recipe title
    if any(k in t_lower for k in ['soup', 'stew', 'chowder', 'chili', 'bisque', 'broth', 'ramen', 'gumbo']):
        return 'Soup'
    if any(k in t_lower for k in ['sandwich', 'burger', 'panini', 'wrap', 'sub', 'toast', 'grilled cheese', 'slider', 'tacos', 'taco', 'fajita', 'burrito', 'quesadilla']):
        return 'Mains & Entrees'
    if any(k in t_lower for k in ['salad', 'slaw', 'vinaigrette salad']):
        return 'Salad'
    if any(k in t_lower for k in ['pasta', 'spaghetti', 'fettuccine', 'penne', 'lasagna', 'ravioli', 'macaroni', 'carbonara', 'bolognese', 'gnocchi', 'noodles', 'alfredo']):
        return 'Pasta'
    if any(k in t_lower for k in ['pancake', 'waffle', 'omelet', 'egg', 'oatmeal', 'french toast', 'crepe', 'frittata', 'breakfast', 'granola']):
        return 'Breakfast'
    if any(k in t_lower for k in ['cookie', 'cake', 'brownie', 'cupcake', 'pie', 'tart', 'pudding', 'ice cream', 'dessert', 'cheesecake', 'tiramisu', 'fudge', 'chocolate', 'frosting']):
        return 'Dessert'
    if any(k in t_lower for k in ['bread', 'biscuit', 'scone', 'muffin', 'focaccia', 'sourdough', 'dough', 'loaf', 'crust', 'bagel', 'roll', 'bun']):
        return 'Baking & Bread'
    if any(k in t_lower for k in ['dressing', 'vinaigrette']):
        return 'Dressing'
    if any(k in t_lower for k in ['sauce', 'salsa', 'gravy', 'marinade', 'pesto', 'mayo', 'aioli', 'glaze']):
        return 'Sauce'
    if any(k in t_lower for k in ['chicken', 'beef', 'steak', 'pork', 'salmon', 'fish', 'roast', 'casserole', 'curry', 'stir fry', 'ribs', 'meatball', 'main', 'dinner', 'entree', 'pork chop', 'shrimp']):
        return 'Mains & Entrees'

    # Fallback matching on full text
    if any(k in combined for k in ['soup', 'stew', 'chowder', 'chili', 'bisque', 'broth', 'ramen', 'gumbo']):
        return 'Soup'
    if any(k in combined for k in ['sandwich', 'burger', 'panini', 'wrap', 'sub', 'toast', 'grilled cheese', 'slider']):
        return 'Sandwich'
    if any(k in combined for k in ['salad', 'slaw', 'vinaigrette salad']):
        return 'Salad'
    if any(k in combined for k in ['pasta', 'spaghetti', 'fettuccine', 'penne', 'lasagna', 'ravioli', 'macaroni', 'carbonara', 'bolognese', 'gnocchi', 'noodles', 'alfredo']):
        return 'Pasta'
    if any(k in combined for k in ['pancake', 'waffle', 'omelet', 'egg', 'oatmeal', 'french toast', 'crepe', 'frittata', 'breakfast', 'granola']):
        return 'Breakfast'
    if any(k in combined for k in ['cocktail', 'margarita', 'martini', 'drink', 'punch', 'mocktail']):
        return 'Drinks & Cocktails'
    if any(k in combined for k in ['smoothie', 'shake', 'latte', 'lemonade', 'juice']):
        return 'Snacks & Smoothies'
    if any(k in combined for k in ['cookie', 'cake', 'brownie', 'cupcake', 'pie', 'tart', 'pudding', 'ice cream', 'dessert', 'cheesecake', 'tiramisu', 'fudge', 'chocolate', 'frosting']):
        return 'Dessert'
    if any(k in combined for k in ['bread', 'biscuit', 'scone', 'muffin', 'focaccia', 'sourdough', 'dough', 'loaf', 'crust', 'bagel', 'roll', 'bun']):
        return 'Baking & Bread'
    if any(k in combined for k in ['dressing', 'vinaigrette']):
        return 'Dressing'
    if any(k in combined for k in ['sauce', 'salsa', 'gravy', 'marinade', 'pesto', 'mayo', 'aioli', 'glaze']):
        return 'Sauce'
    if any(k in combined for k in ['dip', 'appetizer', 'bruschetta', 'nachos', 'wings', 'snack', 'crostini', 'bites', 'tapas']):
        return 'Appetizers & Dips'
    if any(k in combined for k in ['chicken', 'beef', 'steak', 'pork', 'salmon', 'fish', 'tacos', 'roast', 'casserole', 'curry', 'stir fry', 'ribs', 'meatball', 'main', 'dinner', 'entree', 'pork chop', 'shrimp']):
        return 'Mains & Entrees'
    if any(k in combined for k in ['side', 'potato', 'fries', 'vegetables', 'rice dish', 'green beans', 'asparagus']):
        return 'Side Dish'

    return 'General'

def fetch_recipe_html(url):
    """Fetches raw HTML from a recipe URL with multiple browser fingerprints and automatic proxy fallback for bot-protected websites."""
    header_variants = [
        # Variant 1: Mobile Safari with cross-site Referer (bypasses Dotdash Meredith / Allrecipes / Serious Eats / Cloudflare blogs)
        {
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_4_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Mobile/15E148 Safari/604.1',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': 'https://www.google.com/',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'cross-site'
        },
        # Variant 2: Modern Desktop Chrome
        {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': 'https://www.google.com/'
        }
    ]

    # Step 1: Try direct fetches with different header fingerprints
    for headers in header_variants:
        try:
            session = requests.Session()
            resp = session.get(url, headers=headers, timeout=10, allow_redirects=True)
            if resp.status_code == 200 and len(resp.text) > 400:
                lowered = resp.text[:2500].lower()
                is_challenge = any(x in lowered for x in [
                    '<title>just a moment...</title>',
                    '<title>access denied</title>',
                    '<title>attention required! | cloudflare</title>',
                    '<title>403 forbidden</title>',
                    '<title>robot or human?</title>',
                    '<title>security check</title>',
                    'action="/_bm/_data"',
                    'cf-browser-verification',
                    'id="challenge-running"'
                ])
                if not is_challenge:
                    return resp.text
        except Exception:
            pass

    # Step 2: Google Residential Proxy Mirror (Bypasses Datacenter IP 403 on Linux Ubuntu Servers for Allrecipes, Dotdash Meredith, NYT, Cloudflare blogs)
    gt_url = f"https://translate.google.com/translate?sl=auto&tl=en&u={url}"
    try:
        resp = requests.get(gt_url, headers=header_variants[1], timeout=10)
        if resp.status_code == 200 and len(resp.text) > 1000:
            return resp.text
    except Exception:
        pass

    # Step 3: Fallback to Jina Reader proxy with HTML output (bypasses Akamai/Cloudflare EdgeSuite like Food Network)
    jina_url = f"https://r.jina.ai/{url}"
    try:
        resp = requests.get(jina_url, headers={'User-Agent': 'Mozilla/5.0', 'X-Return-Format': 'html'}, timeout=15)
        if resp.status_code == 200 and len(resp.text) > 400:
            return resp.text
    except Exception:
        pass

    # Step 4: Final attempt with standard Jina markdown text
    try:
        resp = requests.get(jina_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
        if resp.status_code == 200 and len(resp.text) > 200:
            return resp.text
    except Exception:
        pass

    # Step 5: Public Web Proxy Mirror
    try:
        resp = requests.get(f"https://api.allorigins.win/raw?url={requests.utils.quote(url)}", headers={'User-Agent': 'Mozilla/5.0'}, timeout=8)
        if resp.status_code == 200 and len(resp.text) > 500:
            return resp.text
    except Exception:
        pass

    # Step 6: Re-run direct request to raise descriptive HTTP error if website was completely unreachable
    resp = requests.get(url, headers=header_variants[0], timeout=12, allow_redirects=True)
    resp.raise_for_status()
    return resp.text

def extract_recipe_from_url(url, raw_content=None):
    """
    Extracts recipe metadata from URL or raw content using a multi-strategy engine:
    1. recipe-scrapers library (scrape_me / scrape_html with wild_mode=True)
    2. Deep BeautifulSoup Schema.org JSON-LD parser (supports nested @graph, HowToStep, HowToSection)
    3. Microdata & Recipe Plugin DOM selectors (WP Recipe Maker, Tasty Recipes, Create by Mediavine, etc.)
    4. Markdown & plaintext regex fallback
    """
    html_content = raw_content if raw_content else fetch_recipe_html(url)

    title = ""
    ingredients = []
    instructions = []
    prep_time = ""
    cook_time = ""
    servings = ""
    category = "General"

    # Strategy 1: recipe-scrapers library (Primary extractor for 150+ sites + schema.org)
    try:
        from recipe_scrapers import scrape_html, scrape_me
        scraper = None
        if "<" in html_content and ">" in html_content:
            try:
                scraper = scrape_html(html_content, org_url=url, wild_mode=True)
            except Exception:
                scraper = None

        if scraper is None and not raw_content:
            try:
                scraper = scrape_me(url, wild_mode=True)
            except Exception:
                scraper = None

        if scraper:
            try:
                t = scraper.title()
                if t:
                    title = str(t).strip()
            except Exception:
                pass

            try:
                ings = scraper.ingredients()
                if ings:
                    ingredients = [str(x).strip() for x in ings if str(x).strip()]
            except Exception:
                pass

            try:
                if hasattr(scraper, 'instructions_list'):
                    inst_list = scraper.instructions_list()
                    if inst_list:
                        instructions = [str(x).strip() for x in inst_list if str(x).strip()]
                if not instructions:
                    raw_inst = scraper.instructions()
                    if isinstance(raw_inst, str) and raw_inst.strip():
                        instructions = [line.strip() for line in raw_inst.split('\n') if line.strip()]
                    elif isinstance(raw_inst, list):
                        instructions = [str(x).strip() for x in raw_inst if str(x).strip()]
            except Exception:
                pass

            try:
                p = scraper.prep_time()
                if p:
                    prep_time = f"{int(p)} mins" if isinstance(p, (int, float)) else parse_iso_duration(p)
            except Exception:
                pass

            try:
                c = scraper.cook_time()
                if c:
                    cook_time = f"{int(c)} mins" if isinstance(c, (int, float)) else parse_iso_duration(c)
                if not cook_time:
                    tot = scraper.total_time()
                    if tot:
                        cook_time = f"{int(tot)} mins" if isinstance(tot, (int, float)) else parse_iso_duration(tot)
            except Exception:
                pass

            try:
                y = scraper.yields()
                if y:
                    servings = str(y).strip()
            except Exception:
                pass

            try:
                raw_cat = scraper.category() or ""
                category = classify_recipe_category(title, raw_cat, " ".join(ingredients))
            except Exception:
                pass
    except Exception:
        pass

    # Strategy 2: Deep Schema.org JSON-LD parser (BeautifulSoup or Regex)
    if not title or not ingredients or not instructions:
        json_ld_matches = re.findall(r'<script[^>]+type=[\"\']application/ld\+json[\"\'][^>]*>(.*?)</script>', html_content, re.DOTALL | re.I)
        recipe_nodes = []

        def search_nodes(node):
            if isinstance(node, dict):
                t = node.get('@type')
                if t == 'Recipe' or (isinstance(t, list) and 'Recipe' in t) or (isinstance(t, str) and 'recipe' in t.lower()):
                    recipe_nodes.append(node)
                if '@graph' in node and isinstance(node['@graph'], list):
                    for sub in node['@graph']:
                        search_nodes(sub)
                if 'mainEntity' in node:
                    search_nodes(node['mainEntity'])
            elif isinstance(node, list):
                for item in node:
                    search_nodes(item)

        for raw_json in json_ld_matches:
            content = raw_json.strip()
            if not content:
                continue
            try:
                parsed_json = json.loads(content)
                search_nodes(parsed_json)
            except Exception:
                continue

        for r in recipe_nodes:
            if not title:
                title = r.get('name') or r.get('headline') or ''

            if not ingredients and 'recipeIngredient' in r:
                raw_ing = r['recipeIngredient']
                if isinstance(raw_ing, list):
                    ingredients = [str(x).strip() for x in raw_ing if str(x).strip()]
                elif isinstance(raw_ing, str):
                    ingredients = [line.strip() for line in raw_ing.split('\n') if line.strip()]

            if not instructions and 'recipeInstructions' in r:
                raw_inst = r['recipeInstructions']
                if isinstance(raw_inst, list):
                    for step in raw_inst:
                        if isinstance(step, dict):
                            if 'itemListElement' in step and isinstance(step['itemListElement'], list):
                                for sub_step in step['itemListElement']:
                                    if isinstance(sub_step, dict) and 'text' in sub_step:
                                        instructions.append(str(sub_step['text']).strip())
                                    elif isinstance(sub_step, str):
                                        instructions.append(sub_step.strip())
                            elif 'text' in step:
                                instructions.append(str(step['text']).strip())
                        elif isinstance(step, str):
                            instructions.append(step.strip())
                elif isinstance(raw_inst, str):
                    instructions = [line.strip() for line in raw_inst.split('\n') if line.strip()]

            if not prep_time and 'prepTime' in r:
                prep_time = parse_iso_duration(r['prepTime'])

            if not cook_time:
                if 'cookTime' in r:
                    cook_time = parse_iso_duration(r['cookTime'])
                elif 'totalTime' in r:
                    cook_time = parse_iso_duration(r['totalTime'])

            if not servings and ('recipeYield' in r or 'yield' in r):
                y = r.get('recipeYield') or r.get('yield')
                if isinstance(y, list) and len(y) > 1 and not str(y[0]).isalpha():
                    servings = str(y[-1])
                elif isinstance(y, list) and y:
                    servings = str(y[0])
                else:
                    servings = str(y or '')

            if category == 'General' and 'recipeCategory' in r:
                cat_val = r['recipeCategory']
                cat_str = ", ".join(cat_val) if isinstance(cat_val, list) else str(cat_val)
                category = classify_recipe_category(title, cat_str, " ".join(ingredients))

            if title and ingredients and instructions:
                break

    # Strategy 3: Microdata & Recipe Plugin HTML DOM Parser (WordPress Recipe Maker, Tasty, Mediavine Create, etc.)
    if not title or not ingredients or not instructions:
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html_content, 'html.parser')

            if not title:
                t_el = soup.select_one('[itemprop="name"], .recipe-title, .wprm-recipe-name, .tasty-recipes-title, .mv-create-title, h1.entry-title, h1')
                if t_el:
                    title = t_el.get_text().strip()

            if not ingredients:
                ing_els = soup.select('[itemprop="recipeIngredient"], [itemprop="ingredients"], .wprm-recipe-ingredient, .tasty-recipes-ingredients li, .mv-create-ingredients li, .recipe-ingredients li, ul.recipe-ingredients li, .ingredients-item')
                if ing_els:
                    ingredients = [el.get_text().strip() for el in ing_els if el.get_text().strip()]

            if not instructions:
                inst_els = soup.select('[itemprop="recipeInstructions"], .wprm-recipe-instruction-text, .tasty-recipes-instructions li, .mv-create-instructions li, .recipe-instructions li, ol.recipe-instructions li, .instructions-section li, .direction-step')
                if inst_els:
                    instructions = [el.get_text().strip() for el in inst_els if el.get_text().strip()]

            if not prep_time:
                p_el = soup.select_one('.wprm-recipe-prep-time-container, .tasty-recipes-prep-time, [itemprop="prepTime"]')
                if p_el:
                    prep_time = parse_iso_duration(p_el.get_text().strip())

            if not cook_time:
                c_el = soup.select_one('.wprm-recipe-cook-time-container, .tasty-recipes-cook-time, [itemprop="cookTime"]')
                if c_el:
                    cook_time = parse_iso_duration(c_el.get_text().strip())

            if not servings:
                s_el = soup.select_one('.wprm-recipe-servings, .tasty-recipes-yield, [itemprop="recipeYield"]')
                if s_el:
                    servings = s_el.get_text().strip()
        except Exception:
            pass

    # Strategy 4: Markdown / Plaintext Fallback Parser
    if not title or not ingredients or not instructions:
        title_match = re.search(r'^(?:#\s*|Title:\s*)(.+)$', html_content, re.MULTILINE)
        if title_match and not title:
            title = title_match.group(1).strip()

        if not ingredients:
            ing_matches = re.findall(r'^\s*(?:-\s*\[[ xX]\]|[-*•])\s*(.+)$', html_content, re.MULTILINE)
            clean_ings = [m.strip() for m in ing_matches if not any(x in m.lower() for x in ['deselect', 'cookie', 'privacy', 'personal information', 'shopping list', 'cook mode', 'advertisement', 'share', 'print', 'pin recipe'])]
            if clean_ings:
                ingredients = clean_ings

        if not instructions:
            dir_sec = re.search(r'###?\s*(?:Directions|Instructions|Steps|Preparation|Method)\s*\n(.*?)(?:###?|$)', html_content, re.DOTALL | re.I)
            if dir_sec:
                for l in dir_sec.group(1).split('\n'):
                    l = l.strip()
                    if not l or l.startswith('![') or l.startswith('[Watch') or 'watch how' in l.lower():
                        continue
                    cleaned = re.sub(r'^(?:\d+[\.\)]|step\s+\d+[:\.]?|[-*•])\s*', '', l, flags=re.I).strip()
                    if cleaned:
                        instructions.append(cleaned)

    # Strategy 5: HTML Document <title> fallback
    if not title:
        title_match = re.search(r'<title>(.*?)</title>', html_content, re.I)
        if title_match:
            title = title_match.group(1).split('|')[0].split(' - ')[0].split(' – ')[0].strip()

    if not title or not (ingredients or instructions):
        raise ValueError("Could not automatically detect recipe information from this URL. Please verify the URL or enter the recipe manually.")

    # Clean and format ingredient list
    clean_ing_list = []
    for ing in ingredients:
        cleaned = re.sub(r'[\xa0\u200b]+', ' ', ing).strip().lstrip('-*• ')
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        if cleaned and not any(x in cleaned.lower() for x in [
            'deselect all', 'add to shopping list', 'view shopping list',
            'cook mode (keep screen awake)', 'advertisement', 'nutrition facts',
            'yield:', 'prep time:', 'cook time:', 'total time:'
        ]):
            clean_ing_list.append(cleaned)

    formatted_ingredients = "\n".join([f"- {ing}" for ing in clean_ing_list]) if clean_ing_list else ""

    # Format numbered instructions
    formatted_instructions = []
    for i, step in enumerate(instructions, 1):
        step_clean = re.sub(r'[\xa0\u200b]+', ' ', step).strip()
        step_clean = re.sub(r'^(?:\d+[\.\)]|step\s+\d+[:\.]?|[-*•])\s*', '', step_clean, flags=re.I).strip()
        step_clean = re.sub(r'\s+', ' ', step_clean).strip()
        if step_clean and not step_clean.startswith('![') and not step_clean.startswith('[Watch') and 'watch how' not in step_clean.lower():
            formatted_instructions.append(f"{i}) {step_clean}")
    formatted_instructions_text = "\n\n".join(formatted_instructions) if formatted_instructions else "\n".join(instructions)

    # Recalculate category with all available data
    final_category = classify_recipe_category(title, category, " ".join(clean_ing_list) + " " + formatted_instructions_text)

    # Estimate difficulty
    difficulty = "Easy"
    if len(formatted_instructions) > 8 or len(clean_ing_list) > 12:
        difficulty = "Hard"
    elif len(formatted_instructions) > 4 or len(clean_ing_list) > 7:
        difficulty = "Medium"

    return {
        'title': title.strip(),
        'ingredients': formatted_ingredients.strip(),
        'instructions': formatted_instructions_text.strip(),
        'prep_time': prep_time.strip(),
        'cook_time': cook_time.strip(),
        'servings': servings.strip(),
        'difficulty': difficulty,
        'category': final_category,
        'source_url': url
    }

@app.route('/api/recipes/import-url', methods=['POST'])
def import_recipe_from_url():
    data = request.get_json()
    if not data or ('url' not in data and 'raw_text' not in data):
        return jsonify({'error': 'URL or raw_text is required'}), 400

    url = data.get('url', '').strip()
    raw_text = data.get('raw_text', '').strip() or None

    if url and not url.startswith('http://') and not url.startswith('https://'):
        url = 'https://' + url

    try:
        recipe_data = extract_recipe_from_url(url, raw_content=raw_text)
        return jsonify(recipe_data), 200
    except requests.exceptions.RequestException as e:
        return jsonify({'error': f'Could not reach website ({str(e)})'}), 400
    except ValueError as e:
        return jsonify({'error': str(e)}), 422
    except Exception as e:
        return jsonify({'error': f'Failed to scrape recipe: {str(e)}'}), 500

# --- Recipe Endpoints ---

@app.route('/api/recipes', methods=['GET'])
def get_recipes():
    conn = get_db_connection()
    recipes_db = conn.execute('SELECT * FROM recipes ORDER BY is_favorite DESC, id DESC').fetchall()
    conn.close()

    recipes_list = []
    for recipe in recipes_db:
        keys = recipe.keys()
        recipes_list.append({
            'id': recipe['id'],
            'title': recipe['title'],
            'ingredients': recipe['ingredients'],
            'instructions': recipe['instructions'],
            'category': recipe['category'] if 'category' in keys else 'General',
            'is_favorite': bool(recipe['is_favorite']) if 'is_favorite' in keys else False,
            'prep_time': recipe['prep_time'] if 'prep_time' in keys else '',
            'cook_time': recipe['cook_time'] if 'cook_time' in keys else '',
            'difficulty': recipe['difficulty'] if 'difficulty' in keys else 'Easy',
            'servings': recipe['servings'] if 'servings' in keys else ''
        })
    return jsonify(recipes_list)

@app.route('/api/recipes/<int:recipe_id>', methods=['GET'])
def get_recipe(recipe_id):
    conn = get_db_connection()
    recipe = conn.execute('SELECT * FROM recipes WHERE id = ?', (recipe_id,)).fetchone()
    conn.close()
    if recipe:
        keys = recipe.keys()
        return jsonify({
            'id': recipe['id'],
            'title': recipe['title'],
            'ingredients': recipe['ingredients'],
            'instructions': recipe['instructions'],
            'category': recipe['category'] if 'category' in keys else 'General',
            'is_favorite': bool(recipe['is_favorite']) if 'is_favorite' in keys else False,
            'prep_time': recipe['prep_time'] if 'prep_time' in keys else '',
            'cook_time': recipe['cook_time'] if 'cook_time' in keys else '',
            'difficulty': recipe['difficulty'] if 'difficulty' in keys else 'Easy',
            'servings': recipe['servings'] if 'servings' in keys else ''
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
    prep_time = data.get('prep_time', '').strip()
    cook_time = data.get('cook_time', '').strip()
    difficulty = data.get('difficulty', 'Easy').strip() or 'Easy'
    servings = data.get('servings', '').strip()

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO recipes (title, ingredients, instructions, category, is_favorite, prep_time, cook_time, difficulty, servings) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (title, ingredients, instructions, category, is_favorite, prep_time, cook_time, difficulty, servings)
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
    if 'prep_time' in data:
        updates.append("prep_time = ?")
        params.append(data['prep_time'].strip())
    if 'cook_time' in data:
        updates.append("cook_time = ?")
        params.append(data['cook_time'].strip())
    if 'difficulty' in data:
        updates.append("difficulty = ?")
        params.append(data['difficulty'].strip())
    if 'servings' in data:
        updates.append("servings = ?")
        params.append(data['servings'].strip())

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
            return jsonify({'message': 'Recipe updated successfully'}), 200
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
    row = conn.execute('SELECT is_favorite FROM recipes WHERE id = ?', (recipe_id,)).fetchone()
    if not row:
        conn.close()
        return jsonify({'error': 'Recipe not found'}), 404
    new_fav = 0 if row['is_favorite'] else 1
    cursor.execute('UPDATE recipes SET is_favorite = ? WHERE id = ?', (new_fav, recipe_id))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Favorite status toggled', 'is_favorite': bool(new_fav)}), 200

@app.route('/api/recipes/<int:recipe_id>', methods=['DELETE'])
def delete_recipe(recipe_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM recipes WHERE id = ?", (recipe_id,))
        conn.commit()
        rows_affected = cursor.rowcount
        conn.close()
        if rows_affected > 0:
            return jsonify({'message': 'Recipe deleted successfully'}), 200
        else:
            return jsonify({'error': 'Recipe not found'}), 404
    except sqlite3.Error as e:
        conn.rollback()
        conn.close()
        return jsonify({'error': str(e)}), 500

# --- Planner Endpoints ---

@app.route('/api/planner', methods=['GET'])
def get_planner():
    conn = get_db_connection()
    planner_db = conn.execute('SELECT * FROM planner').fetchall()
    conn.close()

    planner_data = {}
    for entry in planner_db:
        planner_data[entry['date_key']] = {
            'meals': {
                'breakfast': entry['breakfast'],
                'lunch': entry['lunch'],
                'dinner': entry['dinner']
            },
            'tasks': entry['tasks'],
            'notes': entry['notes']
        }
    return jsonify(planner_data)

@app.route('/api/planner/<string:date_key>', methods=['GET'])
def get_planner_day(date_key):
    conn = get_db_connection()
    entry = conn.execute('SELECT * FROM planner WHERE date_key = ?', (date_key,)).fetchone()
    conn.close()
    if entry:
        return jsonify({
            'date_key': entry['date_key'],
            'meals': {
                'breakfast': entry['breakfast'],
                'lunch': entry['lunch'],
                'dinner': entry['dinner']
            },
            'tasks': entry['tasks'],
            'notes': entry['notes']
        })
    else:
        return jsonify({
            'date_key': date_key,
            'meals': {'breakfast': 'Not planned', 'lunch': 'Not planned', 'dinner': 'Not planned'},
            'tasks': '',
            'notes': ''
        })

@app.route('/api/planner/<string:date_key>', methods=['POST'])
def save_planner_day(date_key):
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    existing = conn.execute('SELECT * FROM planner WHERE date_key = ?', (date_key,)).fetchone()

    if existing:
        meals = data.get('meals', {})
        breakfast = meals.get('breakfast', existing['breakfast'])
        lunch = meals.get('lunch', existing['lunch'])
        dinner = meals.get('dinner', existing['dinner'])
        tasks = data.get('tasks', existing['tasks'])
        notes = data.get('notes', existing['notes'])
    else:
        meals = data.get('meals', {})
        breakfast = meals.get('breakfast', 'Not planned')
        lunch = meals.get('lunch', 'Not planned')
        dinner = meals.get('dinner', 'Not planned')
        tasks = data.get('tasks', '')
        notes = data.get('notes', '')

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
        return jsonify({'message': f'Planner updated for {date_key}'}), 200
    except sqlite3.Error as e:
        conn.rollback()
        conn.close()
        return jsonify({'error': str(e)}), 500

@app.route('/api/planner/<string:date_key>', methods=['DELETE'])
def clear_planner_day(date_key):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM planner WHERE date_key = ?", (date_key,))
    conn.commit()
    rows_affected = cursor.rowcount
    conn.close()
    if rows_affected > 0:
        return jsonify({'message': f'Planner cleared for {date_key}'}), 200
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
    do_consolidate = data.get('consolidate', True)

    if isinstance(items_to_add, str):
        items_list = [line.strip().lstrip('-*• ') for line in items_to_add.split('\n') if line.strip()]
    elif isinstance(items_to_add, list):
        items_list = [str(x).strip().lstrip('-*• ') for x in items_to_add if str(x).strip()]
    else:
        items_list = []

    if do_consolidate and len(items_list) > 1:
        items_list = consolidate_ingredients(items_list)

    conn = get_db_connection()
    cursor = conn.cursor()
    for item in items_list:
        cursor.execute("INSERT INTO groceries (item, checked) VALUES (?, 0)", (item,))
    conn.commit()
    conn.close()
    return jsonify({'message': f'Added {len(items_list)} items to groceries'}), 201

@app.route('/api/groceries/consolidate', methods=['POST'])
def consolidate_grocery_list():
    """
    Consolidates unchecked grocery items in the database by combining identical ingredients and quantities.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    unchecked_rows = conn.execute('SELECT id, item FROM groceries WHERE checked = 0').fetchall()

    if not unchecked_rows:
        conn.close()
        return jsonify({'message': 'No unchecked groceries to consolidate', 'count': 0}), 200

    raw_items = [r['item'] for r in unchecked_rows]
    consolidated = consolidate_ingredients(raw_items)

    # Delete existing unchecked rows and re-insert consolidated ones
    cursor.execute('DELETE FROM groceries WHERE checked = 0')
    for item in consolidated:
        cursor.execute('INSERT INTO groceries (item, checked) VALUES (?, 0)', (item,))

    conn.commit()
    conn.close()
    return jsonify({
        'message': f'Consolidated {len(raw_items)} items into {len(consolidated)} clean items!',
        'count': len(consolidated)
    }), 200

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

# --- Pantry & "What Can I Make?" Endpoints ---

@app.route('/api/pantry', methods=['GET'])
def get_pantry():
    conn = get_db_connection()
    items = conn.execute('SELECT * FROM pantry ORDER BY item ASC').fetchall()
    conn.close()
    return jsonify([{
        'id': row['id'],
        'item': row['item'],
        'category': row['category'] if 'category' in row.keys() else 'General'
    } for row in items])

@app.route('/api/pantry', methods=['POST'])
def add_pantry_items():
    data = request.get_json() or {}
    raw_input = data.get('item', '')
    category = data.get('category', 'General')

    if isinstance(raw_input, str):
        # Split by comma or newline
        lines = [x.strip() for line in raw_input.split('\n') for x in line.split(',') if x.strip()]
    elif isinstance(raw_input, list):
        lines = [str(x).strip() for x in raw_input if str(x).strip()]
    else:
        lines = []

    if not lines:
        return jsonify({'error': 'No pantry items provided'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    added_count = 0
    for item_text in lines:
        # Avoid duplicate inserts
        exists = cursor.execute('SELECT id FROM pantry WHERE LOWER(item) = ?', (item_text.lower(),)).fetchone()
        if not exists:
            cursor.execute('INSERT INTO pantry (item, category) VALUES (?, ?)', (item_text, category))
            added_count += 1

    conn.commit()
    conn.close()
    return jsonify({'message': f'Added {added_count} items to pantry'}), 201

@app.route('/api/pantry/<int:item_id>', methods=['DELETE'])
def delete_pantry_item(item_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM pantry WHERE id = ?', (item_id,))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Pantry item deleted'}), 200

@app.route('/api/pantry/clear', methods=['POST'])
def clear_pantry():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM pantry')
    conn.commit()
    conn.close()
    return jsonify({'message': 'Pantry cleared'}), 200

# --- Backup & Restore Endpoints ---

@app.route('/api/backup', methods=['GET'])
def get_backup():
    conn = get_db_connection()
    recipes_db = conn.execute('SELECT * FROM recipes').fetchall()
    planner_db = conn.execute('SELECT * FROM planner').fetchall()
    groceries_db = conn.execute('SELECT * FROM groceries').fetchall()
    stickies_db = conn.execute('SELECT * FROM stickies').fetchall()
    pantry_db = conn.execute('SELECT * FROM pantry').fetchall()
    conn.close()

    backup_data = {
        'version': '1.0',
        'exported_at': datetime.utcnow().isoformat() + 'Z',
        'recipes': [dict(r) for r in recipes_db],
        'planner': [dict(p) for p in planner_db],
        'groceries': [dict(g) for g in groceries_db],
        'stickies': [dict(s) for s in stickies_db],
        'pantry': [dict(pt) for pt in pantry_db]
    }
    return jsonify(backup_data)

@app.route('/api/restore', methods=['POST'])
def restore_backup():
    payload = request.get_json()
    if not payload:
        return jsonify({'error': 'Invalid backup JSON payload'}), 400

    mode = payload.get('mode', 'merge')  # 'merge' or 'replace'
    data = payload.get('data', payload)

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        if mode == 'replace':
            cursor.execute('DELETE FROM recipes')
            cursor.execute('DELETE FROM planner')
            cursor.execute('DELETE FROM groceries')
            cursor.execute('DELETE FROM stickies')
            cursor.execute('DELETE FROM pantry')

        # Restore recipes
        recipes = data.get('recipes', [])
        for r in recipes:
            title = r.get('title', '').strip()
            if not title:
                continue
            if mode == 'merge':
                exists = cursor.execute('SELECT id FROM recipes WHERE LOWER(title) = ?', (title.lower(),)).fetchone()
                if exists:
                    continue
            cursor.execute('''
                INSERT INTO recipes (title, ingredients, instructions, category, is_favorite, prep_time, cook_time, difficulty, servings)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                title,
                r.get('ingredients', ''),
                r.get('instructions', ''),
                r.get('category', 'General'),
                1 if r.get('is_favorite') else 0,
                r.get('prep_time', ''),
                r.get('cook_time', ''),
                r.get('difficulty', 'Easy'),
                r.get('servings', '')
            ))

        # Restore planner
        planner = data.get('planner', [])
        if isinstance(planner, dict):
            # If exported as { "YYYY-MM-DD": { meals, tasks, notes } }
            for date_key, p_data in planner.items():
                meals = p_data.get('meals', {})
                cursor.execute('''
                    INSERT INTO planner (date_key, breakfast, lunch, dinner, tasks, notes)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(date_key) DO UPDATE SET
                        breakfast = excluded.breakfast,
                        lunch = excluded.lunch,
                        dinner = excluded.dinner,
                        tasks = excluded.tasks,
                        notes = excluded.notes
                ''', (
                    date_key,
                    meals.get('breakfast', 'Not planned'),
                    meals.get('lunch', 'Not planned'),
                    meals.get('dinner', 'Not planned'),
                    p_data.get('tasks', ''),
                    p_data.get('notes', '')
                ))
        elif isinstance(planner, list):
            for p in planner:
                date_key = p.get('date_key', '').strip()
                if not date_key:
                    continue
                cursor.execute('''
                    INSERT INTO planner (date_key, breakfast, lunch, dinner, tasks, notes)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(date_key) DO UPDATE SET
                        breakfast = excluded.breakfast,
                        lunch = excluded.lunch,
                        dinner = excluded.dinner,
                        tasks = excluded.tasks,
                        notes = excluded.notes
                ''', (
                    date_key,
                    p.get('breakfast', 'Not planned'),
                    p.get('lunch', 'Not planned'),
                    p.get('dinner', 'Not planned'),
                    p.get('tasks', ''),
                    p.get('notes', '')
                ))

        # Restore groceries
        groceries = data.get('groceries', [])
        for g in groceries:
            item = g.get('item', '').strip()
            if not item:
                continue
            if mode == 'merge':
                exists = cursor.execute('SELECT id FROM groceries WHERE LOWER(item) = ? AND checked = ?', (item.lower(), 1 if g.get('checked') else 0)).fetchone()
                if exists:
                    continue
            cursor.execute('INSERT INTO groceries (item, checked) VALUES (?, ?)', (item, 1 if g.get('checked') else 0))

        # Restore stickies
        stickies = data.get('stickies', [])
        for s in stickies:
            content = s.get('content', '').strip()
            if not content:
                continue
            cursor.execute('INSERT INTO stickies (content, author) VALUES (?, ?)', (content, s.get('author', 'Note')))

        # Restore pantry
        pantry = data.get('pantry', [])
        for pt in pantry:
            item = pt.get('item', '').strip()
            if not item:
                continue
            if mode == 'merge':
                exists = cursor.execute('SELECT id FROM pantry WHERE LOWER(item) = ?', (item.lower(),)).fetchone()
                if exists:
                    continue
            cursor.execute('INSERT INTO pantry (item, category) VALUES (?, ?)', (item, pt.get('category', 'General')))

        conn.commit()
        conn.close()
        return jsonify({'message': f'Backup successfully restored ({mode} mode)'}), 200

    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    # For development only. For production, use Gunicorn/Nginx.
    app.run(host='0.0.0.0', port=5000, debug=True)
