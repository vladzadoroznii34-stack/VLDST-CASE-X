CREATE TABLE IF NOT EXISTS users(
 id BIGSERIAL PRIMARY KEY,
 telegram_id BIGINT UNIQUE NOT NULL,
 username TEXT DEFAULT '',
 first_name TEXT DEFAULT '',
 coins BIGINT NOT NULL DEFAULT 5000,
 xp BIGINT NOT NULL DEFAULT 0,
 level INT NOT NULL DEFAULT 1,
 tickets INT NOT NULL DEFAULT 0,
 daily_streak INT NOT NULL DEFAULT 0,
 last_daily DATE,
 premium BOOLEAN NOT NULL DEFAULT FALSE,
 season_pass BOOLEAN NOT NULL DEFAULT FALSE,
 xp_boost_until TIMESTAMPTZ,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS cases(
 case_code TEXT PRIMARY KEY,
 name TEXT NOT NULL,
 price BIGINT NOT NULL,
 theme TEXT NOT NULL,
 unlock_level INT NOT NULL,
 active BOOLEAN DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS items(
 item_code TEXT PRIMARY KEY,
 case_code TEXT REFERENCES cases(case_code),
 name TEXT NOT NULL,
 rarity TEXT NOT NULL,
 chance NUMERIC NOT NULL,
 sell_price BIGINT NOT NULL,
 visual_theme TEXT NOT NULL,
 visual_seed TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS inventory(
 user_id BIGINT REFERENCES users(id) ON DELETE CASCADE,
 item_code TEXT REFERENCES items(item_code),
 quantity BIGINT NOT NULL DEFAULT 0,
 pinned BOOLEAN NOT NULL DEFAULT FALSE,
 acquired_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 PRIMARY KEY(user_id,item_code)
);

CREATE TABLE IF NOT EXISTS case_openings(
 id BIGSERIAL PRIMARY KEY,
 user_id BIGINT REFERENCES users(id),
 request_id TEXT NOT NULL,
 case_code TEXT NOT NULL,
 results_json JSONB NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 UNIQUE(user_id,request_id)
);

CREATE TABLE IF NOT EXISTS economy_transactions(
 id BIGSERIAL PRIMARY KEY,
 user_id BIGINT REFERENCES users(id),
 kind TEXT NOT NULL,
 amount BIGINT NOT NULL,
 meta TEXT,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS mission_claims(
 user_id BIGINT REFERENCES users(id) ON DELETE CASCADE,
 mission_id TEXT NOT NULL,
 reward BIGINT NOT NULL,
 claimed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 PRIMARY KEY(user_id,mission_id)
);

CREATE TABLE IF NOT EXISTS achievement_claims(
 user_id BIGINT REFERENCES users(id) ON DELETE CASCADE,
 achievement_id TEXT NOT NULL,
 reward BIGINT NOT NULL,
 claimed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 PRIMARY KEY(user_id,achievement_id)
);

CREATE TABLE IF NOT EXISTS season_claims(
 user_id BIGINT REFERENCES users(id) ON DELETE CASCADE,
 level INT NOT NULL,
 reward BIGINT NOT NULL,
 premium BOOLEAN NOT NULL DEFAULT FALSE,
 claimed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 PRIMARY KEY(user_id,level,premium)
);

CREATE TABLE IF NOT EXISTS referrals(
 id BIGSERIAL PRIMARY KEY,
 referrer_id BIGINT REFERENCES users(id),
 referred_id BIGINT UNIQUE REFERENCES users(id),
 active BOOLEAN DEFAULT FALSE,
 earned BIGINT DEFAULT 0,
 created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS payments(
 id BIGSERIAL PRIMARY KEY,
 user_id BIGINT REFERENCES users(id),
 payment_id TEXT UNIQUE,
 payload TEXT NOT NULL,
 currency TEXT,
 amount INT,
 status TEXT,
 created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Safe migration for databases created by older VLDST CASE X builds.
ALTER TABLE users ADD COLUMN IF NOT EXISTS blocked BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS premium BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS season_pass BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS xp_boost_until TIMESTAMPTZ;


-- V5 admin / advertising / mini-games / audit
CREATE TABLE IF NOT EXISTS admin_audit(
 id BIGSERIAL PRIMARY KEY,
 admin_user_id BIGINT,
 action TEXT NOT NULL,
 target_user_id BIGINT,
 meta JSONB NOT NULL DEFAULT '{}'::jsonb,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS ad_campaigns(
 id BIGSERIAL PRIMARY KEY,
 title TEXT NOT NULL,
 description TEXT NOT NULL DEFAULT '',
 reward BIGINT NOT NULL DEFAULT 0,
 url TEXT NOT NULL DEFAULT '',
 daily_limit INT NOT NULL DEFAULT 1,
 cooldown_seconds INT NOT NULL DEFAULT 86400,
 active BOOLEAN NOT NULL DEFAULT TRUE,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS ad_claims(
 user_id BIGINT REFERENCES users(id) ON DELETE CASCADE,
 ad_id BIGINT REFERENCES ad_campaigns(id) ON DELETE CASCADE,
 claimed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 PRIMARY KEY(user_id,ad_id,claimed_at)
);
CREATE TABLE IF NOT EXISTS game_plays(
 id BIGSERIAL PRIMARY KEY,
 user_id BIGINT REFERENCES users(id) ON DELETE CASCADE,
 game_code TEXT NOT NULL,
 reward BIGINT NOT NULL DEFAULT 0,
 result TEXT NOT NULL DEFAULT '',
 request_id TEXT NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 UNIQUE(user_id,game_code,request_id)
);


-- V6 platform indexes / state
CREATE INDEX IF NOT EXISTS idx_case_openings_user_created ON case_openings(user_id,created_at DESC);
CREATE INDEX IF NOT EXISTS idx_transactions_user_created ON economy_transactions(user_id,created_at DESC);
CREATE INDEX IF NOT EXISTS idx_payments_status_created ON payments(status,created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ads_active ON ad_campaigns(active);
CREATE INDEX IF NOT EXISTS idx_game_plays_user_day ON game_plays(user_id,created_at DESC);


-- V10.1 final monetization / promo / economy tools
CREATE TABLE IF NOT EXISTS promo_codes(
 id BIGSERIAL PRIMARY KEY,
 code TEXT UNIQUE NOT NULL,
 reward_coins BIGINT NOT NULL DEFAULT 0,
 reward_xp BIGINT NOT NULL DEFAULT 0,
 reward_premium BOOLEAN NOT NULL DEFAULT FALSE,
 max_uses INT NOT NULL DEFAULT 1,
 used_count INT NOT NULL DEFAULT 0,
 active BOOLEAN NOT NULL DEFAULT TRUE,
 expires_at TIMESTAMPTZ,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS promo_redemptions(
 promo_id BIGINT REFERENCES promo_codes(id) ON DELETE CASCADE,
 user_id BIGINT REFERENCES users(id) ON DELETE CASCADE,
 redeemed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 PRIMARY KEY(promo_id,user_id)
);
CREATE INDEX IF NOT EXISTS idx_promo_active ON promo_codes(active,expires_at);
CREATE INDEX IF NOT EXISTS idx_promo_redemptions_user ON promo_redemptions(user_id,redeemed_at DESC);


-- V10 social world / DNA / legacy / events / forge / creator systems
CREATE TABLE IF NOT EXISTS player_world(
 user_id BIGINT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
 core_level INT NOT NULL DEFAULT 1,
 reactor_level INT NOT NULL DEFAULT 1,
 vault_level INT NOT NULL DEFAULT 1,
 forge_level INT NOT NULL DEFAULT 1,
 points BIGINT NOT NULL DEFAULT 0,
 updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS player_dna(
 user_id BIGINT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
 inferno INT NOT NULL DEFAULT 0,
 neon INT NOT NULL DEFAULT 0,
 galaxy INT NOT NULL DEFAULT 0,
 collector INT NOT NULL DEFAULT 0,
 social INT NOT NULL DEFAULT 0,
 updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS player_factions(
 user_id BIGINT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
 faction TEXT NOT NULL,
 joined_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS global_events(
 id BIGSERIAL PRIMARY KEY,
 code TEXT UNIQUE NOT NULL,
 title TEXT NOT NULL,
 description TEXT NOT NULL DEFAULT '',
 target BIGINT NOT NULL DEFAULT 0,
 progress BIGINT NOT NULL DEFAULT 0,
 reward BIGINT NOT NULL DEFAULT 0,
 ends_at TIMESTAMPTZ NOT NULL,
 active BOOLEAN NOT NULL DEFAULT TRUE
);
CREATE TABLE IF NOT EXISTS event_contributions(
 event_id BIGINT REFERENCES global_events(id) ON DELETE CASCADE,
 user_id BIGINT REFERENCES users(id) ON DELETE CASCADE,
 points BIGINT NOT NULL DEFAULT 0,
 updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 PRIMARY KEY(event_id,user_id)
);
CREATE TABLE IF NOT EXISTS item_history(
 id BIGSERIAL PRIMARY KEY,
 user_id BIGINT REFERENCES users(id) ON DELETE SET NULL,
 item_code TEXT REFERENCES items(item_code) ON DELETE SET NULL,
 action TEXT NOT NULL,
 meta JSONB NOT NULL DEFAULT '{}'::jsonb,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS forge_recipes(
 recipe_id TEXT PRIMARY KEY,
 title TEXT NOT NULL,
 result_item_code TEXT REFERENCES items(item_code),
 ingredients JSONB NOT NULL,
 cost BIGINT NOT NULL DEFAULT 0,
 active BOOLEAN NOT NULL DEFAULT TRUE
);
CREATE TABLE IF NOT EXISTS creator_codes(
 code TEXT PRIMARY KEY,
 owner_user_id BIGINT REFERENCES users(id) ON DELETE SET NULL,
 uses BIGINT NOT NULL DEFAULT 0,
 reward BIGINT NOT NULL DEFAULT 0,
 active BOOLEAN NOT NULL DEFAULT TRUE,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS creator_uses(
 code TEXT REFERENCES creator_codes(code) ON DELETE CASCADE,
 user_id BIGINT REFERENCES users(id) ON DELETE CASCADE,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 PRIMARY KEY(code,user_id)
);
ALTER TABLE users ADD COLUMN IF NOT EXISTS legacy_level INT NOT NULL DEFAULT 0;
ALTER TABLE users ADD COLUMN IF NOT EXISTS faction_points BIGINT NOT NULL DEFAULT 0;
CREATE INDEX IF NOT EXISTS idx_event_contributions_event ON event_contributions(event_id,points DESC);
CREATE INDEX IF NOT EXISTS idx_item_history_item ON item_history(item_code,created_at DESC);
