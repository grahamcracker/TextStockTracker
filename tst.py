from flask import Flask, request, redirect
import twilio.twiml
import requests

app = Flask(__name__)
MOD_BASE_URL = 'http://dev.markitondemand.com/MODApis/Api/v2/'

@app.route("/hello", methods=['POST'])
def hello():
    body = request.values.get('Body')
    resp = twilio.twiml.Response()
    first_word = body.split(' ')[0]
    message = ""

    if body == 'commands':
        message = "Available commands:\n"
        message += "_stock_symbol_ = look up stock symbol 'ABCD'\n"
        message += "lookup _company name_ = get the stock symbol for a company\n"
    elif first_word == 'lookup':
        query = body.split(' ', 1)[1]
        r = requests.get(MOD_BASE_URL + 'Lookup/json?input=' + query)
        json = r.json()
        first_result = json[0]
        message = "You're probably looking for "
        message += first_result['Name']
        message += ", which is listed on "
        message += first_result['Exchange']
        message += " as '"
        message += first_result ['Symbol']
        message += "'."
    elif body.isalpha() and len(body) <= 5 and all(letter.isupper() for letter in body):
        # probably a stock ticker: alphabet characters, length <= 5 and all letters are capitalized
        r = requests.get(MOD_BASE_URL + 'Quote/json?symbol=' + body)
        json = r.json()
        message = json['Symbol']
        message += " ("
        message += json['Name']
        message += ") is currently trading at $"
        message += str(json['LastPrice'])
        message += "."
        resp.message(message)
    else:
        message = "Oops! We couldn't understand your query. Text 'commands' to learn more."

    resp.message(message)
    return str(resp)

if __name__ == "__main__":
    app.run(debug=True, port=12345)
