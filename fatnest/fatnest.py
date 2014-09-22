import os
import sys
import datetime
import hashlib
import random
import string
import smtplib
import tweepy

import psycopg2
from flask import Blueprint, Flask, render_template, url_for, redirect, \
        request,session, g, send_file, jsonify, Response, flash
from flaskext.csrf import csrf, csrf_exempt
from functools import wraps
from psycopg2.extras import DictCursor
from jinja2 import TemplateNotFound
#from werkzeug.contrib.cache import MemcachedCache
from email.mime.text import MIMEText

import default_settings
import model

#cache = MemcachedCache(['127.0.0.1:11211'])

instance_path = os.path.expanduser('~/fatnest_instance/')
app = Flask(__name__, instance_path=instance_path)
csrf(app)
app.config.from_object('fatnest.default_settings')
external_cfg = os.path.join(app.instance_path, 'application.cfg')
app.config.from_pyfile(external_cfg, silent=True)
app.TRAP_BAD_REQUEST_ERRORS = True
cached_ip = None

def gen_token():
    return ''.join(random.choice(string.letters) for x in range(20))

def full_url_for(name):
    return "http://fatnest.com%s" % (
            url_for(name)
            )

def send_email(email_address, subject, message,
        from_address="noreply@fatnest.com"):
    msg = MIMEText(message)
    msg['subject'] = subject
    msg['From'] = from_address
    msg['To'] = email_address
    s = smtplib.SMTP(app.config['SMTP_HOST'], app.config['SMTP_PORT'])
    if 'SMTP_USERNAME' in app.config:
        s.login(app.config['SMTP_USERNAME'], app.config['SMTP_PASSWORD'])
    s.sendmail(msg['From'], [msg['To']], msg.as_string())
    s.quit()

def send_invite(email_address, sending_user):
    m = hashlib.sha256()        
    pw = pwgen()
    m.update(pw)
    password = m.hexdigest()
    user = model.User.new({
        'email': email_address,
        'password': password
        })
    send_email(email_address, "You've been invited to fatnest",
        render_template('email_invite.html', password=pw,
            sending_user=sending_user))
    return user


def pwgen(length=12, chars=string.letters + string.digits):
    return ''.join([random.choice(chars) for i in range(length)])

def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user' not in session:
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated

def ajaxonly(f):
    f = csrf_exempt(f)
    @wraps(f)
    def decorated(*args, **kwargs):
        if not request.is_xhr:
            return "Bad Request", 400
        return f(*args, **kwargs)
    return decorated

@app.before_request
def before_request():
    model.set_conn(app.config['DATABASE_CONNECTION'])

@app.teardown_request
def teardown_request(exception):
    pass


@app.route('/')
def home():
    return render_template('home.html', home=True)

@app.route('/privacy-policy')
def privacy_policy():
    return render_template('privacy_policy.html')

@app.route('/terms-of-service')
def terms_of_service():
    return render_template('terms_of_service.html')

@app.route('/twitter-accounts')
def twitter_accounts():
    return render_template('twitter_accounts.html')

@app.route('/create-an-account')
def create_account():
    return render_template('create_account.html')

@app.route('/login', methods=['GET','POST'])
def login(next=None):
    if next is None:
        next = url_for('home')
    if request.method == 'POST':
        form = request.form
        email = form['email']  
        if '' in [email, form['password']]:
            flash("Please fill out all form fields.", "error")
            return render_template('login.html', form={'email': ''})   
        found_user = model.User.where({'email': email})[0]
        m = hashlib.sha256()        
        if not found_user:
            flash('Could not log you in with that email and password.',
                'error')
            return redirect(url_for('login'))
        else:
            # login
            m.update(form['password'])
            attempted_password = m.hexdigest()
            if (attempted_password == found_user['password']):
                # success
                session['user'] = found_user
            else:
                flash("Could not log you in with that email and password.",
                    'error')
                return redirect(url_for('login'))
            flash("Thanks for logging in, friend.", "success")
            return redirect(next)
    return render_template('login.html', form={'email': ''})

@requires_auth
@app.route('/change-password', methods=['POST'])
def change_password():
    m = hashlib.sha256()        
    m.update(request.form['current-password'])
    attempted_password = m.hexdigest()
    if attempted_password != session['user'].password:
        flash("The current password you entered was not correct.", "error")
    else:
        n = hashlib.sha256()
        n.update(request.form['password'])
        new_pw = n.hexdigest()
        session['user'].password = new_pw 
        session['user'].save()
        flash("Your password was changed.", "success")
    return redirect(url_for('settings'))

@requires_auth
@app.route('/settings', methods=['GET'])
def settings():
    return render_template('settings.html')

@app.route('/reset-password', methods=['GET', 'POST'])
def reset_password():
    if request.method == 'POST':
        form = request.form
        email = form['email']
        if email == '':
            flash("No email address entered.", "error")
            return render_template('reset_password.html')     
        found_user = model.User.where({'email': email})[0]
        token = model.ResetToken.generate_for(found_user.id)
        send_email(email, "Fatnest Password Reset", 
            render_template('email_reset_password.html',
                reset_link='http://fatnest.com' + url_for('send_reset_password',
                token=token.token)))
        flash("An email was sent with instructions on how to reset your " + \
            "password.", "success")
        return redirect(url_for('login'))
    else:
        return render_template('reset_password.html')


