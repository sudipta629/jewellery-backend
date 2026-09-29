import os
from dotenv import load_dotenv
from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token
from datetime import timedelta

load_dotenv()

app = Flask(__name__)
app.config["JWT_SECRET_KEY"] = os.environ.get("JWT_SECRET_KEY", "dev-jwt-secret-change-me-in-production")
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(days=365) # 1 year expiration
jwt = JWTManager(app)

with app.app_context():
    # Admin user id usually 1
    token = create_access_token(identity="1", additional_claims={"role": "super_admin"})
    print("TOKEN:", token)
