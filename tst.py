from flask import Flask, request, redirect
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
import twilio.twiml
import requests

# The base URL for the MarkitOnDemand API
MOD_BASE_URL = 'http://dev.markitondemand.com/MODApis/Api/v2/'

# Create the application, set up a temporary database
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////tmp/tst.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# User model is simple: we store an ID and the user's phone number
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    phone_number = db.Column(db.String(100), unique=True)

    def __init__(self, phone_number):
        self.phone_number = phone_number

    def __repr__(self):
        return '<User %r>' % self.phone_number

# We keep track of Messages for 'more info' texts.
# Stored are the user, stock symbol, and the date the message was sent
class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    user = db.relationship('User',
        backref=db.backref('messages', lazy='dynamic'))
    stock_symbol = db.Column(db.String(5))
    sent_date = db.Column(db.DateTime)

    def __init__(self, user, stock_symbol, sent_date=None):
        self.user = user
        self.stock_symbol = stock_symbol
        if sent_date is None:
            sent_date = datetime.utcnow()
        self.sent_date = sent_date

    def __repr__(self):
        return '<Message from %r about %r>' % (self.user.phone_number, self.stock_symbol)

# The Twilio webhook should be set to /hello wherever this app is run.
@app.route("/hello", methods=['POST'])
def hello():
    body = request.values.get('Body')
    _from = request.values.get('From')
    first_word = body.split(' ')[0]

    message = ""

    # First, create a User object for this number if one does not already exist
    user = User.query.filter_by(phone_number=_from).first()
    if not user:
        user = User(_from)
        db.session.add(user)
        db.session.commit()
        message += "Welcome to Text Stock Tracker!\n"

    # The 'commands' feature informs users how to use the app.
    if body.lower() == 'commands':
        message += "Available commands:\n"
        message += "To look up the current price for a company, text us the stock symbol e.g. 'AAPL'.\n"
        message += "To find a company's symbol, text us with 'lookup' and the company name, e.g. 'lookup Wal Mart'.\n"
        message += "After looking for a company or stock price, text 'more info' for more information."
    # With 'more info', users can learn more about a company's stock.
    elif body.lower() == 'more info':
        # We first find the latest message for the user that isn't older than 24 hours,
        # then find out which stock symbol was looked up.
        since = datetime.utcnow() - timedelta(hours=24)
        last_message = Message.query\
            .filter_by(user_id=user.id)\
            .filter(Message.sent_date > since)\
            .order_by(Message.sent_date.desc()).first()
        if not last_message:
            message += "Hello! Try looking up a stock first, example: lookup AAPL."
        else:
            symbol = last_message.stock_symbol
            r = requests.get(MOD_BASE_URL + 'Quote/json?symbol=' + symbol)
            json = r.json()
            message += "%s (%s) is currently trading at %s, a change of %r from yesterday.\n" % (
                json['Symbol'],
                json['Name'],
                json['LastPrice'],
                json['Change']
            )
            message += "%s has a market cap of %s and opened at %s today.\n" % (
                json['Symbol'],
                json['MarketCap'],
                json['Open']
            )
            message += "Today's high price for %s was %s and the low price was %s\n" % (
                json['Symbol'],
                json['High'],
                json['Low']
            )
    # Users can research the symbol for the company with 'lookup'
    elif first_word.lower() == 'lookup':
        # The query here is everything after 'lookup'
        query = body.split(' ', 1)[1]
        r = requests.get(MOD_BASE_URL + 'Lookup/json?input=' + query)
        json = r.json()
        first_result = json[0]
        new_message = Message(user, first_result['Symbol'])
        db.session.add(new_message)
        db.session.commit()
        message += "You're probably looking for %s, which is listed on %s as '%s'." % (
            first_result['Name'],
            first_result['Exchange'],
            first_result ['Symbol']
        )
    elif body.isalpha() and len(body) <= 5 and all(letter.isupper() for letter in body):
        # User is probably submitting a stock ticker:
        # alphabet characters, length <= 5 and all letters are capitalized
        r = requests.get(MOD_BASE_URL + 'Quote/json?symbol=' + body)
        json = r.json()
        if not 'Symbol' in json:
            message += "Sorry! We couldn't find the U.S. stock ticker symbol for '%s'." % body
        else:
            new_message = Message(user, json['Symbol'])
            db.session.add(new_message)
            db.session.commit()
            message += "%s (%s) is currently trading at %s." % (
                json['Symbol'],
                json['Name'],
                str(json['LastPrice'])
            )
    else:
        message = "Oops! We couldn't understand your query. Text 'commands' to learn more."

    # Send a message back to the user using the Twilio API
    resp = twilio.twiml.Response()
    resp.message(message)
    return str(resp)

if __name__ == "__main__":
    app.run(debug=True, port=12345)