@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def send_reset_password(token):
    reset_token = model.ResetToken.where({'token': token})
    if not reset_token or len(reset_token) == 0:
        flash("Token not found.", "error")
        return redirect(url_for('login'))
    reset_token = reset_token[0]
    if request.method == 'POST':
        form = request.form
        if 'password' not in form:
            flash('No password supplied.', 'error')
            return render_template('complete_password_reset.html',
                token=reset_token.token)
        found_user = model.User.get(reset_token.user_id)
        m = hashlib.sha256()        
        pw = form['password']
        m.update(pw)
        password = m.hexdigest()
        found_user.password = password
        found_user.save()
        session['user'] = found_user
        flash("Your password was reset and you've been logged in.", "success")
        reset_token.delete()
        return redirect(url_for('home'))
    else:
        return render_template('complete_password_reset.html',
            token=reset_token.token)

@app.route('/register', methods=['POST'])
def register():
    form = request.form
    email = form['email']        
    found_user = model.User.exists({'email': email})
    m = hashlib.sha256()
    if not found_user:
        # create one
        pw = pwgen()
        m.update(pw)
        password = m.hexdigest()
        user = model.User.new({
            'email': email,
            'password': password
            })
        send_email(email, "Welcome to FatNest!",
            render_template('email_signup.html', user=user, password=pw))
        flash("Thanks for registering. Check your email for your password.",
            "success")
        return redirect(url_for('home'))
    else:
        flash('This email address is already registered.', 'error')    
        return redirect(url_for('login'))

@app.route('/logout')
def logout():
    session.clear()
    flash("You were signed out. See you again next time!", "success")
    return redirect(url_for('home'))

@requires_auth
@app.route('/verify-twitter')
def verify_twitter():
    verifier = request.args['oauth_verifier']
    auth = tweepy.OAuthHandler(app.config['TWITTER_CONSUMER_KEY'],
            app.config['TWITTER_CONSUMER_SECRET'])
    token = session['twitter_request_token']
    del session['twitter_request_token']
    auth.set_request_token(token[0], token[1])
    try:
        auth.get_access_token(verifier)
    except tweepy.TweepError:
        flash("Could not authenticate your Twitter account.", 'error')
        return redirect(url_for('twitter_accounts'))
    api = tweepy.API(auth)
    username = api.me().screen_name
    if model.TwitterAccount.exists({'username': username}):
        flash("This Twitter account is already managed by another user.", 'error')
        return redirect(url_for('twitter_accounts'))
    data = {
        'access_token_key': auth.access_token.key,
        'access_token_secret': auth.access_token.secret,
        'username': username,
        'user_id': session['user'].id
        }
    taccount = model.TwitterAccount.new(data)
    taccount.set_submission_token()
    return redirect(url_for('twitter_accounts'))

@requires_auth
@ajaxonly
@app.route('/delegate-twitter', methods=['POST'])
def delegate_twitter_account():
    form = request.form
    target_email = form['email']
    twitter_id = form['twitter_account_id']
    result = 'delegated'
    if not session['user'].has_twitter_account(twitter_id):
        return jsonify({'result': 'invalid'})
    if not model.User.exists({'email': target_email}):
        user = send_invite(target_email, session['user'])
        result = 'invited'
    else:
        user = model.User.where({'email': target_email}) 
        if user:
            user = user[0]
    new_delegate = model.Delegate.new({
        'twitter_account_id': twitter_id,
        'user_id': user.id
        })
    return jsonify({'result': result})

@requires_auth
@ajaxonly
@app.route('/delete-twitter-delegate', methods=['POST'])
def delete_twitter_delegate():
    form = request.form
    delegate = model.Delegate.get(form['delegate'])
    if delegate.owner.id != session['user'].id:
        return jsonify({'result': False})
    delegate.delete()
    return jsonify({'result': True})

@requires_auth
@ajaxonly
@app.route('/twitter-delegates/<id>')
def twitter_delegates(id):
    if id is None:
        return jsonify({'result': None})
    twitter_account = model.TwitterAccount.get(id)
    if id == 'null' or \
        twitter_account.user_id != session['user'].id:
        return jsonify({'result': None})

    delegates = [dict(deleg) for deleg in twitter_account.delegates]
    for deleg in delegates:
        deleg['user'] = dict(model.User.get(deleg['user_id']))
        del deleg['user']['created']
        del deleg['user']['password']
    return jsonify({'result': delegates})

