-- Where the current contents of each input table came from (synthetic seed or a user upload).
-- Shown by GET /datasets/status. One row per dataset: cbse_results, jan_aadhaar_members, ground_truth.
CREATE TABLE IF NOT EXISTS dataset_sources (
    dataset                TEXT PRIMARY KEY,
    source                 TEXT NOT NULL,   -- synthetic / uploaded / cleared
    filename               TEXT,
    row_count              INTEGER,
    uploaded_at            TIMESTAMP,
    checksum               TEXT,            -- SHA-256 of the uploaded/seeded file content
    note                   TEXT
);

-- Databases seeded before this migration: record their current contents as synthetic.
INSERT INTO dataset_sources (dataset, source, filename, row_count, uploaded_at, checksum, note)
SELECT dataset, 'synthetic',
       CASE dataset WHEN 'cbse_results' THEN 'cbse_passed_2025_26.csv.gz'
                    WHEN 'jan_aadhaar_members' THEN 'jan_aadhaar_members.csv.gz'
                    ELSE 'ground_truth.csv.gz' END,
       row_count, loaded_at, checksum, 'bundled synthetic data (data/)'
FROM seed_meta WHERE dataset IN ('cbse_results', 'jan_aadhaar_members', 'ground_truth');
