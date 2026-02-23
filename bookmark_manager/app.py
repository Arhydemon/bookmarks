import csv
import io
import json

from flask import Flask, render_template, request, redirect, url_for, flash, Response, abort
from sqlalchemy import or_, func
from werkzeug.security import generate_password_hash, check_password_hash

from flask_login import (
    LoginManager,
    login_user,
    logout_user,
    login_required,
    current_user,
)

from models import db, User, Link, Category, Tag
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# подгружаем .env
load_dotenv()

# секретный ключ для сессий (логин/куки)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev_secret")

# делаем абсолютный путь к instance/bookmarks.db
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
INSTANCE_DIR = os.path.join(BASE_DIR, "instance")
os.makedirs(INSTANCE_DIR, exist_ok=True)

DB_PATH = os.path.join(INSTANCE_DIR, "bookmarks.db")
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + DB_PATH

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)

# настраиваем login manager
login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.init_app(app)

with app.app_context():
    db.create_all()

# набор значков, которые можно выбрать в форме
ICON_OPTIONS = [
    ("", "без значка"),
    ("bi bi-bookmark", "закладка"),
    ("bi bi-globe", "сайт"),
    ("bi bi-youtube", "youtube"),
    ("bi bi-play-circle", "видео"),
    ("bi bi-file-earmark-text", "текст/статья"),
    ("bi bi-music-note-beamed", "музыка"),
    ("bi bi-code-slash", "код"),
    ("bi bi-mortarboard", "обучение"),
    ("bi bi-star", "звезда"),
    ("bi bi-heart", "сердце"),
    ("bi bi-link-45deg", "ссылка"),
]
ALLOWED_ICONS = {x[0] for x in ICON_OPTIONS}

@login_manager.user_loader
def load_user(user_id: str):
    # flask-login будет грузить пользователя по id
    try:
        uid = int(user_id)
    except ValueError:
        return None
    return User.query.get(uid)


def normalize_tag_name(name: str) -> str:
    # приводим тег к нижнему регистру, чтобы не было дублей по регистру
    name = (name or "").strip()
    if name.startswith("#"):
        name = name[1:]
    name = name.strip()

    # убираем мусор на конце
    while name.endswith((",", ".", ";", ":")):
        name = name[:-1].strip()

    return name.lower()


def parse_tags_input(raw: str) -> list[str]:
    # поддерживаем форматы:
    # "#react #frontend" или "react, frontend" или "react frontend"
    if not raw:
        return []
    raw = raw.replace(",", " ")
    parts = [p.strip() for p in raw.split() if p.strip()]

    names = []
    for p in parts:
        n = normalize_tag_name(p)
        if n:
            names.append(n)

    # убираем дубли
    seen = set()
    result = []
    for n in names:
        if n not in seen:
            result.append(n)
            seen.add(n)
    return result


def get_or_create_tags_for_user(tag_names: list[str], user_id: int) -> list[Tag]:
    # создаём/находим теги строго в рамках текущего пользователя
    tags: list[Tag] = []

    normalized = []
    for name in tag_names:
        n = normalize_tag_name(name)
        if n:
            normalized.append(n)

    with db.session.no_autoflush:
        for name in normalized:
            existing = Tag.query.filter_by(user_id=user_id, name=name).first()
            if existing:
                tags.append(existing)
            else:
                t = Tag(user_id=user_id, name=name)
                db.session.add(t)
                tags.append(t)

    # делаем flush, чтобы ловить ошибки тут, а не в неожиданный момент
    try:
        db.session.flush()
    except Exception:
        # если вдруг конфликт уникальности, перезагружаем
        db.session.rollback()
        tags = []
        with db.session.no_autoflush:
            for name in normalized:
                existing = Tag.query.filter_by(user_id=user_id, name=name).first()
                if existing:
                    tags.append(existing)
                else:
                    t = Tag(user_id=user_id, name=name)
                    db.session.add(t)
                    tags.append(t)
        db.session.flush()

    return tags


def get_user_category_or_none(category_id_raw: str | None, user_id: int):
    # берём категорию только если она принадлежит пользователю
    if not category_id_raw:
        return None
    try:
        cid = int(category_id_raw)
    except ValueError:
        return None
    return Category.query.filter_by(id=cid, user_id=user_id).first()


