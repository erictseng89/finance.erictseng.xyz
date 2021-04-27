import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")

# function for viewing the portfolio
def view_portfolio(user_id):
    user_id = session["user_id"]
    portfolio = db.execute("SELECT * FROM owned WHERE user_id = ? AND shares > 0 ORDER BY symbol ASC" , user_id)
    shares_value = 0
    for row in portfolio:
        price = lookup(row["symbol"])["price"]
        row["price"] = price
        shares_value += price * row["shares"]
    cash = db.execute("SELECT cash FROM users WHERE id = ?", user_id)[0]["cash"]
    
    return render_template("index.html", portfolio = portfolio, cash = cash, shares_value = shares_value)    


@app.route("/", methods=["GET"])
@login_required
def index():
    """Show portfolio of stocks"""
    return view_portfolio(session["user_id"])


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "GET":
        return render_template("buy.html")
    if request.method == "POST":
        symbol = request.form.get("symbol")
        shares = int(request.form.get("shares"))
        # First check for correct input.
        if not symbol:
            return apology("must input symbol", 400)
        elif not shares:
            return apology("must input number of shares", 400)
        elif shares < 0:
            return apology("must be greater than 0", 400)

        # Check for correct symbol
        quote = lookup(symbol.lower())
        if quote == None:
            return apology("must input correct symbol")
        
        # Check enough cash
        total = quote["price"] * shares
        user_id = session["user_id"]
        cash = db.execute("SELECT cash FROM users WHERE id = ?", user_id)[0]["cash"]
        if total > cash:
            return apology("cant afford", 400)
        else:
            # Update database
            cash_left = cash - total
            db.execute("UPDATE users SET cash = ? WHERE id = ?", cash_left, user_id)
            db.execute("INSERT INTO transactions(user_id, symbol, name, price, shares) VALUES(?, ?, ?, ?, ?)", user_id, quote["symbol"], quote["name"], quote["price"], shares)
            owned = db.execute("SELECT * FROM owned WHERE user_id = ? AND symbol = ?", user_id, quote["symbol"])
            if owned:
                # update_shares = owned[0]["shares"] + shares
                db.execute("UPDATE owned SET shares = shares + ? WHERE user_id = ? AND symbol = ?", shares, user_id, quote["symbol"].upper())
            elif not owned:
                db.execute("INSERT INTO owned(user_id, symbol, name, shares) Values(?, ?, ?, ?)", user_id, quote["symbol"].upper(), quote["name"], shares)

            return view_portfolio(session["user_id"])


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""

    history = db.execute("SELECT time, symbol, price, shares FROM transactions WHERE user_id = ?", session["user_id"])
    return render_template("history.html", history = history)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "GET":
        return render_template("quote.html")
    else:
        symbol = request.form.get("symbol").lower()
        symbol_quote = lookup(symbol)
        price_quote = f'A share of {symbol_quote["name"]} ({symbol_quote["symbol"]}) costs ${symbol_quote["price"]}'
        return render_template("message.html", message = price_quote)


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    if request.method == "GET":
        return render_template("register.html")
    else:
        # Check for invalid inputs.
        if not request.form.get("username"):
            return apology("must provide username", 403)

        elif db.execute("SELECT username FROM users WHERE username = ?", request.form.get("username")):
            return apology("that username has already been taken", 403)
        
        elif not request.form.get("password") or not request.form.get("password_repeated"):
            return apology("must input password correctly", 403)

        elif request.form.get("password") != request.form.get("password_repeated"):
            return apology("passwords do not match", 403)
        
        hashedPassword = generate_password_hash(request.form.get("password"))
        db.execute('INSERT INTO users ("username", "hash") VALUES(?, ?)', request.form.get("username"), hashedPassword)
        
        return view_portfolio(session["user_id"])


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    if request.method == "GET":
        portfolio = db.execute("SELECT * FROM owned WHERE user_id = ? AND shares > 0", session["user_id"])
        for row in portfolio:
            price = lookup(row["symbol"])["price"]
            row["price"] = price
        return render_template("sell.html", portfolio = portfolio)
    else:
        symbol = request.form.get("share_selected")
        shares = float(request.form.get("shares"))

        if not symbol:
            return apology("must select shares", 400)
        elif not shares:
            return apology("must input number of shares", 400)
        elif shares < 0.0:
            return apology("number of shares must be above 0", 400)


        owned_shares = db.execute("SELECT shares FROM owned WHERE user_id = ? AND symbol = ?", session["user_id"], symbol)[0]["shares"]
        if not owned_shares:
            return apology("select correct stock", 400)
        elif owned_shares < shares:
            return apology("not enough shares", 400)
        elif owned_shares >= shares:
            quote = lookup(symbol)
            # Update sell table
            db.execute('INSERT INTO transactions(user_id, symbol, name, price, shares) Values(?, ?, ?, ?, ?)', session["user_id"], symbol, quote["name"], quote["price"], shares)

            # update owned table
            db.execute('UPDATE owned SET shares = shares - ? WHERE user_id = ? AND symbol = ?', shares, session["user_id"], symbol)

            # update cash
            db.execute('UPDATE users SET cash = cash + ? WHERE id = ?', quote["price"] * shares, session["user_id"])

        return view_portfolio(session["user_id"])


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
