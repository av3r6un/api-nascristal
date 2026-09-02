SELECT 'PRAGMA foreign_keys=OFF;';
SELECT 'BEGIN TRANSACTION;';

SELECT CONCAT(
  'INSERT INTO onec_import_runs (exchange_type, classifier_id, source_md5, status, started_at, finished_at, created, updated) SELECT ',
  CONCAT(CHAR(39), REPLACE(exchange_type, CHAR(39), CHAR(39, 39)), CHAR(39)), ', ',
  IF(classifier_id IS NULL, 'NULL', CONCAT(CHAR(39), REPLACE(classifier_id, CHAR(39), CHAR(39, 39)), CHAR(39))), ', ',
  CONCAT(CHAR(39), REPLACE(source_md5, CHAR(39), CHAR(39, 39)), CHAR(39)), ', ',
  CONCAT(CHAR(39), REPLACE(status, CHAR(39), CHAR(39, 39)), CHAR(39)), ', ',
  IF(started_at IS NULL, 'NULL', CONCAT(CHAR(39), started_at, CHAR(39))), ', ',
  IF(finished_at IS NULL, 'NULL', CONCAT(CHAR(39), finished_at, CHAR(39))), ', ',
  IF(created IS NULL, 'NULL', CONCAT(CHAR(39), created, CHAR(39))), ', ',
  IF(updated IS NULL, 'NULL', CONCAT(CHAR(39), updated, CHAR(39))),
  ' WHERE NOT EXISTS (SELECT 1 FROM onec_import_runs WHERE source_md5 = ',
  CONCAT(CHAR(39), REPLACE(source_md5, CHAR(39), CHAR(39, 39)), CHAR(39)),
  ');'
)
FROM onec_import_runs
WHERE id IN (
  SELECT DISTINCT last_seen_import_run_id
  FROM (SELECT id, last_seen_import_run_id FROM products ORDER BY id LIMIT 5) seed_products
  WHERE last_seen_import_run_id IS NOT NULL
);

SELECT CONCAT(
  'INSERT INTO categories (eid, parent_id, name, "index", icon, created, updated) VALUES (',
  CONCAT(CHAR(39), REPLACE(eid, CHAR(39), CHAR(39, 39)), CHAR(39)), ', ',
  IF(parent_id IS NULL, 'NULL', CONCAT('(SELECT id FROM categories WHERE eid = ', CHAR(39), REPLACE((SELECT parent.eid FROM categories parent WHERE parent.id = categories.parent_id), CHAR(39), CHAR(39, 39)), CHAR(39), ')')), ', ',
  CONCAT(CHAR(39), REPLACE(name, CHAR(39), CHAR(39, 39)), CHAR(39)), ', ',
  `index`, ', ',
  CONCAT(CHAR(39), REPLACE(icon, CHAR(39), CHAR(39, 39)), CHAR(39)), ', ',
  IF(created IS NULL, 'NULL', CONCAT(CHAR(39), created, CHAR(39))), ', ',
  IF(updated IS NULL, 'NULL', CONCAT(CHAR(39), updated, CHAR(39))), ') ',
  'ON CONFLICT(eid) DO UPDATE SET parent_id = excluded.parent_id, name = excluded.name, "index" = excluded."index", icon = excluded.icon, updated = excluded.updated;'
)
FROM categories
ORDER BY parent_id IS NOT NULL, id;

SELECT CONCAT(
  'INSERT INTO properties (eid, parent_category_id, "index", name, is_active, created, updated) VALUES (',
  CONCAT(CHAR(39), REPLACE(eid, CHAR(39), CHAR(39, 39)), CHAR(39)), ', ',
  IF(parent_category_id IS NULL, 'NULL', CONCAT('(SELECT id FROM categories WHERE eid = ', CHAR(39), REPLACE((SELECT category.eid FROM categories category WHERE category.id = properties.parent_category_id), CHAR(39), CHAR(39, 39)), CHAR(39), ')')), ', ',
  `index`, ', ',
  CONCAT(CHAR(39), REPLACE(name, CHAR(39), CHAR(39, 39)), CHAR(39)), ', ',
  IF(is_active, 1, 0), ', ',
  IF(created IS NULL, 'NULL', CONCAT(CHAR(39), created, CHAR(39))), ', ',
  IF(updated IS NULL, 'NULL', CONCAT(CHAR(39), updated, CHAR(39))), ') ',
  'ON CONFLICT(eid) DO UPDATE SET parent_category_id = excluded.parent_category_id, "index" = excluded."index", name = excluded.name, is_active = excluded.is_active, updated = excluded.updated;'
)
FROM properties;