@requires_auth
@app.route('/add-twitter')
def auth_twitter_account():
    try:
        auth = tweepy.OAuthHandler(app.config['TWITTER_CONSUMER_KEY'],
            app.config['TWITTER_CONSUMER_SECRET'],
            full_url_for('verify_twitter'))
        twitter_auth_url = auth.get_authorization_url()
        session['twitter_request_token'] = (auth.request_token.key,
            auth.request_token.secret)
    except tweepy.TweepError:
        flash("Could not authenticate your Twitter account.", 'error')
        return redirect(url_for('home'))
    return redirect(twitter_auth_url)

@requires_auth
@ajaxonly
@app.route('/remove-twitter', methods=['POST'])
def remove_twitter_account():
    twitter_account_id = request.form['twitter_account_id']
    if not session['user'].has_twitter_account(twitter_account_id):
        return jsonify({'result': False})
    tw = model.TwitterAccount.get(twitter_account_id)
    if tw is None:
        return jsonify({'result': False})
    tw.delete()
    return jsonify({'result': True})

@requires_auth
@ajaxonly
@app.route('/send-tweet', methods=['POST'])
def send_tweet():
    token = request.form.get('token')
    if token is None and 'user' not in session:
        # Anonymous users must tweet with a token
        return jsonify({'result': False})
    twitter_account = model.TwitterAccount.get(request.form['twitter_account_id'])
    tweet = request.form['tweet']
    user_id = session['user'].id if 'user' in session else None
    delegate = model.Delegate.by_user(user_id, twitter_account.id)
    # Approve the tweet if a) The user is the same as the owner
    # b) delegation is present and allowed
    # c) anon submissions are unmoderated
    approved = twitter_account.user_id == user_id or \
        (delegate is not None and not delegate.moderated) or \
        not twitter_account.anonymous_moderated
    tweet = model.Tweet.new({
        'twitter_account_id': twitter_account.id,
        'tweet': request.form['tweet'],
        'approved': approved,
        'resolved': approved,
        'resolved_time': model.candle.RawValue('now()') if approved else None,
        'user_id': user_id,
        'ip_address': str(request.remote_addr)
        })
    if approved:
        tweet.send_tweet()
    result = 'tweeted' if approved else 'pending'
    return jsonify({'result': result, 'tweet_id': tweet.id if result else None})
       
@requires_auth
@app.route('/twitter-account/<id>')
def twitter_account(id):
    twitter_account = model.TwitterAccount.get(id)
    twitter_account.set_submission_token()
    if not twitter_account.has_access(session['user'].id):
        return redirect(url_for('home'))
    return render_template('twitter_account_settings.html',
        twitter_account=twitter_account)

@requires_auth
@ajaxonly
@app.route('/set-delegate-moderation', methods=['POST'])
def set_delegate_moderation():
    delegate = model.Delegate.get(request.form['delegate'])
    if delegate is not None and \
        delegate.twitter_account.user_id == session['user'].id:
        delegate.moderated = 'moderated' in request.form and \
            request.form['moderated'] == 'checked'
        delegate.save()
        return jsonify({'result': True})
    return jsonify({'result': False})

@requires_auth
@ajaxonly
@app.route('/set-anonymous-moderation', methods=['POST'])
def set_anonymous_moderation():
    twitter_account = model.TwitterAccount.get(request.form['twitter_account'])
    if twitter_account and twitter_account.user_id == session['user'].id:
        twitter_account.anonymous_moderated = \
            'moderated' in request.form and \
            request.form['moderated'] == 'checked'
        print ">>> " + str(request.form['moderated'])
        twitter_account.save()
        return jsonify({'result': True})
    return jsonify({'result': False})

@app.route('/submit/<token>')
def submit_tweet(token):
    submit_token = model.SubmissionToken.get(token)
    twitter_account = submit_token.twitter_account
    return render_template('submit.html',
        submission_token=submit_token.token,
        twitter_account=twitter_account)

@requires_auth
@ajaxonly
@app.route('/approve-tweet', methods=['POST'])
def approve_tweet():
    tweet = model.Tweet.get(request.form['tweet'])
    if tweet.twitter_account.user_id == session['user'].id:
        tweet.approved = True 
        tweet.resolved = True
        tweet.resolved_time = model.candle.RawValue('now()')
        result = tweet.send_tweet()
        return jsonify({'result': True, 'tweet_id': tweet.id})
    else:
        return jsonify({'result': False})

@requires_auth
@ajaxonly
@app.route('/reject-tweet', methods=['POST'])
def reject_tweet():
    tweet = model.Tweet.get(request.form['tweet'])
    if tweet.twitter_account.user_id == session['user'].id:
        tweet.approved = False 
        tweet.resolved = True
        tweet.resolved_time = model.candle.RawValue('now()')
        tweet.save()
        return jsonify({'result': True})
    else:
        return jsonify({'result': False})

@requires_auth
@ajaxonly
@app.route('/embedded/<tweet_id>')
def embedded_tweet(tweet_id):
    tweet = model.Tweet.get(tweet_id)
    if tweet.twitter_tweet_id is not None:
        return jsonify({'result': True, 'html': tweet.embedded})
    return jsonify({'result': False})

app.secret_key = app.config['SECRET_KEY']
app.debug = True

if __name__ == '__main__':
    app.run()

