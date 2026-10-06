-- =============================================================================
-- 02-seed.sql
--
-- Seeds enough data for the app to be immediately usable and for the
-- Grafana dashboard's "total products" panel to show something real:
--   - 3 sample products (product-service's catalog), each with matching
--     inventory stock (inventory-service) so they can actually be ordered.
--   - An admin login for user-service:
--       email:    admin@example.com
--       password: password123
--     Stored as a bcrypt hash (never plaintext), generated with the same
--     algorithm user-service verifies against at login (passlib's
--     CryptContext(schemes=["bcrypt"])).
--
-- Change this password (or remove this user) before using this anywhere
-- other than local development.
-- =============================================================================

INSERT INTO product (id, name, price, description, image_url)
VALUES
    (1, 'Super Fast Laptop', 1999.99, 'A high-performance laptop for developers who refuse to wait for anything to compile.', 'https://images.unsplash.com/photo-1517336714731-489689fd1ca8?w=600&q=80'),
    (2, 'Wireless Mechanical Keyboard', 129.99, 'Hot-swappable switches, per-key RGB, and a satisfying amount of clack.', 'https://images.unsplash.com/photo-1587829741301-dc798b83add3?w=600&q=80'),
    (3, 'Ultra-Wide Monitor', 549.99, '34" curved display, because one monitor was never really enough.', 'https://images.unsplash.com/photo-1527443224154-c4a3942d3acf?w=600&q=80')
ON CONFLICT (id) DO NOTHING;

-- Keep the id sequence consistent with the explicit ids inserted above, so
-- the next product created through the app doesn't collide with id 1/2/3.
SELECT setval(pg_get_serial_sequence('product', 'id'), (SELECT MAX(id) FROM product));

INSERT INTO inventory (product_id, stock)
VALUES
    (1, 25),
    (2, 100),
    (3, 40)
ON CONFLICT (product_id) DO NOTHING;

INSERT INTO "user" (name, email, password, role)
SELECT
    'Admin User',
    'admin@example.com',
    '$2b$10$ld7TkLvMTc2VA8Rn//jbSu1m6Xa7ddTryqce6M7oRmS48IdaU2Sbu',
    'admin'
WHERE NOT EXISTS (
    SELECT 1 FROM "user" WHERE email = 'admin@example.com'
);
