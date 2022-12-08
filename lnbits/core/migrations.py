from sqlalchemy.exc import OperationalError  # type: ignore


async def m000_create_migrations_table(db):
    await db.execute(
        """
    CREATE TABLE IF NOT EXISTS dbversions (
        db TEXT PRIMARY KEY,
        version INT NOT NULL
    )
    """
    )


async def m001_initial(db):
    """
    Initial LNbits tables.
    """
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS accounts (
            id TEXT PRIMARY KEY,
            email TEXT,
            pass TEXT
        );
    """
    )
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS extensions (
            "user" TEXT NOT NULL,
            extension TEXT NOT NULL,
            active BOOLEAN DEFAULT false,

            UNIQUE ("user", extension)
        );
    """
    )
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS wallets (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            "user" TEXT NOT NULL,
            adminkey TEXT NOT NULL,
            inkey TEXT
        );
    """
    )
    await db.execute(
        f"""
        CREATE TABLE IF NOT EXISTS apipayments (
            payhash TEXT NOT NULL,
            amount {db.big_int} NOT NULL,
            fee INTEGER NOT NULL DEFAULT 0,
            wallet TEXT NOT NULL,
            pending BOOLEAN NOT NULL,
            memo TEXT,
            time TIMESTAMP NOT NULL DEFAULT {db.timestamp_now},
            UNIQUE (wallet, payhash)
        );
    """
    )

    await db.execute(
        """
        CREATE VIEW balances AS
        SELECT wallet, COALESCE(SUM(s), 0) AS balance FROM (
            SELECT wallet, SUM(amount) AS s  -- incoming
            FROM apipayments
            WHERE amount > 0 AND pending = false  -- don't sum pending
            GROUP BY wallet
            UNION ALL
            SELECT wallet, SUM(amount + fee) AS s  -- outgoing, sum fees
            FROM apipayments
            WHERE amount < 0  -- do sum pending
            GROUP BY wallet
        )x
        GROUP BY wallet;
    """
    )


async def m002_add_fields_to_apipayments(db):
    """
    Adding fields to apipayments for better accounting,
    and renaming payhash to checking_id since that is what it really is.
    """
    try:
        await db.execute("ALTER TABLE apipayments RENAME COLUMN payhash TO checking_id")
        await db.execute("ALTER TABLE apipayments ADD COLUMN hash TEXT")
        await db.execute("CREATE INDEX by_hash ON apipayments (hash)")
        await db.execute("ALTER TABLE apipayments ADD COLUMN preimage TEXT")
        await db.execute("ALTER TABLE apipayments ADD COLUMN bolt11 TEXT")
        await db.execute("ALTER TABLE apipayments ADD COLUMN extra TEXT")

        import json

        rows = await (await db.execute("SELECT * FROM apipayments")).fetchall()
        for row in rows:
            if not row["memo"] or not row["memo"].startswith("#"):
                continue

            for ext in ["withdraw", "events", "lnticket", "paywall", "tpos"]:
                prefix = "#" + ext + " "
                if row["memo"].startswith(prefix):
                    new = row["memo"][len(prefix) :]
                    await db.execute(
                        """
                        UPDATE apipayments SET extra = ?, memo = ?
                        WHERE checking_id = ? AND memo = ?
                        """,
                        (
                            json.dumps({"tag": ext}),
                            new,
                            row["checking_id"],
                            row["memo"],
                        ),
                    )
                    break
    except OperationalError:
        # this is necessary now because it may be the case that this migration will
        # run twice in some environments.
        # catching errors like this won't be necessary in anymore now that we
        # keep track of db versions so no migration ever runs twice.
        pass


async def m003_add_invoice_webhook(db):
    """
    Special column for webhook endpoints that can be assigned
    to each different invoice.
    """

    await db.execute("ALTER TABLE apipayments ADD COLUMN webhook TEXT")
    await db.execute("ALTER TABLE apipayments ADD COLUMN webhook_status TEXT")


async def m004_ensure_fees_are_always_negative(db):
    """
    Use abs() so wallet backends don't have to care about the sign of the fees.
    """

    await db.execute("DROP VIEW balances")
    await db.execute(
        """
        CREATE VIEW balances AS
        SELECT wallet, COALESCE(SUM(s), 0) AS balance FROM (
            SELECT wallet, SUM(amount) AS s  -- incoming
            FROM apipayments
            WHERE amount > 0 AND pending = false  -- don't sum pending
            GROUP BY wallet
            UNION ALL
            SELECT wallet, SUM(amount - abs(fee)) AS s  -- outgoing, sum fees
            FROM apipayments
            WHERE amount < 0  -- do sum pending
            GROUP BY wallet
        )x
        GROUP BY wallet;
    """
    )


async def m005_balance_check_balance_notify(db):
    """
    Keep track of balanceCheck-enabled lnurl-withdrawals to be consumed by an LNbits wallet and of balanceNotify URLs supplied by users to empty their wallets.
    """

    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS balance_check (
          wallet TEXT NOT NULL REFERENCES wallets (id),
          service TEXT NOT NULL,
          url TEXT NOT NULL,

          UNIQUE(wallet, service)
        );
    """
    )

    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS balance_notify (
          wallet TEXT NOT NULL REFERENCES wallets (id),
          url TEXT NOT NULL,

          UNIQUE(wallet, url)
        );
    """
    )


async def m006_create_admin_settings_table(db):
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS settings (
            super_user TEXT,
            lnbits_admin_extensions TEXT,
            lnbits_admin_users TEXT,
            lnbits_allowed_users TEXT,
            lnbits_disabled_extensions TEXT,
            lnbits_site_title TEXT,
            lnbits_site_tagline TEXT,
            lnbits_site_description TEXT,
            lnbits_default_wallet_name TEXT,
            lnbits_theme_options TEXT,
            lnbits_custom_logo TEXT,
            lnbits_ad_space TEXT,
            lnbits_ad_space_title TEXT,
            lnbits_ad_space_enabled BOOLEAN,
            lnbits_force_https TEXT,
            lnbits_reserve_fee_min TEXT,
            lnbits_reserve_fee_percent TEXT,
            lnbits_service_fee TEXT,
            lnbits_hide_api TEXT,
            lnbits_denomination TEXT,
            lnbits_backend_wallet_class TEXT,
            lnbits_endpoint TEXT,
            lnbits_key TEXT,
            fake_wallet_secret TEXT,
            cliche_endpoint TEXT,
            corelightning_rpc TEXT,
            eclair_url TEXT,
            eclair_pass TEXT,
            lnd_cert TEXT,
            lnd_admin_macaroon TEXT,
            lnd_invoice_macaroon TEXT,
            lnd_rest_endpoint TEXT,
            lnd_rest_cert TEXT,
            lnd_rest_macaroon TEXT,
            lnd_rest_macaroon_encrypted TEXT,
            lnd_grpc_endpoint TEXT,
            lnd_grpc_cert TEXT,
            lnd_grpc_port INTEGER,
            lnd_grpc_admin_macaroon TEXT,
            lnd_grpc_invoice_macaroon TEXT,
            lnd_grpc_macaroon TEXT,
            lnd_grpc_macaroon_encrypted TEXT,
            lnpay_api_endpoint TEXT,
            lnpay_api_key TEXT,
            lnpay_wallet_key TEXT,
            lntxbot_api_endpoint TEXT,
            lntxbot_key TEXT,
            opennode_api_endpoint TEXT,
            opennode_key TEXT,
            spark_url TEXT,
            spark_token TEXT,
            boltz_network TEXT,
            boltz_url TEXT,
            boltz_mempool_space_url TEXT,
            boltz_mempool_space_url_ws TEXT,
            lntips_api_endpoint TEXT,
            lntips_api_key TEXT,
            lntips_admin_key TEXT,
            lntips_invoice_key TEXT
        );
    """
    )