@app.get("/")
def index():
    # если пользователь залогинен, показываем ссылки, иначе на login
    if current_user.is_authenticated:
        return redirect(url_for("links_list"))
    return redirect(url_for("login"))


# регистрация
@app.get("/register")
def register():
    if current_user.is_authenticated:
        return redirect(url_for("links_list"))
    return render_template("register.html")


@app.post("/register")
def register_post():
    if current_user.is_authenticated:
        return redirect(url_for("links_list"))

    username = (request.form.get("username") or "").strip()
    password = request.form.get("password") or ""
    password2 = request.form.get("password2") or ""

    if not username or not password:
        flash("логин и пароль обязательны", "danger")
        return redirect(url_for("register"))

    if password != password2:
        flash("пароли не совпадают", "danger")
        return redirect(url_for("register"))

    # проверяем уникальность логина
    exists = User.query.filter(func.lower(User.username) == username.lower()).first()
    if exists:
        flash("такой логин уже занят", "warning")
        return redirect(url_for("register"))

    # сохраняем хеш пароля
    user = User(
        username=username,
        password_hash=generate_password_hash(password),
    )
    db.session.add(user)
    db.session.commit()

    flash("аккаунт создан, теперь войди", "success")
    return redirect(url_for("login"))


# вход
@app.get("/login")
def login():
    if current_user.is_authenticated:
        return redirect(url_for("links_list"))
    return render_template("login.html")


@app.post("/login")
def login_post():
    if current_user.is_authenticated:
        return redirect(url_for("links_list"))

    username = (request.form.get("username") or "").strip()
    password = request.form.get("password") or ""

    if not username or not password:
        flash("логин и пароль обязательны", "danger")
        return redirect(url_for("login"))

    user = User.query.filter(func.lower(User.username) == username.lower()).first()
    if not user:
        flash("неверный логин или пароль", "danger")
        return redirect(url_for("login"))

    if not check_password_hash(user.password_hash, password):
        flash("неверный логин или пароль", "danger")
        return redirect(url_for("login"))

    login_user(user)
    return redirect(url_for("links_list"))


