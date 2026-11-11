import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session, url_for
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""

    user_id = session["user_id"]

    rows = db.execute("""SELECT symbol, 
                        SUM( 
                            CASE 
                                WHEN type = 'BUY' THEN shares
                                WHEN type = 'SELL' THEN -shares
                            END
                        ) AS total_shares
                    FROM transactions
                    WHERE user_id = ?
                    GROUP BY symbol
                    HAVING total_shares > 0""", user_id)
    portfolio = []

    for row in rows:
        symbol = row["symbol"]
        shares = row["total_shares"]

        stock = lookup(symbol)
        price = stock["price"]
        total_value = shares * price

        portfolio.append({
            "symbol": symbol, 
            "shares": shares, 
            "price": price, 
            "total_value": total_value
        })

    rows = db.execute("SELECT cash FROM users WHERE id = ?", user_id)

    cash = rows[0]["cash"]

    total_portfolio = cash + sum(stock["total_value"] for stock in portfolio)

    return render_template("index.html", portfolio=portfolio, cash=cash, total_portfolio=total_portfolio)

@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""

    if request.method == "GET":
        return render_template("buy.html")
    else:
        symbol = request.form.get("symbol")
        shares = request.form.get("shares")

        if not symbol or not shares:
            return apology("Must provide symbol and shares")

        if not shares.isdigit() or int(shares) <= 0:
            return apology("Share must be a positive integer")

        shares = int(shares)

        stock = lookup(symbol)

        if stock is None:
            return apology("Invalid stock symbol")

        total_cost = stock["price"] * shares

        user_id = session["user_id"]

        rows = db.execute("SELECT cash FROM users WHERE id = ?", user_id)
        cash = rows[0]["cash"]

        if total_cost > cash:
            return apology("Not enough cash")

        db.execute("UPDATE users SET cash = cash - ? WHERE id = ?", total_cost, user_id)
        db.execute("""INSERT INTO transactions (user_id, symbol, type, shares, price) VALUES (?, ?, ?, ?, ?)""", user_id, symbol, "BUY", shares, stock["price"])
    
    return redirect("/history")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""

    user_id = session["user_id"]

    rows = db.execute("""SELECT * FROM transactions WHERE user_id = ? ORDER BY timestamp DESC""", user_id)

    return render_template("history.html", transaction=rows)


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
        rows = db.execute(
            "SELECT * FROM users WHERE username = ?", request.form.get("username")
        )

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(
            rows[0]["hash"], request.form.get("password")
        ):
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

    if request.method == 'POST':
        symbol = request.form.get("symbol")

        if not symbol:
            return apology("Must provide stock symbol")

        stock = lookup(symbol)

        if stock is None:
            return apology("Invalid stock symbol")

        return render_template("quoted.html", stock=stock)
    
    return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    if request.method == 'POST':
        username = request.form.get("username")
        password = request.form.get("password")
        confirmation = request.form.get("confirmation")

        # Check empty fields
        if not username or not password or not confirmation:
            return apology("All fields must be filled")

        # Check existing username
        rows = db.execute("SELECT * FROM users WHERE username = ?", username)

        if len(rows) > 0:
            return apology("Username has already taken")

        # Check password confirmation
        if password != confirmation:
            return apology("Password do not match. Please try again.")

        # Hash password
        hashed_password = generate_password_hash(password)

        # Insert new user into database
        try: 
            db.execute("INSERT INTO users (username, hash) VALUES (?, ?)", username, hashed_password)
        except ValueError:
            return apology("Username already taken")

        # Redirect after successful registration
        return redirect("/login")
    
    # Display registration form
    return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

    if request.method == "GET":
        user_id = session["user_id"]

        rows = db.execute("""SELECT symbol, 
                                SUM( 
                                    CASE 
                                        WHEN type = 'BUY' THEN shares
                                        WHEN type = 'SELL' THEN -shares
                                    END
                                ) AS total_shares
                            FROM transactions
                            WHERE user_id = ?
                            GROUP BY symbol
                            HAVING total_shares > 0""", user_id)
    
        return render_template("sell.html", stocks=rows)

    else:
        symbol = request.form.get("symbol")
        shares = request.form.get("shares")

        if not symbol or not shares:
            return apology("Must provide symbol and shares")

        if not shares.isdigit() or int(shares) <= 0:
            return apology("Share must be a positive integer")

        shares = int(shares)
    
        user_id = session["user_id"]

        rows = db.execute("""SELECT symbol, 
                                        SUM( 
                                            CASE 
                                                WHEN type = 'BUY' THEN shares
                                                WHEN type = 'SELL' THEN -shares
                                            END
                                        ) AS total_shares
                                    FROM transactions
                                    WHERE user_id = ?
                                    AND symbol = ?
                                    """
                                    , user_id, 
                                    symbol)

        owned_shares = rows[0]["total_shares"]

        if owned_shares is None or shares > owned_shares:
            return apology("You don't own enough shares")

        stock = lookup(symbol)

        if stock is None:
            return apology("Invalid stock symbol")

        price = stock["price"]
        total_revenue = shares * price
        
        db.execute("UPDATE users SET cash = cash + ? WHERE id = ?", total_revenue, user_id)
        db.execute("""INSERT INTO transactions (user_id, symbol, type, shares, price) VALUES (?, ?, ?, ?, ?)""", user_id, symbol, "SELL", shares, price)

    return redirect("/")