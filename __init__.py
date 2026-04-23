from flask import Flask, render_template, request, redirect, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from flask_login import UserMixin, LoginManager, login_user, login_required, logout_user, current_user
from werkzeug.security import check_password_hash, generate_password_hash
import json
from sqlalchemy import inspect, text

app = Flask(__name__)
app.secret_key = 'alchemy-secret-key-change-me'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///main.db'
db = SQLAlchemy(app)
manager = LoginManager(app)
manager.login_view = 'login'
manager.login_message = 'Необходимо войти в аккаунт'
manager.login_message_category = 'warning'

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String, unique=True)
    password = db.Column(db.String)
    admin = db.Column(db.Boolean, default=False)

    def __init__(self, username, password):
        self.username = username
        self.password = password

    def __str__(self):
        return f"ID: {self.id}, Логин: {self.username}"

class game_state(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, unique=True)
    money = db.Column(db.Float, default=0.0)
    total_earned = db.Column(db.Float, default=0.0)
    rebirths = db.Column(db.Integer, default=0)
    click_combo = db.Column(db.Integer, default=0)
    upgrades_json = db.Column(db.Text, default='[]')
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


def _default_game_state():
    return {
        "essence": 0.0,
        "totalEarned": 0.0,
        "clickComboCounter": 0,
        "rebirthCount": 0,
        "upgrades": [],
        "version": 1
    }


def _serialize_game_state(state):
    try:
        upgrades = json.loads(state.upgrades_json or "[]")
    except (ValueError, TypeError):
        upgrades = []
    return {
        "essence": float(state.money or 0.0),
        "totalEarned": float(state.total_earned or 0.0),
        "clickComboCounter": int(state.click_combo or 0),
        "rebirthCount": int(state.rebirths or 0),
        "upgrades": upgrades,
        "version": 1
    }


def _ensure_game_state_columns():
    inspector = inspect(db.engine)
    if "game_state" not in inspector.get_table_names():
        return

    existing_columns = {col["name"] for col in inspector.get_columns("game_state")}
    required_columns = {
        "click_combo": "INTEGER DEFAULT 0",
        "upgrades_json": "TEXT DEFAULT '[]'",
        "updated_at": "DATETIME"
    }

    for col_name, col_type in required_columns.items():
        if col_name not in existing_columns:
            db.session.execute(text(f"ALTER TABLE game_state ADD COLUMN {col_name} {col_type}"))
    db.session.commit()


def _cleanup_game_state_columns():
    inspector = inspect(db.engine)
    if "game_state" not in inspector.get_table_names():
        return

    existing_columns = {col["name"] for col in inspector.get_columns("game_state")}
    obsolete_columns = ["click_level", "passive_level"]

    for col_name in obsolete_columns:
        if col_name in existing_columns:
            try:
                db.session.execute(text(f"ALTER TABLE game_state DROP COLUMN {col_name}"))
                db.session.commit()
            except Exception:
                db.session.rollback()


@manager.user_loader
def load_user(user_id):
    return db.session.get(User, user_id)


@app.route('/')
def index():
    return render_template("index.html")

@app.route('/login', methods=["POST", "GET"])
def login():
    if request.method == "GET":
        if current_user.is_authenticated:
            flash("Вы уже авторизованы", 'warning')
            return redirect("/")
        return render_template("login.html")
    username = request.form.get('username')
    password = request.form.get('password')
    user = User.query.filter_by(username=username).first()
    if user is None:
        flash('Такого пользователя не существует', 'danger')
        return redirect("/login")
    if check_password_hash(user.password, password):
        login_user(user)
        return redirect('/')
    flash("Неверный логин или пароль!", 'danger')
    return render_template("login.html")

@app.route('/register', methods=["POST", "GET"])
def register():
    if request.method == "GET":
        if current_user.is_authenticated:
            flash("Вы уже авторизованы", 'warning')
            return redirect("/")
        return render_template("register.html")
    username = request.form.get('username')
    password = request.form.get('password')
    if not username or not password:
        flash("Заполните все поля", 'danger')
        return redirect("/register")
    if User.query.filter_by(username=username).first():
        flash("Пользователь с таким логином уже существует", 'danger')
        return redirect("/register")
    user = User(username=username, password=generate_password_hash(password))
    db.session.add(user)
    db.session.commit()
    login_user(user)
    flash("Регистрация прошла успешно!", 'success')
    return redirect('/')

@app.route('/logout')
def logout():
    logout_user()
    return redirect("/")


@app.route('/api/game-state', methods=['GET'])
@login_required
def get_game_state():
    state = game_state.query.filter_by(user_id=current_user.id).first()
    if not state:
        return jsonify(_default_game_state())
    return jsonify(_serialize_game_state(state))


@app.route('/api/game-state', methods=['POST'])
@login_required
def save_game_state():
    data = request.get_json(silent=True) or {}

    essence = float(data.get("essence", 0.0))
    raw_total_earned = data.get("totalEarned")
    click_combo = int(data.get("clickComboCounter", 0))
    rebirth_count = int(data.get("rebirthCount", 0))
    upgrades = data.get("upgrades", [])

    if not isinstance(upgrades, list):
        return jsonify({"ok": False, "error": "invalid_upgrades"}), 400

    state = game_state.query.filter_by(user_id=current_user.id).first()
    if not state:
        state = game_state(user_id=current_user.id)
        db.session.add(state)

    state.money = max(0.0, essence)
    # Backward compatibility: do not erase total_earned for old clients
    # that still send saves without totalEarned.
    if raw_total_earned is not None:
        state.total_earned = max(0.0, float(raw_total_earned))
    state.click_combo = max(0, click_combo)
    state.rebirths = max(0, rebirth_count)
    state.upgrades_json = json.dumps(upgrades)
    state.updated_at = datetime.utcnow()
    db.session.commit()

    return jsonify({"ok": True})

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        _ensure_game_state_columns()
        _cleanup_game_state_columns()
    app.run()
