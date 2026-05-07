from flask import Flask, render_template, request, redirect, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from flask_login import UserMixin, LoginManager, login_user, login_required, logout_user, current_user
from werkzeug.security import check_password_hash, generate_password_hash
import json
from sqlalchemy import inspect, text
import requests as http_requests

# AI config (из main.py)
AI_API_KEY = "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"  
AI_URL = "https://openrouter.ai/api/v1/chat/completions"
AI_MODEL = "openrouter/free"
AI_SYSTEM_PROMPT = """Ты — внутриигровой ИИ-ассистент Alchemy Clicker.

Ты знаешь все механики текущей версии игры и отвечаешь как игровой консультант.

Ключевые механики:
1) Ресурс:
- Основной ресурс: алхимическая эссенция.
- Эссенция растёт от кликов по котлу и от пассивного дохода.

2) Клики:
- Базовый доход клика начинается с 1.
- Формула клика: baseClickGain * clickMultiplier * incomeMultiplier.

3) Алхимический жар (комбо):
- Каждые 10 кликов дают +0.1 к временному множителю.
- Временный множитель ограничен максимумом x3.
- Жар влияет и на клик, и на пассивный доход.

4) Перерождение:
- Стоимость: 5000 * (1 + rebirthCount * 0.75), округляется вниз.
- При перерождении сбрасываются эссенция, комбо и уровни улучшений.
- Количество перерождений увеличивается на 1.
- Постоянный множитель дохода: incomeMultiplier = 1 + rebirthCount.

5) Улучшения (4 вида):
- 🌿 Травник: +0.6 к силе клика за уровень.
- 🧪 Гомункул-помощник: +0.25 эссенции/сек за уровень.
- 🔮 Философский камень: +0.06 к постоянному множителю клика за уровень.
- 🕯️ Эссенциальный алтарь: +0.5 эссенции/сек за уровень.
- Цена улучшения растёт с уровнем: floor(basePrice * (1 + level * 0.95)).

6) Сохранение:
- У авторизованных: сохранение на сервер.
- Без авторизации: сохранение в localStorage.
- Есть автосохранение.

7) Лидерборд:
- Режим "Всего заработано" (totalEarned).
- Режим "Сейчас" (текущая эссенция).

Правила ответов:
- Отвечай кратко, понятно, по делу.
- Если вопрос про стратегию, давай 2-4 практичных совета с приоритетом.
- Если есть контекст состояния игрока, учитывай его в ответе.
- Не выдумывай несуществующие механики или кнопки.
- Если вопрос не про игру, вежливо объясни, что ты консультант только по Alchemy Clicker."""


def _offline_ai_answer(user_text, game_context):
    text = (user_text or "").lower()
    essence = float(game_context.get("essence", 0) or 0)
    rebirth = int(game_context.get("rebirthCount", 0) or 0)
    eps = float(game_context.get("eps", 0) or 0)
    click_mult = float(game_context.get("clickMultiplier", 1) or 1)

    if any(word in text for word in ["привет", "здрав", "hello", "hi"]):
        return "Привет! Я помогу по механикам Alchemy Clicker: клики, улучшения, перерождение и лидерборд."

    if "перерожд" in text:
        cost = int(5000 * (1 + rebirth * 0.75))
        if essence >= cost:
            return f"Ты уже можешь переродиться: нужно {cost} эссенции, у тебя {essence:.1f}. Перерождение сбросит прогресс улучшений, но повысит доходный множитель."
        return f"До перерождения нужно {cost} эссенции. Сейчас у тебя {essence:.1f}. Сначала усили пассивный доход и докачай клик."

    if any(word in text for word in ["улучш", "качать", "что купить", "стратег"]):
        return (
            "Оптимальная база: 1) возьми несколько уровней Травника для разгона клика, "
            "2) затем качай Гомункула и Алтарь для стабильного пассивного дохода, "
            "3) Философский камень усиливает общий клик-множитель и хорошо скейлится в мидгейме."
        )

    if any(word in text for word in ["жар", "комбо", "множител"]):
        return "Алхимический жар растет на +0.1 каждые 10 кликов и ограничен x3. Он усиливает и клики, и эссенцию в секунду."

    if any(word in text for word in ["сохран", "пропал прогресс"]):
        return "Сохранение работает так: с аккаунтом прогресс пишется на сервер, без аккаунта — в localStorage браузера. Также есть автосохранение."

    if any(word in text for word in ["лидер", "топ"]):
        return "В таблице лидеров есть 2 режима: по общему заработку и по текущей эссенции. Для участия нужен аккаунт."

    return (
        f"Сейчас у тебя {essence:.1f} эссенции, {eps:.1f}/сек, множитель клика x{click_mult:.2f}, перерождений: {rebirth}. "
        "Могу подсказать, что выгоднее купить следующим шагом."
    )

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

