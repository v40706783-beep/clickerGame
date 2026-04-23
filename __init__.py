from flask import Flask, render_template, request, redirect, flash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from flask_login import UserMixin, LoginManager, login_user, login_required, logout_user, current_user
from werkzeug.security import check_password_hash, generate_password_hash

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
    money = db.Column(db.Float)
    total_earned = db.Column(db.Float)
    rebirths = db.Column(db.Integer)
    click_level = db.Column(db.Integer)
    passive_level = db.Column(db.Integer)


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

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run()
