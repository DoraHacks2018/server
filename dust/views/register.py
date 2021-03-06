import ast
import binascii
from datetime import datetime
import os
from flask import Blueprint, current_app, request
from flask.views import MethodView
from ..core import db, logger, oauth_client, redis_store
from ..forms.register import UserRegisterForm
from ..exceptions import FormValidationError, RegisterError, DuplicateGithubUser, RegisterFailError
from ..models.user_planet import User, Notification
from ..constants import Notify, NotifyContent

bp = Blueprint('register', __name__)


class RegisterView(MethodView):
    def post(self):
        form = UserRegisterForm()
        if form.validate():
            user = form.save()
            return user.todict()
        else:
            raise FormValidationError(form)


class RegisterAuthGithub(MethodView):
    def post(self):
        code = request.get_json().get('code')
        resp = oauth_client.get_token(code)
        access_token = resp.json().get('access_token')
        if not access_token:
            raise RegisterError()
        oauth_client.set_token(access_token)
        user_info = oauth_client.user().json()
        u1 = User.get_by_username(user_info.get('login'))
        if u1:
            raise DuplicateGithubUser()
        u = User(username=user_info.get('login'))
        u.git_account = user_info.get('login')
        u.github_link = user_info.get('html_url')
        u.avatar = user_info.get('avatar_url')
        db.session.add(u)
        db.session.flush()
        auth_token = binascii.hexlify(os.urandom(16)).decode()  # noqa
        redis_store.hmset(auth_token, dict(
            id=u.id,
            created_at=datetime.now(),
        ))
        expires_in = current_app.config.get('LOGIN_EXPIRE_TIME', 7200*12)  # expire in 1 day
        redis_store.expire(auth_token, expires_in)
        # n = Notification(type=Notify.BUILD, uid=u.id)
        # db.session.add(n)
        # redis_store.set("%s:build_times" % u.id, 3, ex=expires_in)
        # n.content = NotifyContent.get(Notify.BUILD).format('3')
        db.session.commit()
        return dict(auth_token=auth_token, expires_in=expires_in, user_info=u.todict())


class ClaimGithub(MethodView):
    def post(self):
        code = request.get_json().get('code')
        author_login = request.get_json().get('author_login')
        resp = oauth_client.get_token(code)
        access_token = resp.json().get('access_token')
        if not access_token:
            raise RegisterError()
        oauth_client.set_token(access_token)
        user_info = oauth_client.user().json()
        u1 = User.get_by_username(user_info.get('login'))
        if u1:
            raise DuplicateGithubUser()
        pass


class RegisterKCash(MethodView):
    def post(self):
        code = request.get_json().get('code')
        kcash_addr = request.get_json().get('addr')
        invite = request.get_json().get('invite')
        resp = oauth_client.get_token(code)
        access_token = resp.json().get('access_token')
        if not access_token:
            raise RegisterError()
        oauth_client.set_token(access_token)
        user_info = oauth_client.user().json()
        u1 = User.get_by_username(user_info.get('login'))
        if u1:
            raise DuplicateGithubUser()
        u = User(username=user_info.get('login'))
        u.git_account = user_info.get('login')
        u.github_link = user_info.get('html_url')
        u.gift_addr = kcash_addr
        u.invitation_code = invite
        db.session.add(u)
        db.session.flush()
        u.owned_dust += 50
        resp = oauth_client.star('truechain', 'truechain-consensus-core')
        resp.raise_for_status()
        r2 = oauth_client.check_star('truechain', 'truechain-consensus-core')
        r2.raise_for_status()
        if not resp.ok:
            logger.debug('### star resp.headers', resp.headers)
            raise RegisterFailError()
        auth_token = binascii.hexlify(os.urandom(16)).decode()  # noqa
        redis_store.hmset(auth_token, dict(
            id=u.id,
            created_at=datetime.now(),
        ))
        expires_in = current_app.config.get('LOGIN_EXPIRE_TIME', 7200*12)  # expire in 1 day
        redis_store.expire(auth_token, expires_in)
        db.session.commit()
        return dict(auth_token=auth_token, expires_in=expires_in, user_info=u.todict())


bp.add_url_rule('/register', view_func=RegisterView.as_view('user_register'))
bp.add_url_rule('/register/github', view_func=RegisterAuthGithub.as_view('register_github'))
bp.add_url_rule('/register/kcash', view_func=RegisterKCash.as_view('register_kcash'))
bp.add_url_rule('/register/claim', view_func=ClaimGithub.as_view('claim_github'))
