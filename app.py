import os
import sqlite3
import datetime as dt
from flask import Flask, request, jsonify, render_template
from dotenv import load_dotenv

# --- Plaid SDK (v24+) imports ---
from plaid.api import plaid_api
from plaid import Configuration, ApiClient
from plaid.exceptions import ApiException

from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
from plaid.model.products import Products
from plaid.model.country_code import CountryCode
from plaid.model.item_public_token_exchange_request import (
    ItemPublicTokenExchangeRequest,
)
from plaid.model.item_get_request import ItemGetRequest
from plaid.model.institutions_get_by_id_request import InstitutionsGetByIdRequest
from plaid.model.item_remove_request import ItemRemoveRequest

# ------------------------------------------------------------------------------
# Config & setup
# ------------------------------------------------------------------------------

load_dotenv()

PLAID_CLIENT_ID = os.getenv("PLAID_CLIENT_ID")
PLAID_SECRET = os.getenv("PLAID_SECRET")
PLAID_ENV = os.getenv("PLAID_ENV", "sandbox")  # sandbox | development | production
PLAID_REDIRECT_URI = os.getenv(
    "PLAID_REDIRECT_URI"
)  # e.g. https://localhost:5000/oauth-return

PLAID_ENV_URLS = {
    "SANDBOX": "https://sandbox.plaid.com",
    "DEVELOPMENT": "https://development.plaid.com",
    "PRODUCTION": "https://production.plaid.com",
}

conf = Configuration(
    host=PLAID_ENV_URLS[PLAID_ENV.upper()],
    api_key={"clientId": PLAID_CLIENT_ID, "secret": PLAID_SECRET},
)
client = plaid_api.PlaidApi(ApiClient(conf))

app = Flask(__name__, template_folder="templates")

# Simple on-disk store for item/access tokens (demo use only)
TOK_DB = ".tokens.sqlite"
tok_conn = sqlite3.connect(TOK_DB, check_same_thread=False)
tok_conn.execute(
    """CREATE TABLE IF NOT EXISTS items(
         item_id TEXT PRIMARY KEY,
         access_token TEXT NOT NULL,
         institution_id TEXT,
         institution_name TEXT,
         created_utc TEXT NOT NULL
       )"""
)
tok_conn.commit()

# ------------------------------------------------------------------------------
# Pages
# ------------------------------------------------------------------------------


@app.get("/")
def home():
    # Fancy Tailwind UI listing items, link-new & relink buttons
    return render_template("home.html")


@app.get("/oauth-return")
def oauth_return_page():
    # OAuth completes here; page resumes Link with receivedRedirectUri
    return render_template("oauth_return.html")


# ------------------------------------------------------------------------------
# API: Link token (create & update), token exchange, items listing
# ------------------------------------------------------------------------------


@app.route("/link_token/create", methods=["POST", "OPTIONS"])
def link_token_create():
    if request.method == "OPTIONS":
        return ("", 204)

    req_kwargs = dict(
        user=LinkTokenCreateRequestUser(
            client_user_id="user-123"
        ),  # replace with your real user id
        client_name="Personal Finance ETL",
        products=[Products("transactions")],
        country_codes=[CountryCode("GB")],
        language="en",
        # webhook="https://your-public-url/webhook",  # optional
    )
    # UK/EU OAuth requires HTTPS redirect URI exactly matching the dashboard
    if PLAID_REDIRECT_URI:
        req_kwargs["redirect_uri"] = PLAID_REDIRECT_URI

    try:
        req = LinkTokenCreateRequest(**req_kwargs)
        resp = client.link_token_create(req).to_dict()
        return jsonify(resp)
    except ApiException as e:
        # Bubble Plaid error body back for easy debugging
        return jsonify({"plaid_error": e.body}), e.status
    except Exception as e:
        return jsonify({"error": repr(e)}), 500


@app.post("/link_token/update")
def link_token_update():
    data = request.get_json(force=True)
    item_id = data["item_id"]
    row = tok_conn.execute(
        "SELECT access_token FROM items WHERE item_id=?", (item_id,)
    ).fetchone()
    if not row:
        return jsonify({"error": "unknown item"}), 404
    access_token = row[0]

    req_kwargs = dict(
        user=LinkTokenCreateRequestUser(client_user_id="user-123"),
        client_name="Personal Finance ETL",
        products=[Products("transactions")],
        country_codes=[CountryCode("GB")],
        language="en",
        access_token=access_token,  # <-- update mode
    )
    if PLAID_REDIRECT_URI:
        req_kwargs["redirect_uri"] = PLAID_REDIRECT_URI

    try:
        req = LinkTokenCreateRequest(**req_kwargs)
        resp = client.link_token_create(req).to_dict()
        return jsonify(resp)
    except ApiException as e:
        return jsonify({"plaid_error": e.body}), e.status
    except Exception as e:
        return jsonify({"error": repr(e)}), 500