@app.route('/leaderboard')
def leaderboard():
    from flask import jsonify, request as req
    mode = req.args.get('mode', 'total')
    if mode == 'current':
        states = db.session.query(game_state, User).join(User, game_state.user_id == User.id)\
            .order_by(game_state.money.desc()).limit(100).all()
        players = [{"rank": i+1, "username": u.username, "value": round(gs.money or 0, 1)} for i, (gs, u) in enumerate(states)]
    else:
        states = db.session.query(game_state, User).join(User, game_state.user_id == User.id)\
            .order_by(game_state.total_earned.desc()).limit(100).all()
        players = [{"rank": i+1, "username": u.username, "value": round(gs.total_earned or 0, 1)} for i, (gs, u) in enumerate(states)]
    return jsonify(players)

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

@app.route('/save_game', methods=['POST'])
def save_game():
    if not current_user.is_authenticated:
        return jsonify({'ok': False}), 401
    data = request.get_json(force=True, silent=True) or {}
    state = game_state.query.filter_by(user_id=current_user.id).first()
    if not state:
        state = game_state(user_id=current_user.id)
        db.session.add(state)
    state.money = float(data.get('essence', 0))
    state.total_earned = float(data.get('totalEarned', 0))
    state.rebirths = int(data.get('rebirthCount', 0))
    state.click_combo = int(data.get('clickComboCounter', 0))
    state.upgrades_json = json.dumps(data.get('upgrades', []))
    db.session.commit()
    return jsonify({'ok': True})

@app.route('/load_game')
def load_game():
    if not current_user.is_authenticated:
        return jsonify({}), 401
    state = game_state.query.filter_by(user_id=current_user.id).first()
    if not state:
        return jsonify(_default_game_state())
    return jsonify(_serialize_game_state(state))
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

@app.route('/api/ai-chat', methods=['POST'])
def ai_chat():
    data = request.get_json(silent=True) or {}
    messages = data.get('messages', [])
    game_context = data.get('context', {})
    if not isinstance(messages, list) or not messages:
        return jsonify({'error': 'no messages'}), 400

    sanitized = []
    for msg in messages[-10:]:
        role = msg.get("role")
        content = msg.get("content", "")
        if role not in {"user", "assistant"}:
            continue
        sanitized.append({"role": role, "content": str(content)})

    context_text = (
        f"Текущее состояние игрока: essence={game_context.get('essence', 0)}, "
        f"eps={game_context.get('eps', 0)}, clickMultiplier={game_context.get('clickMultiplier', 1)}, "
        f"rebirthCount={game_context.get('rebirthCount', 0)}, totalEarned={game_context.get('totalEarned', 0)}."
    )
    full_messages = [
        {"role": "system", "content": AI_SYSTEM_PROMPT},
        {"role": "system", "content": context_text}
    ] + sanitized

    # Fallback режим: ассистент остается доступным даже без внешнего AI API.
    if not AI_API_KEY.strip():
        last_user = ""
        for msg in reversed(sanitized):
            if msg["role"] == "user":
                last_user = msg["content"]
                break
        return jsonify({'answer': _offline_ai_answer(last_user, game_context if isinstance(game_context, dict) else {})})

    try:
        resp = http_requests.post(
            AI_URL,
            headers={"Authorization": f"Bearer {AI_API_KEY}", "Content-Type": "application/json"},
            json={"model": AI_MODEL, "messages": full_messages},
            timeout=30
        )
        if resp.status_code != 200:
            return jsonify({'error': resp.text}), 502
        answer = resp.json()["choices"][0]["message"]["content"]
        return jsonify({'answer': answer})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        _ensure_game_state_columns()
        _cleanup_game_state_columns()
    app.run()
