import candle
import psycopg2
import tweepy
import fatnest
import requests


class Cache(candle.Candle):
    table_name = 'cache'

    @classmethod
    def set(cls, key, val, expires=None):
        cursor = cls.cursor()
        if expires is None:
            cursor.execute("""
                SELECT cache_set(%s, %s)
                """, [key, val])
        else:
            if type(expires) != int:
                raise Exception("Expires must be an integer.")
            interval = "'%s seconds'" % expires
            cursor.execute("""
                SELECT cache_set(%s, %s, interval """ + interval + """)
                """, [key, val])
        cls.conn.commit()
 
    @classmethod
    def get(cls, key):
        cursor = cls.cursor()
        cursor.execute("""
            SELECT cache_get(%s) AS "value"
            """, [key])
        result = cursor.fetchone()
        return result['value'] if result else None

    @classmethod
    def delete(cls, key):
        cursor = cls.cursor()
        cursor.execute("""
            SELECT cache_del(%s)
            """, [key])
        cls.conn.commit()


class User(candle.Candle):
    table_name = 'users'

    @property
    @candle.enablecache
    def twitter_accounts(self):
        return TwitterAccount.where({'user_id': self.id})

    def has_twitter_account(self, id):
        return TwitterAccount.exists({
            'user_id': self.id,
            'id': id
            })

    def has_delegate(self, id):
        return Delegate.get(id).owner.id == self.id

    @property
    @candle.enablecache
    def display_name(self):
        return self.email

    @property
    @candle.enablecache
    def delegated_twitter_accounts(self):
        cursor = self.cursor()
        cursor.execute("""
            SELECT * FROM twitter_accounts WHERE id IN (
                SELECT twitter_account_id FROM delegates WHERE user_id = %s
                )
                OR user_id = %s
                ORDER BY user_id = %s DESC, username ASC
            """, [self.id, self.id, self.id])
        return [TwitterAccount(row) for row in cursor.fetchall()]

    @property
    @candle.enablecache
    def moderation_needed(self):
        return len(self.moderation_queue) > 0

    @property
    def moderation_queue(self):
        cursor = self.cursor()
        cursor.execute("""
            SELECT * FROM tweets
            WHERE twitter_account_id IN (
                SELECT id 
                FROM twitter_accounts
                WHERE user_id = %s
                )
            AND NOT resolved
            """, [self.id])
        result = cursor.fetchall()
        tweets = [Tweet(r) for r in result]
        return tweets

    @property
    def recent_tweets(self):
        cursor = self.cursor()
        cursor.execute("""
            SELECT * FROM tweets
            WHERE twitter_account_id IN (
                SELECT id
                FROM twitter_accounts
                WHERE user_id = %s
                UNION
                SELECT twitter_account_id
                FROM delegates
                WHERE user_id = %s
            )
            AND resolved
            AND approved
            ORDER BY resolved_time DESC
            LIMIT 10
            """, [self.id, self.id])
        result = cursor.fetchall()
        tweets = [Tweet(r) for r in result]
        return tweets


class TwitterAccount(candle.Candle):
    table_name = 'twitter_accounts'
    _id_column = 'id'

    @property
    @candle.enablecache
    def moderation_needed(self):
        return len(self.moderation_queue) > 0
    
    @property
    @candle.enablecache
    def moderation_queue(self):
        return Tweet.where({
            'twitter_account_id': self.id,
            'resolved': False
        })

    @property
    @candle.enablecache
    def api(self):
        auth = tweepy.OAuthHandler(fatnest.app.config['TWITTER_CONSUMER_KEY'],
            fatnest.app.config['TWITTER_CONSUMER_SECRET'])
        auth.set_access_token(self.access_token_key, self.access_token_secret)
        return tweepy.API(auth)

    @property
    @candle.enablecache
    def delegates(self):
        return Delegate.where({'twitter_account_id': self.id})

    @property
    @candle.enablecache
    def user(self):
        return User.get(self.user_id)

    def has_access(self, user_id):
        if self.user_id == user_id:
            return True
        cursor = self.cursor()
        cursor.execute("""
            SELECT TRUE FROM delegates WHERE twitter_account_id = %s AND user_id = %s
            """, [self.id, user_id])
        return cursor.fetchone() != None

    @property
    def has_submission_token(self):
        return SubmissionToken.exists({
            'twitter_account_id': self.id
            })

    def set_submission_token(self):
        if not self.has_submission_token:
            token = SubmissionToken.generate_for(self.id)
            token.save()

    @property
    @candle.enablecache
    def submission_token(self):
        return SubmissionToken.where({
            'twitter_account_id': self.id
            })[0]

    @property
    @candle.enablecache
    def submission_url(self):
        return "http://fatnest.com/submit/%s" % self.submission_token.token

    def __init__(self, *args, **kwargs):
        super(candle.Candle, self).__setattr__('_api', None)
        super(TwitterAccount, self).__init__(*args, **kwargs)


