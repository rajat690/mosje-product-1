# MoSJE Product 1 platform: hosting guide (GitHub + Render)

This guide is for someone who is **not a developer**. Follow the numbered steps in order. You will put
the project files on GitHub, then Render will read them and build three things for you:

* a **database** that holds the synthetic Jan Aadhaar, CBSE and scheme data, plus the results,
* an **API**, the "engine room", which runs record linkage and eligibility,
* a **dashboard**, the web page you and your colleagues will open.

Total time: about 45 minutes the first time. Cost: **free** (read step 9 for the limits).

> Screens change. Button names on GitHub and Render may be slightly different from what is written here
> (for example "New +" instead of "New", or "Env Groups" instead of "Environment Groups"). Look for the
> closest match.

![Architecture](docs/architecture.png)

## What you need before starting
1. The file **mosje_platform.zip**. Unzip it. You will get a folder called `mosje_platform`.
2. An email address you can open. You will use it for GitHub and Render.
3. A laptop with Chrome, Edge or Firefox.

**Upload limits to know about.** On the GitHub website, each file can be at most **25 MB**, and you can
upload at most **100 files at a time**. This project is well within both limits: it has about 70 files
and the biggest one is about 0.5 MB, because the data files are compressed as `.csv.gz`. Do not unzip
the `.gz` files. The system reads them as they are.

---

## Step 1: Put the files on GitHub
1. Go to **https://github.com** and click **Sign up**. Create a free account and confirm your email.
2. When you are logged in, click the **+** at the top right, then **New repository**.
3. Fill in the form:
   * **Repository name**: `mosje-platform`
   * Choose **Private**. Render can still read private repositories, and private keeps the work out of public view.
   * Do **not** tick "Add a README", ".gitignore" or "license". The zip already contains them.
   * Click **Create repository**.
4. On the next page, click the link **uploading an existing file**. If you don't see it, use
   **Add file → Upload files**.
5. Open the unzipped `mosje_platform` folder on your computer. Select **everything inside it**: the
   folders `api`, `dashboard`, `data`, `db`, `docs`, `mosje`, `tests` and `tools`, and all the files such as
   `render.yaml` and `requirements.txt`. Drag them into the GitHub upload box.
   * **Important:** drag the *contents* of the folder, not the `mosje_platform` folder itself. The file
     `render.yaml` must end up at the **top level** of the repository, not inside a sub-folder.
   * **Hidden files.** Some files start with a dot: `.gitignore`, `.python-version`, `.env.example`,
     `.dockerignore`. On a Mac, press **Cmd + Shift + .** in Finder to show them. On Windows, go to File Explorer →
     View → Show → Hidden items. These files are helpful but not essential. The deployment still works
     without them.
6. Wait until every file shows in the list. Scroll to the bottom, type a message such as "first upload"
   and click **Commit changes**.
7. Check the result. The main page of the repository should show `render.yaml`, `README.md`,
   `requirements.txt` and the folders listed above. Click into `data` and confirm the three `.csv.gz` files and the
   `.xlsx` are there.

*Optional, for people comfortable with a terminal:*
```bash
cd mosje_platform
git init && git add . && git commit -m "MoSJE platform"
git branch -M main
git remote add origin https://github.com/<your-user>/mosje-platform.git
git push -u origin main
```

## Step 2: Sign up for Render and connect GitHub
1. Go to **https://render.com** and click **Get Started** (or **Sign up**).
2. Choose **Sign up with GitHub**. This is the easiest option because it connects the two accounts in one go.
   Approve the permissions GitHub shows you.
3. If Render asks which repositories it may see, choose **Only select repositories**, pick
   `mosje-platform` and save. You can change this later under GitHub → Settings → Applications.
4. Render may ask you to create a **workspace** (any name is fine). It may also ask for a payment card to
   verify your account. Free resources are not charged.

## Step 3: Deploy everything with the Blueprint
A "Blueprint" is the file `render.yaml` in your repository. It tells Render exactly what to build, so
you don't have to set anything up by hand.

1. In the Render dashboard, click **New** (top right), then **Blueprint**.
2. Pick the repository **mosje-platform**. If it is not listed, click **Configure account** or
   **Connect GitHub** and give Render access to it (step 2.3).
3. Give the Blueprint a name, e.g. `mosje`. Leave the branch as `main`.
4. Render shows what it will create. You should see:
   * **mosje-db**: PostgreSQL, Free
   * **mosje-api**: Web Service, Free
   * **mosje-dashboard**: Web Service, Free
   * **mosje-shared**: Environment Group (it holds the generated `API_KEY`)
5. Click **Apply** (or **Deploy Blueprint**).
6. Wait. The database is ready in a minute or two. Each web service then **builds** (installs software,
   3–6 minutes) and **deploys**. You can click a service and open **Logs** to watch.
   The API also loads the data and runs the pipeline once automatically on its first start (step 5).
