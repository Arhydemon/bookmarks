# подключаем datetime для даты регистрации и даты добавления ссылок
from datetime import datetime

# подключаем базу и constraints
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import UniqueConstraint

# для flask-login нужно, чтобы user был “примешан” к UserMixin
from flask_login import UserMixin

db = SQLAlchemy()

# таблица связи многие-ко-многим между ссылками и тегами
link_tags = db.Table(
    "link_tags",
    db.Column("link_id", db.Integer, db.ForeignKey("links.id"), primary_key=True),
    db.Column("tag_id", db.Integer, db.ForeignKey("tags.id"), primary_key=True),
)


# модель пользователя
class User(db.Model, UserMixin):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)

    # логин пользователя (уникальный)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)

    # тут хранится хеш пароля, а не сам пароль
    password_hash = db.Column(db.String(255), nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


# модель категории (у каждого пользователя свой набор категорий)
class Category(db.Model):
    __tablename__ = "categories"

    id = db.Column(db.Integer, primary_key=True)

    # владелец категории
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)

    name = db.Column(db.String(120), nullable=False)

    # запрет одинаковых категорий у одного пользователя
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_categories_user_name"),
    )

    # связь: одна категория -> много ссылок
    links = db.relationship("Link", back_populates="category")


# модель тега (у каждого пользователя свой набор тегов)
class Tag(db.Model):
    __tablename__ = "tags"

    id = db.Column(db.Integer, primary_key=True)

    # владелец тега
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)

    name = db.Column(db.String(80), nullable=False, index=True)

    # запрет одинаковых тегов у одного пользователя
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_tags_user_name"),
    )


# модель ссылки (у каждой ссылки есть владелец)
class Link(db.Model):
    __tablename__ = "links"

    id = db.Column(db.Integer, primary_key=True)

    # владелец ссылки
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)

    url = db.Column(db.String(2048), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # категория ровно одна (или пусто), но принадлежит тому же user
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"), nullable=True)
    category = db.relationship("Category", back_populates="links")

    # теги много
    tags = db.relationship("Tag", secondary=link_tags, lazy="subquery")

    icon = db.Column(db.String(80), nullable=True)