class Tweet(candle.Candle):
    table_name = 'tweets'

    @property
    @candle.enablecache
    def user(self):
        return User.get(self.user_id)

    @property
    @candle.enablecache
    def twitter_account(self):
        return TwitterAccount.get(self.twitter_account_id)

    @property
    @candle.enablecache
    def api(self):
        return self.twitter_account.api

    def send_tweet(self):
        try:
            result = self.api.update_status(self.tweet)
        except tweepy.TweepError:
            return False
        if type(result) != tweepy.models.Status:
            return False
        self.twitter_tweet_id = result.id
        self.save()
        return True

    @property
    @candle.enablecache
    def author(self):
        if self.user_id is not None:
            return self.user
        return self.ip_address

    @property
    @candle.enablecache
    def embedded(self):
        if self.twitter_tweet_id is None or int(self.twitter_tweet_id) == 0:
            raise Exception("Tweet not published.")
        cache_key = "embed_" + self.twitter_tweet_id
        embedded_html = Cache.get(cache_key)
        if embedded_html:
            return embedded_html
        response = requests.get(
            ('https://api.twitter.com/1/statuses/oembed.json?id=%s&' + \
            'omit_script=true&align=none&hide_threa=true') % self.twitter_tweet_id)
        if response.status_code == 200:
            embedded_html = response.json['html']
            Cache.set(cache_key, embedded_html, 3600)
        elif response.status_code == 404:
            Cache.delete(cache_key)
            self.twitter_tweet_id = None
            self.save()
            return None
        return embedded_html


class Delegate(candle.Candle):
    table_name = 'delegates'

    @property
    @candle.enablecache
    def user(self):
        return User.get(self.user_id)

    @property
    @candle.enablecache
    def owner(self):
        return self.twitter_account.user

    @property
    @candle.enablecache
    def twitter_account(self):
        return TwitterAccount.get(self.twitter_account_id)

    @classmethod
    def by_user(cls, user_id, twitter_id):
        if user_id is None:
            return None
        result = cls.where({'user_id': user_id, 'twitter_account_id': twitter_id})
        if result and len(result) > 0:
            return result[0]
        return None

class ResetToken(candle.Candle):
    table_name = 'password_reset_tokens'
    _id_column = 'token'

    @property
    @candle.enablecache
    def user(self):
        return User.get(self.user_id)
    
    @classmethod
    def generate_for(cls, user_id):
        return cls.new({
            'user_id': user_id,
            'token': fatnest.gen_token()
            })

class SubmissionToken(candle.Candle):
    table_name = 'submission_tokens'
    _id_column = 'token'

    @property
    @candle.enablecache
    def twitter_account(self):
        return TwitterAccount.get(self.twitter_account_id)

    @classmethod
    def generate_for(cls, twitter_account_id):
        return cls.new({
            'twitter_account_id': twitter_account_id,
            'token': fatnest.gen_token()
            })


def set_conn(connstring):
    conn = psycopg2.connect(connstring)
    User.set_conn(conn)
    TwitterAccount.set_conn(conn)
    Delegate.set_conn(conn)
    SubmissionToken.set_conn(conn)
    Tweet.set_conn(conn)
    Cache.set_conn(conn)
    ResetToken.set_conn(conn)