7. When both web services show **Live** (green), the deployment is done.

Write down the two web addresses shown at the top of each service page. They look like:
* API: `https://mosje-api-xxxx.onrender.com` (the `-xxxx` part may not be there)
* Dashboard: `https://mosje-dashboard-xxxx.onrender.com`

## Step 4: Find your API key
The API is protected by a password-like key. Render generated it for you.

1. In Render, open **Environment Groups** (in the left menu; it may be called **Env Groups**).
2. Click **mosje-shared**.
3. Next to `API_KEY`, click the **eye** icon (or **Reveal**) and copy the value.
4. Keep it private. Share it only with people who need to call the API directly. You don't need the key to
   *view* the dashboard, because the dashboard already has it.

To change the key, edit the value in the same place and click **Save**. Render restarts both services, and
the new key applies to both automatically.

## Step 5: Load the data into the database ("seed")
**Normally you don't have to do anything.** The Blueprint sets `AUTO_SEED=true`, so on its first start the
API creates the tables and loads the synthetic data files and the scheme master by itself.

To check it, open `https://<your-api-address>/health` in the browser. You should see `"seeded": true`.

If it says `false`, or you want to reload the data, use either of these:
* **Easiest:** open the dashboard, go to the **Admin** tab and click **1 · Load (seed) the database**.
* **Or:** open `https://<your-api-address>/docs`, click **Authorize**, paste the API key and click
  **Authorize** again. Then open **POST /admin/seed**, click **Try it out**, then **Execute**. A response of
  `"status": "seeded"` or `"skipped"` (already loaded) means it worked. Setting `force` to `true` reloads
  everything and clears old results.

(Render's "Shell" and "one-off jobs" are not available on the free plan. That is why loading is done
through the API.)

## Step 6: Run the pipeline (linkage + eligibility)
**The first run also happens automatically** after the first seed (`AUTO_RUN_PIPELINE=true`).

To run it again, for example after re-seeding:
* **Dashboard:** open the **Admin** tab and click **2 · Run the pipeline**. On the free plan it takes about 1–3 minutes.
  A green "SUCCEEDED" message appears. Then click **Refresh results**.
* **Or /docs:** **POST /pipeline/run** → Try it out → Execute. Watch progress with **GET /pipeline/runs**.

## Step 7: Open the dashboard and the API docs
* **Dashboard:** `https://<your-dashboard-address>`. The tabs are Funnel, Linkage decisions, Match quality,
  Eligibility & schemes, Outreach queues, Student drill-down, **Scenarios** (matching and non-matching
  students for all 56 matrix scenarios), Compiled rules, Admin, **Match Outcomes** (the six headline match
  numbers with plain-English definitions) and **36-Scenario Matrix** (a reporting view of the earlier 36-row matrix).
* **API docs:** `https://<your-api-address>/docs`. This is an interactive page listing every endpoint.
  Click **Authorize** first.

If a page takes about a minute to open, the service was asleep. This is normal on the free plan (step 9).

## Step 8: Checklist to confirm it all works
Tick each line:
1. [ ] `https://<api>/health` shows `"status": "ok"`, `"database": "postgresql"`, `"seeded": true` and a
   `latest_run` with `"status": "SUCCEEDED"`.
2. [ ] `https://<api>/schemes` in the browser shows **401 "missing or invalid X-API-Key"**. This is good: the key protection works.
3. [ ] In `/docs`, after Authorize, **GET /results/funnel** returns data.
4. [ ] The dashboard header shows **CBSE records 5,000 · Linked 3,712 (74.2%) · Precision 1.000 · Recall
   0.873 · QUEUE_FOR_OUTREACH 3,712 · DISCOVERY 141 · eligible schemes/student 18.1**. These are exactly
   the prototype's numbers.
5. [ ] The **Scenarios** tab shows *Unreachable rows: 27 of 56* and totals of TP 3,712 · FP 0 · FN 538 · TN 750 ·
   G7-blocked 48.
6. [ ] **Student drill-down** opens a student and lists their eligible schemes.
7. [ ] The **Admin** tab shows the row counts: jan_aadhaar_members 21,173, cbse_results 5,000, scheme_rules 547,
   eligibility_results 248,704.

## Step 9: Costs and free-plan limits
| Item | Free plan behaviour |
|---|---|
| Web services (API, dashboard) | Free. They **go to sleep after 15 minutes** with no visitors. The next visit wakes them, which takes **about 1 minute**. Render gives 750 free hours per workspace per month, which is enough for these two services because sleeping services don't use hours. |
| Postgres database | Free: 1 GB storage (this project uses about 250 MB). **It expires 30 days after creation.** After that you have 14 days to upgrade it to a paid plan, or Render deletes it. To keep using the free plan, delete the old database and create a new one: re-apply the Blueprint, and the data loads again automatically. |
| One free database | Only one free Postgres database is allowed per workspace. |
| Shell / one-off jobs | Not available on the free plan, so seeding happens through the API or dashboard (step 5). |