SELECT CONCAT(
  'INSERT INTO property_options (eid, property_id, value, name, icon, is_active, created, updated) VALUES (',
  CONCAT(CHAR(39), REPLACE(property_options.eid, CHAR(39), CHAR(39, 39)), CHAR(39)), ', ',
  '(SELECT id FROM properties WHERE eid = ', CONCAT(CHAR(39), REPLACE(properties.eid, CHAR(39), CHAR(39, 39)), CHAR(39)), '), ',
  CONCAT(CHAR(39), REPLACE(property_options.value, CHAR(39), CHAR(39, 39)), CHAR(39)), ', ',
  IF(property_options.name IS NULL, 'NULL', CONCAT(CHAR(39), REPLACE(property_options.name, CHAR(39), CHAR(39, 39)), CHAR(39))), ', ',
  IF(property_options.icon IS NULL, 'NULL', CONCAT(CHAR(39), REPLACE(property_options.icon, CHAR(39), CHAR(39, 39)), CHAR(39))), ', ',
  IF(property_options.is_active, 1, 0), ', ',
  IF(property_options.created IS NULL, 'NULL', CONCAT(CHAR(39), property_options.created, CHAR(39))), ', ',
  IF(property_options.updated IS NULL, 'NULL', CONCAT(CHAR(39), property_options.updated, CHAR(39))), ') ',
  'ON CONFLICT(eid) DO UPDATE SET property_id = excluded.property_id, value = excluded.value, name = excluded.name, icon = excluded.icon, is_active = excluded.is_active, updated = excluded.updated;'
)
FROM property_options
JOIN properties ON properties.id = property_options.property_id;

SELECT CONCAT(
  'INSERT INTO products (eid, sku, code, name, description, category_id, primary_image, is_active, last_seen_import_run_id, created, updated) VALUES (',
  CONCAT(CHAR(39), REPLACE(products.eid, CHAR(39), CHAR(39, 39)), CHAR(39)), ', ',
  CONCAT(CHAR(39), REPLACE(products.sku, CHAR(39), CHAR(39, 39)), CHAR(39)), ', ',
  CONCAT(CHAR(39), REPLACE(products.code, CHAR(39), CHAR(39, 39)), CHAR(39)), ', ',
  CONCAT(CHAR(39), REPLACE(products.name, CHAR(39), CHAR(39, 39)), CHAR(39)), ', ',
  IF(products.description IS NULL, 'NULL', CONCAT(CHAR(39), REPLACE(products.description, CHAR(39), CHAR(39, 39)), CHAR(39))), ', ',
  IF(categories.eid IS NULL, 'NULL', CONCAT('(SELECT id FROM categories WHERE eid = ', CHAR(39), REPLACE(categories.eid, CHAR(39), CHAR(39, 39)), CHAR(39), ')')), ', ',
  IF(products.primary_image IS NULL, 'NULL', CONCAT(CHAR(39), REPLACE(products.primary_image, CHAR(39), CHAR(39, 39)), CHAR(39))), ', ',
  IF(products.is_active, 1, 0), ', ',
  IF(onec_import_runs.source_md5 IS NULL, 'NULL', CONCAT('(SELECT id FROM onec_import_runs WHERE source_md5 = ', CHAR(39), REPLACE(onec_import_runs.source_md5, CHAR(39), CHAR(39, 39)), CHAR(39), ' LIMIT 1)')), ', ',
  IF(products.created IS NULL, 'NULL', CONCAT(CHAR(39), products.created, CHAR(39))), ', ',
  IF(products.updated IS NULL, 'NULL', CONCAT(CHAR(39), products.updated, CHAR(39))), ') ',
  'ON CONFLICT(eid) DO UPDATE SET sku = excluded.sku, code = excluded.code, name = excluded.name, description = excluded.description, category_id = excluded.category_id, primary_image = excluded.primary_image, is_active = excluded.is_active, last_seen_import_run_id = excluded.last_seen_import_run_id, updated = excluded.updated;'
)
FROM products
LEFT JOIN categories ON categories.id = products.category_id
LEFT JOIN onec_import_runs ON onec_import_runs.id = products.last_seen_import_run_id
WHERE products.id IN (SELECT id FROM (SELECT id FROM products ORDER BY id LIMIT 5) seed_products);

