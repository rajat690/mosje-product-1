# MoSJE Product 1: how to upload your own datasets

This guide is for someone who is **not a developer**. It shows how to add the new "upload" feature to
your live system, and how to load your own CBSE and Jan Aadhaar files into it.

> **Warning: never upload real government personal data to Render or GitHub.** Render and GitHub are
> public cloud services. Only upload **anonymised or synthetic** data there. Real student and family data
> must stay on government infrastructure (NIC / MeghRaj).

## What you need
* The file **mosje_upload_changes.zip** (only the new and changed files).
* Your GitHub login (repository **rajat690/mosje-product-1**) and your Render login.
* Your two files, with the column names from `templates/cbse_template.csv` and
  `templates/jan_aadhaar_template.csv`. `templates/DATA_DICTIONARY.md` explains every column.
  Accepted file types: `.csv` (in Excel: **Save As → CSV UTF-8**), `.csv.gz` or `.xlsx`.

---

## Step A: Put the changed files on GitHub, then sync Render
1. Unzip **mosje_upload_changes.zip**. You get a folder `mosje_upload_changes` with folders such as
   `api`, `dashboard`, `db`, `templates`, `tests`, `tools` and a few files such as `requirements.txt`.
2. Go to **https://github.com/rajat690/mosje-product-1** and log in.
3. Click **Add file → Upload files**.
4. Open the unzipped `mosje_upload_changes` folder. Select **everything inside it** (not the folder
   itself) and drag it into the GitHub upload box. GitHub keeps the folder paths and replaces the old
   files with the same names. Other files in the repository are not touched.
   * One file, `.env.example`, is hidden because its name starts with a dot. It is optional. To see it:
     Mac Finder **Cmd + Shift + .**; Windows File Explorer **View → Show → Hidden items**.
5. Wait until all files are listed. At the bottom, type a message such as "dataset upload" and click
   **Commit changes**.
6. Check: click into the `templates` folder in the repository. You should see three files.
7. Go to **https://dashboard.render.com**. Click **Blueprints** in the left menu, click your blueprint
   (mosje), then click **Manual sync** and confirm. (Render usually starts deploying by itself after a
   commit. The manual sync makes sure everything is up to date.)
8. Click **mosje-api**, then **Events**. Wait until the newest deploy says **Deploy live** (about
   3–5 minutes). Do the same for **mosje-dashboard**.

## Step B: Find your API key
The key is called **API_KEY**. You need it for option B below (the dashboard already knows it).
1. In Render, click **Environment Groups** (or **Env Groups**) in the left menu.
2. Click **mosje-shared**.
3. Next to **API_KEY**, click the **eye** icon (or **Reveal**) and copy the value.
   *Other way:* open **mosje-api → Environment**; API_KEY is listed there through the group.
4. Keep the key private. Do not email it or paste it into documents.

## Step C (option A, easiest): Upload through the dashboard
1. Open your dashboard address (Render → **mosje-dashboard** → the link at the top). The first visit can
   take about a minute because free services sleep.
2. Click the **Admin** tab. Scroll down to **Upload datasets**.
3. Under **CBSE passed students**, click **Browse files** and choose your CBSE file. Click
   **Upload CBSE passed students**.
   * Green message = loaded. It says how many rows were loaded.
   * Red message = **nothing was changed**. It lists what is wrong (missing columns, bad dates, unknown
     gender, and so on) and shows the first 10 bad rows with their line numbers. Fix the file and upload again.
4. Do the same under **Jan Aadhaar members**.
5. Click **Run matching (linkage + eligibility)**. Wait for **SUCCEEDED** (1–3 minutes on the free plan),
   then click **Refresh results** at the top of the Admin panel.

## Step D (option B): Upload through the API page (Swagger)
Use this if the dashboard is not available.
1. Open **https://mosje-api.onrender.com/docs** (if your API has a different address, it is shown at the
   top of the **mosje-api** page in Render; add `/docs`). Wait up to a minute if it is waking up.
2. Click the **Authorize** button (padlock, top right). Paste the API key into the **Value** box, click
   **Authorize**, then **Close**.
3. Find the **datasets** section. Click **POST /datasets/cbse/upload** to open it.
4. Click **Try it out**. Next to **file**, click **Choose File** and pick your CBSE file. Leave
   **run_pipeline** as it is.
5. Click **Execute**. Look at **Server response** below:
   * **Code 200**: loaded. `rows_loaded` shows the number of rows.
   * **Code 422**: not loaded, nothing changed. Read `missing_columns`, `problem_counts` and
     `bad_rows_sample` (line numbers in your file), fix the file and try again.
6. Repeat steps 3–5 with **POST /datasets/jan-aadhaar/upload** and your Jan Aadhaar file.
7. Open **POST /pipeline/run** (section **pipeline**), click **Try it out**, then **Execute**. Copy the
   `run_id` from the response.
8. Open **GET /pipeline/runs/{run_id}**, **Try it out**, paste the run_id, **Execute**. Repeat every
   30 seconds until `status` is **SUCCEEDED**.

## Step E: Check the results
* **Dashboard:** the grey line under the title now says **UPLOADED data**. The funnel, linkage decisions,
  eligibility, outreach queues and student drill-down show your data.
* **Precision and Recall show "n/a"**, and the Match outcomes / TP-FP-FN numbers say **"not available (no
  ground truth)"**. This is expected: real data has no answer key to check the matches against.
* **Swagger:** **GET /datasets/status** shows, for each table, whether it is `synthetic` or `uploaded`, the
  file name, the number of rows and the time it was loaded (UTC). **GET /results/funnel** shows the headline numbers.
* Your uploaded data **stays** when Render restarts the service. It is only replaced when you upload again
  or restore the synthetic data (step F).

## Step F: Go back to the synthetic data
* **Dashboard:** Admin tab → **1 · Load / restore the synthetic data**, then **2 · Run the pipeline**.
* **Swagger:** **POST /admin/seed** → Try it out → Execute, then **POST /pipeline/run** → Try it out → Execute.

Precision, recall and the match outcomes come back, because the synthetic data has a ground truth.

## Limits on the free plan
* **Upload size:** files of several hundred thousand rows upload fine. The dashboard accepts files up to
  **200 MB**. For bigger files, save them as `.csv.gz` (much smaller) or use Swagger.
* **Matching size:** the free API server has 512 MB of memory. One matching run can handle about
  **7,000 CBSE students with about 20,000 Jan Aadhaar members**, or about 4,000 students with 100,000
  members. For bigger files the upload still works, but **Run matching** refuses with a clear message.
  Split the CBSE file (for example by district) or move to a paid instance.
* The free database expires 30 days after it was created (see HOSTING_GUIDE).

## Reminder
> **Real government personal data must not go on Render or GitHub.** Use anonymised or synthetic data
> only. Real data belongs on NIC / MeghRaj.