**For a longer pilot or a demo that must always be fast**, upgrade in the Render dashboard (the service's
**Settings → Instance type**, and the database's **Change plan**):
* API and dashboard: the smallest paid instance ("Starter", roughly US$7 per month each). These never sleep.
* Database: the smallest paid Postgres (roughly US$6–7 per month). It has no 30-day expiry and includes backups.

That comes to roughly **US$20 per month** in total. Check render.com/pricing for current prices. In the
Blueprint you can change `plan: free` to the paid plan names later.

## Step 10: Troubleshooting
| What you see | What it means | What to do |
|---|---|---|
| Blueprint says **"render.yaml not found"** | The file is not at the top level of the repo | On GitHub, check that `render.yaml` is on the repository's main page and not inside a folder. Re-upload if needed. |
| Build fails with **"Could not open requirements file"** | `requirements.txt` or `requirements-dashboard.txt` is missing | Upload the missing file to the top level of the repo. Render redeploys automatically. |
| Build fails mentioning a **Python version** | The Python version is wrong | The Blueprint sets `PYTHON_VERSION=3.13.5` in the `mosje-shared` group. Check that it is still there. |
| Dashboard shows **"Cannot reach the API"** | The API is asleep, still deploying, or the dashboard is guessing the wrong address | Wait 1–2 minutes and reload. If it keeps happening: open **mosje-dashboard → Environment**, add `API_BASE_URL` = your API address (e.g. `https://mosje-api-xxxx.onrender.com`), and save. |
| Dashboard shows **401 / "invalid X-API-Key"** | The dashboard and the API have different keys | Make sure both services use the **mosje-shared** group and that no service has its own `API_KEY` that overrides it. |
| `/health` shows **"seeded": false** or a `startup_error` | Loading failed | Open **mosje-api → Logs** and look for the red error. Check that the `data/` folder was uploaded with all four files. Then use Admin → Load (seed). |
| Pipeline run shows **FAILED** | See the `error` column in the Admin tab | Most often the data is not loaded yet: seed first, then run. |
| A run stays **RUNNING** after a restart | The service restarted mid-run | The API marks it FAILED on its next start. Just run again. |
| Database **expired** (after 30 days) | Free Postgres limit | Upgrade the database, or delete it and re-sync the Blueprint (**Blueprints → mosje → Manual sync**). The API reloads the data by itself. |
| Everything is slow the first time | Free services were asleep | Normal. Open the dashboard a minute before a demo. |

## Step 11: Security notes (read this)
* **Synthetic data only.** Every name, ID and mobile number in this deployment is fictional (generated with
  a fixed seed). Render is a commercial, overseas cloud. **Real Jan Aadhaar, CBSE or any other government
  personal data must never be uploaded to Render or GitHub.**
* **Production goes on government infrastructure.** As the concept note says, the real system must be
  hosted on **NIC / MeghRaj** (GI Cloud). It must follow the department's data-sharing agreements, Aadhaar-related
  rules and the DPDP Act, 2023, with proper access control and audit logging. This Render setup is for demos and
  for reviewing the rules only.
* **API key.** Treat it like a password. Don't paste it into chats or documents. Change it if it leaks (step 4).
  The key protects the API. The dashboard itself has **no login**: anyone who has the dashboard address can
  view it. That is acceptable for synthetic data, but keep the address within the team.
* **Private repository.** Keep the GitHub repository private. Never upload a `.env` file containing real keys.
* **Outreach.** The system only *builds* outreach queues. It does not send any WhatsApp or SMS messages.
  The eligible-shortlist message text is a prototype draft that still needs departmental approval.

---

### Appendix A: Updating the code later
Upload the changed files to GitHub (**Add file → Upload files**, using the same folder structure) and commit.
Render notices the change and redeploys both services automatically in a few minutes.

### Appendix B: Running it on your own laptop
If Docker Desktop is installed: copy `.env.example` to `.env`, set `API_KEY`, and run `docker compose up --build`.
Then open http://localhost:8501 (dashboard) and http://localhost:8000/docs (API).

### Appendix C: Glossary
* **Repository (repo)**: a project folder on GitHub.
* **Blueprint**: the `render.yaml` file that describes all the services.
* **API**: a program other programs talk to. The dashboard talks to it.
* **Seed**: loading the starting data into the database.
* **Pipeline**: the run that links CBSE students to Jan Aadhaar and checks scheme eligibility.
* **Environment variable**: a named setting (like `API_KEY`) given to a service without being written into the code.