# выход
@app.get("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


# список ссылок
@app.get("/links")
@login_required
def links_list():
    q = (request.args.get("q") or "").strip()
    category_id = (request.args.get("category_id") or "").strip()
    tags_param = (request.args.get("tags") or "").strip()

    query = Link.query.filter_by(user_id=current_user.id)

    # поиск
    if q:
        like = f"%{q}%"
        query = query.filter(or_(Link.title.ilike(like), Link.description.ilike(like)))

    # категория (только своя)
    selected_category = None
    if category_id:
        try:
            cid = int(category_id)
            selected_category = Category.query.filter_by(id=cid, user_id=current_user.id).first()
            if selected_category:
                query = query.filter(Link.category_id == cid)
            else:
                query = query.filter(False)
        except ValueError:
            pass

    # теги (and логика)
    selected_tags: list[Tag] = []
    if tags_param:
        raw_names = [normalize_tag_name(x) for x in tags_param.split(",") if normalize_tag_name(x)]
        for name in raw_names:
            t = Tag.query.filter_by(user_id=current_user.id, name=name).first()
            if t:
                selected_tags.append(t)
                query = query.filter(Link.tags.any(Tag.id == t.id))
            else:
                query = query.filter(False)

    links = query.order_by(Link.created_at.desc()).all()

    categories = Category.query.filter_by(user_id=current_user.id).order_by(Category.name.asc()).all()
    tags = Tag.query.filter_by(user_id=current_user.id).order_by(Tag.name.asc()).all()

    return render_template(
        "links_list.html",
        links=links,
        categories=categories,
        tags=tags,
        q=q,
        tags_param=tags_param,
        selected_category=selected_category,
        selected_tags=selected_tags,
    )


# создание ссылки
@app.get("/links/new")
@login_required
def link_new_form():
    categories = Category.query.filter_by(user_id=current_user.id).order_by(Category.name.asc()).all()
    return render_template(
    "link_form.html",
    link=None,
    categories=categories,
    tag_string="",
    icon_options=ICON_OPTIONS,
    )


@app.post("/links/new")
@login_required
def link_create():
    url = (request.form.get("url") or "").strip()
    title = (request.form.get("title") or "").strip()
    description = (request.form.get("description") or "").strip() or None
    category_id_raw = (request.form.get("category_id") or "").strip()
    tags_raw = request.form.get("tags") or ""
    icon = (request.form.get("icon") or "").strip()
    if icon not in ALLOWED_ICONS:
        icon = ""

    if not url or not title:
        flash("url и название обязательны", "danger")
        return redirect(url_for("link_new_form"))

    category = get_user_category_or_none(category_id_raw, current_user.id)

    tag_names = parse_tags_input(tags_raw)
    tags = get_or_create_tags_for_user(tag_names, current_user.id)

    link = Link(
        user_id=current_user.id,
        url=url,
        title=title,
        description=description,
        category=category,
        tags=tags,
        icon=icon or None,

    )
    db.session.add(link)
    db.session.commit()

    flash("ссылка добавлена", "success")
    return redirect(url_for("links_list"))


# редактирование ссылки
@app.get("/links/<int:link_id>/edit")
@login_required
def link_edit_form(link_id: int):
    link = Link.query.filter_by(id=link_id, user_id=current_user.id).first()
    if not link:
        abort(404)

    categories = Category.query.filter_by(user_id=current_user.id).order_by(Category.name.asc()).all()
    tag_string = " ".join([f"#{t.name}" for t in link.tags])

    return render_template(
    "link_form.html",
    link=link,
    categories=categories,
    tag_string=tag_string,
    icon_options=ICON_OPTIONS,
    )


@app.post("/links/<int:link_id>/edit")
@login_required
def link_update(link_id: int):
    link = Link.query.filter_by(id=link_id, user_id=current_user.id).first()
    if not link:
        abort(404)
    
    url = (request.form.get("url") or "").strip()
    title = (request.form.get("title") or "").strip()
    description = (request.form.get("description") or "").strip() or None
    category_id_raw = (request.form.get("category_id") or "").strip()
    tags_raw = request.form.get("tags") or ""

    if not url or not title:
        flash("url и название обязательны", "danger")
        return redirect(url_for("link_edit_form", link_id=link.id))

    category = get_user_category_or_none(category_id_raw, current_user.id)
    icon = (request.form.get("icon") or "").strip()
    if icon not in ALLOWED_ICONS:
        icon = ""

    link.icon = icon or None
    tag_names = parse_tags_input(tags_raw)
    tags = get_or_create_tags_for_user(tag_names, current_user.id)

    link.url = url
    link.title = title
    link.description = description
    link.category = category
    link.tags = tags

    db.session.commit()
    flash("ссылка обновлена", "success")
    return redirect(url_for("links_list"))


@app.post("/links/<int:link_id>/delete")
@login_required
def link_delete(link_id: int):
    link = Link.query.filter_by(id=link_id, user_id=current_user.id).first()
    if not link:
        abort(404)

    db.session.delete(link)
    db.session.commit()
    flash("ссылка удалена", "success")
    return redirect(url_for("links_list"))


# категории
@app.get("/categories")
@login_required
def categories_page():
    categories = Category.query.filter_by(user_id=current_user.id).order_by(Category.name.asc()).all()
    return render_template("categories.html", categories=categories)


@app.post("/categories/new")
@login_required
def category_create():
    name = (request.form.get("name") or "").strip()
    if not name:
        flash("название категории обязательно", "danger")
        return redirect(url_for("categories_page"))

    # делаем уникальность внутри пользователя
    exists = Category.query.filter(
        Category.user_id == current_user.id,
        func.lower(Category.name) == name.lower()
    ).first()
    if exists:
        flash("такая категория уже есть", "warning")
        return redirect(url_for("categories_page"))

    db.session.add(Category(user_id=current_user.id, name=name))
    db.session.commit()
    flash("категория создана", "success")
    return redirect(url_for("categories_page"))


@app.post("/categories/<int:category_id>/rename")
@login_required
def category_rename(category_id: int):
    cat = Category.query.filter_by(id=category_id, user_id=current_user.id).first()
    if not cat:
        abort(404)

    new_name = (request.form.get("name") or "").strip()
    if not new_name:
        flash("новое имя обязательно", "danger")
        return redirect(url_for("categories_page"))

    exists = Category.query.filter(
        Category.user_id == current_user.id,
        func.lower(Category.name) == new_name.lower(),
        Category.id != cat.id
    ).first()
    if exists:
        flash("категория с таким именем уже есть", "warning")
        return redirect(url_for("categories_page"))

    cat.name = new_name
    db.session.commit()
    flash("категория переименована", "success")
    return redirect(url_for("categories_page"))


@app.post("/categories/<int:category_id>/delete")
@login_required
def category_delete(category_id: int):
    cat = Category.query.filter_by(id=category_id, user_id=current_user.id).first()
    if not cat:
        abort(404)

    # сбрасываем category у ссылок пользователя
    for link in Link.query.filter_by(user_id=current_user.id, category_id=cat.id).all():
        link.category_id = None

    db.session.delete(cat)
    db.session.commit()
    flash("категория удалена (у ссылок категория сброшена)", "success")
    return redirect(url_for("categories_page"))


# теги
@app.get("/tags")
@login_required
def tags_page():
    tags = Tag.query.filter_by(user_id=current_user.id).order_by(Tag.name.asc()).all()

    tag_counts = {}
    for t in tags:
        tag_counts[t.id] = Link.query.filter(
            Link.user_id == current_user.id,
            Link.tags.any(Tag.id == t.id)
        ).count()

    return render_template("tags.html", tags=tags, tag_counts=tag_counts)


@app.post("/tags/<int:tag_id>/delete")
@login_required
def tag_delete(tag_id: int):
    tag = Tag.query.filter_by(id=tag_id, user_id=current_user.id).first()
    if not tag:
        abort(404)

    links = Link.query.filter(Link.user_id == current_user.id, Link.tags.any(Tag.id == tag.id)).all()
    for link in links:
        link.tags = [t for t in link.tags if t.id != tag.id]

    db.session.delete(tag)
    db.session.commit()
    flash("тег удалён", "success")
    return redirect(url_for("tags_page"))


@app.post("/tags/merge")
@login_required
def tag_merge():
    source_name = normalize_tag_name(request.form.get("source") or "")
    target_name = normalize_tag_name(request.form.get("target") or "")

    if not source_name or not target_name:
        flash("нужно указать source и target", "danger")
        return redirect(url_for("tags_page"))

    if source_name == target_name:
        flash("source и target должны отличаться", "warning")
        return redirect(url_for("tags_page"))

    source = Tag.query.filter_by(user_id=current_user.id, name=source_name).first()
    if not source:
        flash("source-тег не найден", "danger")
        return redirect(url_for("tags_page"))

    target = Tag.query.filter_by(user_id=current_user.id, name=target_name).first()
    if not target:
        target = Tag(user_id=current_user.id, name=target_name)
        db.session.add(target)
        db.session.flush()

    links = Link.query.filter(Link.user_id == current_user.id, Link.tags.any(Tag.id == source.id)).all()
    for link in links:
        has_target = any(t.id == target.id for t in link.tags)
        if not has_target:
            link.tags.append(target)
        link.tags = [t for t in link.tags if t.id != source.id]

    db.session.delete(source)
    db.session.commit()

    flash("теги объединены", "success")
    return redirect(url_for("tags_page"))


# экспорт (только свои данные)
@app.get("/export/json")
@login_required
def export_json():
    links = Link.query.filter_by(user_id=current_user.id).order_by(Link.created_at.desc()).all()

    data = []
    for l in links:
        data.append({
            "id": l.id,
            "url": l.url,
            "title": l.title,
            "description": l.description,
            "created_at": l.created_at.isoformat(),
            "category": l.category.name if l.category else None,
            "tags": [t.name for t in l.tags],
        })

    return Response(
        json.dumps(data, ensure_ascii=False, indent=2),
        mimetype="application/json; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=bookmarks.json"}
    )


@app.get("/export/csv")
@login_required
def export_csv():
    links = Link.query.filter_by(user_id=current_user.id).order_by(Link.created_at.desc()).all()

    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["id", "url", "title", "description", "created_at", "category", "tags"])

    for l in links:
        writer.writerow([
            l.id,
            l.url,
            l.title,
            l.description or "",
            l.created_at.isoformat(),
            l.category.name if l.category else "",
            ",".join([t.name for t in l.tags]),
        ])

    return Response(
        out.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=bookmarks.csv"}
    )


if __name__ == "__main__":
    app.run()