@app.post("/item/remove")
def item_remove():
    data = request.get_json(force=True)
    item_id = data["item_id"]

    row = tok_conn.execute(
        "SELECT access_token FROM items WHERE item_id=?", (item_id,)
    ).fetchone()
    if not row:
        return jsonify({"error": "unknown item"}), 404
    access_token = row[0]

    try:
        # 1) Revoke access at Plaid
        client.item_remove(ItemRemoveRequest(access_token=access_token))

        # 2) Remove from local token store
        tok_conn.execute("DELETE FROM items WHERE item_id=?", (item_id,))
        tok_conn.commit()

        return jsonify({"removed": True})
    except ApiException as e:
        return jsonify({"plaid_error": e.body}), e.status
    except Exception as e:
        return jsonify({"error": repr(e)}), 500


@app.post("/item/purge")
def item_purge():
    data = request.get_json(force=True)
    item_id = data["item_id"]
    # remove the Item first
    row = tok_conn.execute(
        "SELECT access_token FROM items WHERE item_id=?", (item_id,)
    ).fetchone()
    if row:
        try:
            client.item_remove(ItemRemoveRequest(access_token=row[0]))
        except ApiException:
            pass
    tok_conn.execute("DELETE FROM items WHERE item_id=?", (item_id,))
    tok_conn.commit()

    # also purge from finance.db if you use it
    try:
        import sqlite3

        fconn = sqlite3.connect("finance.db")
        fcur = fconn.cursor()
        # assuming accounts table has item_id; otherwise map account_ids first
        fcur.execute(
            "DELETE FROM transactions WHERE account_id IN (SELECT account_id FROM accounts WHERE item_id=?)",
            (item_id,),
        )
        fcur.execute("DELETE FROM accounts WHERE item_id=?", (item_id,))
        fconn.commit()
        fconn.close()
    except Exception:
        pass

    return jsonify({"purged": True})


@app.post("/item/public_token/exchange")
def public_token_exchange():
    data = request.get_json(force=True)
    public_token = data["public_token"]
    institution = data.get(
        "institution"
    )  # {institution_id, name} from Link metadata (optional)

    try:
        exchange = client.item_public_token_exchange(
            ItemPublicTokenExchangeRequest(public_token=public_token)
        ).to_dict()

        item_id = exchange["item_id"]
        access_token = exchange["access_token"]

        tok_conn.execute(
            """INSERT OR REPLACE INTO items(
                   item_id, access_token, institution_id, institution_name, created_utc
               ) VALUES (?,?,?,?,?)""",
            (
                item_id,
                access_token,
                (institution or {}).get("institution_id"),
                (institution or {}).get("name"),
                dt.datetime.utcnow().isoformat(),
            ),
        )
        tok_conn.commit()
        return jsonify({"item_id": item_id})
    except ApiException as e:
        return jsonify({"plaid_error": e.body}), e.status
    except Exception as e:
        return jsonify({"error": repr(e)}), 500


@app.get("/items")
def list_items():
    rows = tok_conn.execute(
        "SELECT item_id, access_token, institution_id, institution_name FROM items"
    ).fetchall()

    out = []
    for item_id, access_token, inst_id, inst_name in rows:
        consent_expiry = None

        # Get consent expiry (if provided for your region)
        try:
            item = client.item_get(ItemGetRequest(access_token=access_token)).to_dict()[
                "item"
            ]
            consent_expiry = item.get("consent_expiration_time")
            if not inst_id and item.get("institution_id"):
                inst_id = item.get("institution_id")
        except ApiException:
            pass

        # If we don't have the readable institution name, fetch once and cache it
        if not inst_name and inst_id:
            try:
                inst = client.institutions_get_by_id(
                    InstitutionsGetByIdRequest(
                        institution_id=inst_id, country_codes=[CountryCode("GB")]
                    )
                ).to_dict()
                inst_name = (inst.get("institution") or {}).get("name")
                if inst_name:
                    tok_conn.execute(
                        "UPDATE items SET institution_name=? WHERE item_id=?",
                        (inst_name, item_id),
                    )
                    tok_conn.commit()
            except ApiException:
                pass

        out.append(
            {
                "item_id": item_id,
                "institution_id": inst_id,
                "institution_name": inst_name,
                "consent_expiration_time": consent_expiry,  # ISO8601 or None
            }
        )
    return jsonify(out)


# ------------------------------------------------------------------------------
# Optional: env/debug endpoint (handy while configuring)
# ------------------------------------------------------------------------------


@app.get("/debug/env")
def debug_env():
    return jsonify(
        {
            "PLAID_ENV": PLAID_ENV,
            "PLAID_CLIENT_ID_present": bool(PLAID_CLIENT_ID),
            "PLAID_SECRET_present": bool(PLAID_SECRET),
            "PLAID_REDIRECT_URI": PLAID_REDIRECT_URI,
            "host_used": conf.host,
        }
    )


# ------------------------------------------------------------------------------
# HTTPS entrypoint
# ------------------------------------------------------------------------------

if __name__ == "__main__":
    # Make sure certs/cert.pem & certs/key.pem exist (self-signed is fine for dev)
    base = os.path.dirname(os.path.abspath(__file__))
    cert_path = os.path.join(base, "certs", "cert.pem")
    key_path = os.path.join(base, "certs", "key.pem")

    app.run(
        host="localhost",
        port=5000,
        debug=True,
        ssl_context=(cert_path, key_path),
    )
