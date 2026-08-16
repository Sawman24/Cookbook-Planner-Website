# Recipe & Daily Planner Web App

A clean virtual Recipe Box and Daily Meal Planner web application with a Flask REST API backend, SQLite persistent database, and Nginx frontend.

---

## 🚀 Features

- **Recipe Box**: Browse, add, search, and delete recipes with real-time SQLite persistence.
- **Daily Planner**: Interactive calendar with meal planning (Breakfast, Lunch, Dinner), daily tasks, and notes.
- **Dark Mode**: Built-in toggle with local preference retention.
- **Dockerized**: Preconfigured with `docker-compose.yml` for single-click deployment via **Portainer** or Docker CLI.
- **Persistent Data**: Database volume ensures recipes and meal plans persist across container updates.

---

## 🐳 Deployment with Portainer

1. Open your **Portainer** web interface.
2. Go to **Stacks** ➡️ **Add stack**.
3. Name your stack (e.g. `recipes-app`).
4. Choose **Repository** or **Web editor**:
   - **Repository option**:
     - Repository URL: `https://github.com/Sawman24/website1`
     - Repository reference: `refs/heads/main`
     - Compose path: `docker-compose.yml`
   - **Web Editor option**: Paste the contents of `docker-compose.yml`.
5. (Optional) Under **Environment variables**, set `PORT=5050` (or your preferred host port).
6. Click **Deploy the stack**.
7. Access your website at `http://<your-server-ip>:5050`.

---

## 💻 Local Deployment with Docker Compose

```bash
# Clone the repository
git clone https://github.com/Sawman24/website1.git
cd website1

# Start the stack
docker compose up -d --build
```

Access the app in your browser at `http://localhost:5050`.

---

## 📁 Project Structure

```text
├── docker-compose.yml          # Portainer / Docker Compose stack
├── nginx/
│   └── default.conf            # Nginx reverse proxy configuration
├── recipe_api/
│   ├── app.py                  # Flask API with recipes & planner CRUD
│   ├── Dockerfile              # Python 3.11 backend container
│   ├── requirements.txt        # Backend dependencies (Flask, CORS, Gunicorn)
│   └── recipes.db              # Bundled SQLite database with starter recipes
└── www/
    └── html/
        ├── index.html          # Homepage with upcoming meal previews
        ├── recipes.html        # Recipe management & search
        └── planner.html        # Monthly calendar meal planner
```