SELECT CONCAT(
  'INSERT INTO product_images (eid, product_id, path, sort_order, is_primary, created, updated) VALUES (',
  CONCAT(CHAR(39), REPLACE(product_images.eid, CHAR(39), CHAR(39, 39)), CHAR(39)), ', ',
  '(SELECT id FROM products WHERE eid = ', CONCAT(CHAR(39), REPLACE(products.eid, CHAR(39), CHAR(39, 39)), CHAR(39)), '), ',
  CONCAT(CHAR(39), REPLACE(product_images.path, CHAR(39), CHAR(39, 39)), CHAR(39)), ', ',
  product_images.sort_order, ', ',
  IF(product_images.is_primary, 1, 0), ', ',
  IF(product_images.created IS NULL, 'NULL', CONCAT(CHAR(39), product_images.created, CHAR(39))), ', ',
  IF(product_images.updated IS NULL, 'NULL', CONCAT(CHAR(39), product_images.updated, CHAR(39))), ') ',
  'ON CONFLICT(eid) DO UPDATE SET product_id = excluded.product_id, path = excluded.path, sort_order = excluded.sort_order, is_primary = excluded.is_primary, updated = excluded.updated;'
)
FROM product_images
JOIN products ON products.id = product_images.product_id
WHERE product_images.product_id IN (SELECT id FROM (SELECT id FROM products ORDER BY id LIMIT 5) seed_products);

SELECT CONCAT(
  'INSERT INTO product_attributes (eid, product_id, property_id, option_id, created, updated) VALUES (',
  CONCAT(CHAR(39), REPLACE(product_attributes.eid, CHAR(39), CHAR(39, 39)), CHAR(39)), ', ',
  '(SELECT id FROM products WHERE eid = ', CONCAT(CHAR(39), REPLACE(products.eid, CHAR(39), CHAR(39, 39)), CHAR(39)), '), ',
  '(SELECT id FROM properties WHERE eid = ', CONCAT(CHAR(39), REPLACE(properties.eid, CHAR(39), CHAR(39, 39)), CHAR(39)), '), ',
  IF(property_options.eid IS NULL, 'NULL', CONCAT('(SELECT id FROM property_options WHERE eid = ', CHAR(39), REPLACE(property_options.eid, CHAR(39), CHAR(39, 39)), CHAR(39), ')')), ', ',
  IF(product_attributes.created IS NULL, 'NULL', CONCAT(CHAR(39), product_attributes.created, CHAR(39))), ', ',
  IF(product_attributes.updated IS NULL, 'NULL', CONCAT(CHAR(39), product_attributes.updated, CHAR(39))), ') ',
  'ON CONFLICT(eid) DO UPDATE SET product_id = excluded.product_id, property_id = excluded.property_id, option_id = excluded.option_id, updated = excluded.updated;'
)
FROM product_attributes
JOIN products ON products.id = product_attributes.product_id
JOIN properties ON properties.id = product_attributes.property_id
LEFT JOIN property_options ON property_options.id = product_attributes.option_id
WHERE product_attributes.product_id IN (SELECT id FROM (SELECT id FROM products ORDER BY id LIMIT 5) seed_products);

SELECT CONCAT(
  'INSERT INTO offers (eid, product_id, quantity, unit, coefficient, is_active, amount, currency, created, updated) VALUES (',
  CONCAT(CHAR(39), REPLACE(offers.eid, CHAR(39), CHAR(39, 39)), CHAR(39)), ', ',
  '(SELECT id FROM products WHERE eid = ', CONCAT(CHAR(39), REPLACE(products.eid, CHAR(39), CHAR(39, 39)), CHAR(39)), '), ',
  offers.quantity, ', ',
  IF(offers.unit IS NULL, 'NULL', CONCAT(CHAR(39), REPLACE(offers.unit, CHAR(39), CHAR(39, 39)), CHAR(39))), ', ',
  offers.coefficient, ', ',
  IF(offers.is_active, 1, 0), ', ',
  offers.amount, ', ',
  IF(offers.currency IS NULL, 'NULL', CONCAT(CHAR(39), REPLACE(offers.currency, CHAR(39), CHAR(39, 39)), CHAR(39))), ', ',
  IF(offers.created IS NULL, 'NULL', CONCAT(CHAR(39), offers.created, CHAR(39))), ', ',
  IF(offers.updated IS NULL, 'NULL', CONCAT(CHAR(39), offers.updated, CHAR(39))), ') ',
  'ON CONFLICT(eid) DO UPDATE SET product_id = excluded.product_id, quantity = excluded.quantity, unit = excluded.unit, coefficient = excluded.coefficient, is_active = excluded.is_active, amount = excluded.amount, currency = excluded.currency, updated = excluded.updated;'
)
FROM offers
JOIN products ON products.id = offers.product_id
WHERE offers.product_id IN (SELECT id FROM (SELECT id FROM products ORDER BY id LIMIT 5) seed_products);

SELECT 'COMMIT;';
SELECT 'PRAGMA foreign_keys=ON;';
