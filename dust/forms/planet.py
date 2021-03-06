from datetime import datetime, timedelta
from wtforms import StringField, Field, IntegerField
from wtforms.validators import DataRequired, Length, Email, ValidationError, NumberRange, URL
from . import JSONForm
from ..core import current_user, db, redis_store
from ..models.user_planet import Planet, User, BuildRecord
from ..constants import Status


class SetupPlanetForm(JSONForm):
    name = Field('name', [DataRequired(), Length(max=30, min=1)])
    email = StringField('email', [DataRequired(), Email()])
    keywords = StringField('keywords', [DataRequired(), Length(max=32, min=1)])
    description = StringField('description', [DataRequired(), Length(min=1)])
    demo_url = StringField('demo_url', [DataRequired(), URL()])
    github_url = StringField('github_url', [DataRequired(), URL()])
    team_intro = StringField('team')

    def __init__(self, uid=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.uid = uid or current_user.id

    def validate_name(self, field):
        e = Planet.query.filter_by(name=field.data).first()
        if e:
            raise ValidationError('Duplicate project name')

    def validate_github_url(self, field):
        e = Planet.query.filter_by(github_url=field.data).first()
        if e:
            raise ValidationError('This github project already exits.')

    def validate_demo_url(self, field):
        e = Planet.query.filter_by(github_url=field.data).first()
        if e:
            raise ValidationError('This demo already exits.')

    def save(self, pid=None):
        if pid:
            p = Planet.query.get_or_404(pid)
        else:
            p = Planet(owner_id=self.uid)
            db.session.add(p)
            p.dust_num = 100
        p.name = self.name.data
        p.description = self.description.data
        p.keywords = self.keywords.data
        p.demo_url = self.demo_url.data
        p.github_url = self.github_url.data
        p.team_intro = self.team_intro.data
        p.email = self.email.data
        db.session.commit()
        return p

    def setup(self, owner_id=None):
        if owner_id:
            owner = User.query.get_or_404(owner_id)
        else:
            owner = current_user
        owner.owned_dust += 100
        owner.planet_dust_sum += 100
        return self.save()


class BuildPlanetForm(JSONForm):
    planet_name = Field('planet_name', [DataRequired()])
    dust_num = IntegerField('dust_num', [DataRequired(), NumberRange(min=1)])

    def __init__(self, uid=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.planet = Planet.query.filter_by(name=self.planet_name.data).first()

    def validate_planet_name(self, field):
        if not self.planet:
            raise ValidationError('No such planet.')

    def validate_dust_num(self, field):
        if field.data > current_user.owned_dust:
            raise ValidationError('You donnot have so mach dust.')

    # def validate_builder(self):
    #     if self.planet.owner_id == current_user.id:
    #         raise ValidationError('Owner of the planet cannot build it.')

    def validate_time(self):
        if datetime.now() - self.planet.created_at > timedelta(days=30):
            self.planet.status = Status.UNSHELVED
            db.session.commit()
            raise ValidationError('Build timeout.')

    # def validate_build_times(self):
    #     t = redis_store.get("%s:build_times" % current_user.id)
    #     if t <= 0:
    #         raise ValidationError('Today\'s three times have been used. Please build tomorrow.')

    def build(self):
        record = BuildRecord(builder_id=current_user.id)
        db.session.add(record)
        record.planet_id = self.planet.id
        record.dust_num = self.dust_num.data
        self.planet.dust_num += self.dust_num.data
        self.planet.builder_num += 1
        planet_owner = User.query.get(self.planet.owner_id)
        planet_owner.planet_dust_sum += self.dust_num.data
        current_user.owned_dust -= self.dust_num.data
        db.session.flush()
        record.planet_dust = self.planet.dust_num
        db.session.commit()
        # t = redis_store.get("%s:build_times" % current_user.id)
        # tleft = redis_store.ttl("%s:build_times" % current_user.id)
        # redis_store.set("%s:build_times" % current_user.id, int(t)-1, ex=tleft)
        return record
