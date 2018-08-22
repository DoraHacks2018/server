import binascii
import os
from datetime import datetime
from flask import Blueprint, current_app, request
from flask.views import MethodView
from flask_mail import Message

from ..core import redis_store, db, oauth_client, mail, logger
from ..exceptions import LoginInfoRequired, LoginInfoError, NoError, LoginAuthError, EmailRequired, ResetTokenError, \
    NoEmailError
from ..models.user_planet import User, Notification
from ..constants import Notify, NotifyContent

bp = Blueprint('login', __name__)


class LoginView(MethodView):
    def post(self):
        data = request.get_json() or {}
        username = data.get('username')
        password = data.get('password')
        if not (username and password):
            raise LoginInfoRequired()

        user = User.get_by_username(username)
        if not user:
            raise LoginInfoError()
        if not user.check_password(password):
            raise LoginInfoError()
        auth_token = binascii.hexlify(os.urandom(16)).decode()  # noqa
        redis_store.hmset(auth_token, dict(
            id=user.id,
            # password=user.password,
            created_at=datetime.now(),
        ))
        expires_in = current_app.config.get('LOGIN_EXPIRE_TIME', 7200 * 12)  # expire in 1 day
        redis_store.expire(auth_token, expires_in)

        # s = redis_store.get("%s:build_times" % user.id)
        # if not s:
        #     n = Notification(type=Notify.BUILD, uid=user.id)
        #     db.session.add(n)
        #     redis_store.set("%s:build_times" % user.id, 3, ex=expires_in)
        #     n.content = NotifyContent.get(Notify.BUILD).format('3')
        # db.session.commit()

        return dict(auth_token=auth_token, expires_in=expires_in, user_info=user.todict())


class LogoutView(MethodView):
    def get(self):
        auth_token = request.headers.get('X-Auth-Token')
        if auth_token:
            redis_store.delete(auth_token)
        raise NoError()


class LoginAuthGithub(MethodView):
    def post(self):
        code = request.get_json().get('code')
        resp = oauth_client.get_token(code)
        logger.debug('github auth resp: %s', resp.json())
        logger.debug('github auth resp.data: %s', resp.json())
        logger.debug('github auth resp.json(): %s', resp.json())
        access_token = resp.json().get('access_token')
        if not access_token:
            raise LoginAuthError()
        oauth_client.set_token(access_token)
        user_info = oauth_client.user().json()
        u1 = User.get_by_username(user_info.get('login'))
        u2 = User.query.filter_by(git_account=user_info.get('login')).first()
        if not u1 and not u2:
            u = User(username=user_info.get('login'))
            u.git_account = user_info.get('login')
            u.github_link = user_info.get('html_url')
            u.avatar = user_info.get('avatar_url')
            db.session.add(u)
            db.session.flush()
        elif u1 and not u2:
            u = u1
        elif u2 and not u1:
            u = u2
        elif u1 == u2:
            u = u1
            # raise RegisterFailError()
        auth_token = binascii.hexlify(os.urandom(16)).decode()  # noqa
        redis_store.hmset(auth_token, dict(
            id=u.id,
            created_at=datetime.now(),
        ))
        db.session.commit()
        expires_in = current_app.config.get('LOGIN_EXPIRE_TIME', 7200 * 12)  # expire in 1 day
        redis_store.expire(auth_token, expires_in)

        # s = redis_store.get("%s:build_times" % user.id)
        # if not s:
        #     n = Notification(type=Notify.BUILD, uid=user.id)
        #     db.session.add(n)
        #     redis_store.set("%s:build_times" % user.id, 3, ex=expires_in)
        #     n.content = NotifyContent.get(Notify.BUILD).format('3')
        # db.session.commit()

        return dict(auth_token=auth_token, expires_in=expires_in, user_info=u.todict())


class SendEmailResetPassword(MethodView):
    def post(self):
        data = request.get_json() or {}
        email = data.get('email')
        if not email:
            raise EmailRequired()
        user = User.get_by_email(email)
        if not user:
            raise NoEmailError()
        auth_token = binascii.hexlify(os.urandom(16)).decode()  # noqa
        redis_store.hmset(auth_token, dict(
            email=email,
            created_at=datetime.now(),
        ))
        expires_in =current_app.config.get('LOGIN_EXPIRE_TIME', 3600 * 24)  # expire in 1 day
        redis_store.expire(auth_token, expires_in)
        msg = Message(subject='密码重置',  # 需要使用默认发送者则不用填
                      recipients=[email])
        # 邮件内容会以文本和html两种格式呈现，而你能看到哪种格式取决于你的邮件客户端。
        cnt = "<b>请点击链接修改密码：<a href='http://ranking.dorahacks.com/resetpassword?token=%s'>修改密码</a><br>24小时内有效<b>"
        msg.html = cnt % auth_token
        mail.send(msg)
        return dict(state=0)


class ResetPassword(MethodView):
    def post(self):
        data = request.get_json() or {}
        token = data.get('token')
        passwd = data.get('passwd')
        if not (token and passwd):
            raise LoginInfoRequired()
        if not redis_store.exists(token):
            raise ResetTokenError()
        token_info = redis_store.hget(token, 'email')
        user = User.get_by_email(token_info)
        user.password = passwd
        db.session.commit()
        # auth_token = binascii.hexlify(os.urandom(16)).decode()  # noqa
        return dict(state=0)


bp.add_url_rule('/login', view_func=LoginView.as_view('login'))
bp.add_url_rule('/auth-login/github', view_func=LoginAuthGithub.as_view('login_github'))
bp.add_url_rule('/logout', view_func=LogoutView.as_view('logout'))
bp.add_url_rule('/send-email', view_func=SendEmailResetPassword.as_view('send_email_reset_password'))
bp.add_url_rule('/reset-password', view_func=ResetPassword.as_view('reset_password'))
