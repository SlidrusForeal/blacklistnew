from werkzeug.security import generate_password_hash

# Admin credentials
admins = [
    ('AmphiprionHempfAlexandrChangrettoK1zikBrunoIT', 'riwfJU-2z3PdEQh', 'owner'),
    ('ItGoi', 'cmw037ZuEq3efc_', 'admin'),
    ('prokuror', 'v_eeR5RuwM9rEVy', 'moderator')
]

print("-- Insert blacklist entry")
print("INSERT INTO blacklist_entry (id, nickname, uuid, reason, created_at)")
print("VALUES (1, 'K1zik', '91676fae2a454dc2b92e6bda76d31cb5', 'Хуесос на детективе', '2025-04-18 03:01:38');")
print("\n-- Insert admin users with properly hashed passwords")
print("INSERT INTO admin_user (username, password_hash, role) VALUES")

for i, (username, password, role) in enumerate(admins):
    password_hash = generate_password_hash(password)
    comma = ',' if i < len(admins) - 1 else ';'
    print(f"('{username}', '{password_hash}', '{role}'){comma}")

print("\n-- Reset the sequence for blacklist_entry to start after our inserted data")
print("SELECT setval('blacklist_entry_id_seq', (SELECT MAX(id) FROM blacklist_entry));") 